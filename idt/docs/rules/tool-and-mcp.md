# Tool & MCP Development Rules (TOOL-MCP-001)

> 원본: document-template-extractor 회고 (2026-07)
> 참조 시점: **도구(내부/MCP) 추가·변경·조회 관련 개발 시 반드시 먼저 확인**

---

## 0. 도구는 두 종류 — 소스별로 등록 경로가 다르다

| 소스 | 진실원(정의 위치) | tool_catalog 반영 경로 | tool_id 규약 |
|------|------------------|----------------------|-------------|
| **internal** (내부 코드 도구) | **`src/domain/agent_builder/tool_registry.py`의 `TOOL_REGISTRY`** | 부팅 시 `SyncInternalToolsUseCase`가 자동 upsert | `internal:{tool_id}` |
| **mcp** (외부 MCP 서버 도구) | MCP 레지스트리 DB(`mcp_server_registry`) | `SyncMcpToolsUseCase`가 서버별 동기화 | `mcp:{server_id}:{tool}` (카탈로그) / `mcp_{uuid}` (로더 조회) |

> **핵심**: 내부 도구의 단일 진실원은 **코드(`TOOL_REGISTRY`)**다. tool_catalog 테이블은 UI 노출용 파생 캐시일 뿐이다.

---

## 1. 내부 도구 추가 절차 (필수 순서)

새 내부 도구를 추가할 때는 **아래 지점을 전부** 손봐야 실제로 동작+노출된다.

1. **`TOOL_REGISTRY`에 `ToolMeta` 등록** (`domain/agent_builder/tool_registry.py`)
   - `category`: `search` | `action` | `analysis`. 기본값 `action`.
   - `requires_env`: 필요한 환경변수 키 목록.
2. **`ToolFactory`에 실행체 생성 분기 추가** (`infrastructure/agent_builder/tool_factory.py`)
   - `create()`/`create_async()`의 `match tool_id` 에 `case` 추가. 없으면 컴파일 시 `Unsupported tool_id` 에러.
   - 단, `document_extractor`처럼 **전용 합성 노드**로 컴파일되는 도구는 `workflow_compiler`에서 선행 분기하고 ToolFactory를 타지 않을 수 있다.
3. **UI 노출은 자동** — `SyncInternalToolsUseCase`가 부팅 시 `TOOL_REGISTRY` → `tool_catalog`(source=`internal`, `internal:{id}`)로 upsert한다.
   - ⚠️ **손수 시드 마이그레이션(V008식 INSERT) 금지.** 코드 등록만으로 목록에 떠야 한다. per-tool 시드를 추가하면 드리프트가 재발한다.
   - 적용은 **앱 재시작**으로 충분(마이그레이션 불필요).

### ❌ 흔한 실수 (document-template-extractor 실제 사례)
- `TOOL_REGISTRY`에만 등록하고 UI에 안 뜬다고 당황 → 프론트 도구 선택창은 `GET /agents/tools`(TOOL_REGISTRY)가 아니라 **`GET /api/v1/tool-catalog`(tool_catalog 테이블)**을 읽는다. `SyncInternalToolsUseCase`가 그 간극을 메운다.
- `data_analysis`도 과거 이 시드 누락으로 목록에 안 떴다 — 동일 원인.

---

## 2. 프론트엔드 도구 목록 소스

- 프론트 `useToolCatalog` → `GET /api/v1/tool-catalog` → `tool_catalog` 테이블(`list_active`).
- **`GET /agents/tools`(TOOL_REGISTRY 직접 노출)와 혼동 금지.** 도구 선택창은 tool-catalog만 본다.
- 도구 id 프리픽스: 생성 payload는 `internal:{id}` / `mcp_{uuid}` 형태로 오고, 백엔드 `_normalize_tool_id`가 `:` 앞 프리픽스를 떼어 `TOOL_REGISTRY` 키로 정규화한다. **프론트 상수(예: `DOCUMENT_EXTRACTOR_TOOL_ID = 'internal:document_extractor'`)는 카탈로그 tool_id와 정확히 일치**시켜야 한다.

---

## 3. MCP 변환/외부 도구 소비 시

- MCP 도구 호출은 `MCPToolLoader.load_by_tool_id(tool_id="mcp_{uuid}", repository, request_id)` → `tool.ainvoke(...)`.
- **MCP 서버마다 입출력 계약이 다르다.** 어댑터(예: `DocumentConversionAdapter`)에 정규화 계층을 두고, **실제 등록된 도구로 PoC를 먼저** 수행한다(`/verify-mcp-connections`).
- **`'Session terminated'` 에러 = 대부분 HTTP 404** (세션 만료 아님). 주로 빈 `api_key`가 URL에서 누락된 경우. register/update 검증 + 진단 힌트로 대응.
- 앱 싱글톤(WorkflowCompiler 등)에서 런타임에 MCP 레지스트리를 조회할 때는 per-request 세션 대신 **session-scoped 어댑터**(`SessionScopedMcpServerRepository` 등)를 쓴다.

---

## 4. 도구 종속 테이블 FK 콜레이션 주의 (errno 3780)

- `agent_definition` 등 **초기 테이블은 SQLAlchemy `create_all`로 생성**되어 **DB 기본 콜레이션**(MySQL 8: 보통 `utf8mb4_0900_ai_ci`)을 쓴다. 마이그레이션 SQL의 CREATE가 없다.
- 이 테이블을 FK로 참조하는 신규 테이블에서 `COLLATE=utf8mb4_unicode_ci` 등을 **명시하면 콜레이션 불일치로 FK 생성 실패(errno 3780)**.
- **해결**: 신규 테이블에 테이블 레벨 `COLLATE`를 명시하지 말고 DB 기본을 상속시키거나, FK 컬럼 콜레이션을 참조 컬럼과 명시적으로 일치시킨다.
- 확인 쿼리:
  ```sql
  SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND COLUMN_NAME IN ('id','agent_id')
    AND TABLE_NAME IN ('agent_definition','<신규테이블>');
  ```

---

## 5. 체크리스트 (도구 개발 PR 전)

- [ ] 내부 도구: `TOOL_REGISTRY` 등록 + (필요 시) `ToolFactory` case 추가
- [ ] UI 노출은 `SyncInternalToolsUseCase`(부팅 자동)에 의존 — 손수 시드 마이그레이션 추가하지 않음
- [ ] 프론트 tool_id 상수 = 카탈로그 `internal:{id}`와 일치
- [ ] MCP 소비: 어댑터 정규화 + 실도구 PoC(`/verify-mcp-connections`)
- [ ] FK 종속 테이블: 콜레이션 명시 지양(errno 3780 회피)
- [ ] TDD: domain 순수 규칙 우선, repository는 commit/rollback 없음, `print()` 금지
