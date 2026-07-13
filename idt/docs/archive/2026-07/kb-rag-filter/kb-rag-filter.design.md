# kb-rag-filter Design Document

> **Summary**: `RagToolConfig`에 opt-in 필드 `kb_id`를 신설하고, 에이전트 저장 시점에 KB 존재·권한 검증 + 물리 컬렉션 고정(canonicalize) + scope clamp를 수행한다. 런타임은 ToolFactory가 `kb_id`를 metadata_filter에 병합하는 것만 추가 — `InternalDocumentSearchTool`은 무수정. 프론트는 KB 드롭다운을 컬렉션 드롭다운과 병행 추가한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **Plan**: `docs/01-plan/features/kb-rag-filter.plan.md`

---

## 1. Overview

Plan의 FR-01~07을 구현하기 위한 상세 설계. Plan §4에서 이월된 결정 사항 5건을 §3에서 모두 확정한다.

핵심 설계 원칙: **런타임 최소 변경**. 검색 격리는 이미 존재하는 두 경로(hybrid의 `metadata_filter` payload 필터, routed의 `RoutedScope.kb_id` 매핑 `src/application/rag_agent/tools.py:37,185`)를 그대로 재사용하고, 신규 로직은 "저장 시점 검증·고정"과 "생성 시점 필터 병합" 두 지점에만 넣는다.

---

## 2. 데이터 흐름

```
[에이전트 저장 시 — Create/UpdateAgentUseCase]
  tool_config.kb_id 존재?
    ├─ 예 → KB 조회(kb_repo) ─ 미존재/권한없음 → 400/403
    │        ├─ tool_config.collection_name ← kb.collection_name (canonicalize, D1)
    │        └─ kb.scope → scopes 목록 합류 → VisibilityPolicy.clamp_visibility (D7)
    └─ 아니오 → 기존 동작 그대로 (컬렉션 scope clamp만)

[에이전트 실행 시 — ToolFactory.create]
  RagToolConfig.kb_id 존재?
    ├─ 예 → effective_filter = {**metadata_filter, "kb_id": kb_id} (D6)
    └─ 아니오 → metadata_filter 그대로
  → InternalDocumentSearchTool(metadata_filter=effective_filter,
                               collection_name=저장 시 고정된 KB 컬렉션)
     ├─ hybrid: payload 필터 kb_id 적용 (기존 경로)
     └─ routed: _ROUTED_SCOPE_KEYS의 kb_id → RoutedScope (기존 경로)
```

---

## 3. 결정 사항 (Plan §4 이월분 확정)

### D1. 물리 컬렉션 해석 = **저장 시점 고정** (에이전트 생성/수정 UseCase)

- **결정**: `kb_id`가 지정된 tool_config는 UseCase가 KB를 조회해 `tool_config["collection_name"] = kb.collection_name`으로 덮어써 저장한다. 런타임 KB 조회는 하지 않는다.
- **근거 1 (구조)**: 비 MCP 도구는 `WorkflowCompiler`가 **동기** `ToolFactory.create()`로 생성 (`workflow_compiler.py:235`). 런타임 KB 조회(async MySQL)를 넣으려면 create의 비동기화 또는 getter 우회가 필요 — 침습 대비 이득 없음.
- **근거 2 (불변성)**: KB API는 create/list/get/delete뿐, 컬렉션 재배정(update)이 존재하지 않음 (`knowledge_base_router.py`). 저장 시 고정해도 어긋날 경로가 없다.
- **근거 3 (비용)**: scope clamp(D7) 때문에 UseCase가 어차피 KB를 조회한다 — 같은 조회 결과로 canonicalize까지 처리(추가 쿼리 0).
- 추후 KB 컬렉션 이동 기능이 생기면 재태깅/재고정은 그 PDCA의 책임으로 명시.

### D2. kb_id 우선 규칙

- `kb_id` 지정 시 사용자가 보낸 `collection_name`은 **무시하고 KB의 컬렉션으로 덮어씀** (D1의 canonicalize가 곧 규칙).
- `metadata_filter`에 수동으로 `"kb_id"` 키를 넣은 경우: **first-class `kb_id` 필드가 우선** — ToolFactory 병합 시 `{**metadata_filter, "kb_id": kb_id}` 순서로 덮어씀 (D6).
- UI: KB 선택 시 컬렉션 드롭다운 **비활성화(disabled)** + "지식베이스의 컬렉션이 자동 적용됩니다" 안내. KB 해제 시 재활성.

### D3. 고아 kb_id 처리

- **저장 시**: KB 미존재 → `ValueError`(400), 읽기 권한 없음 → `PermissionError`(403). 드롭다운 선택이므로 정상 흐름에서 발생하지 않고, stale 선택만 걸러낸다.
- **실행 시**: 추가 방어 없음. KB는 soft-delete이고 벡터는 정리 전까지 잔존(`use_case.py:120` "vectors remain until cleanup")하므로 삭제 직후에도 검색은 동작한다. 벡터 정리 후에는 빈 결과 — 후속 `kb-orphan-cleanup`에서 참조 에이전트 처리.

### D4. KB 목록 API = 기존 `GET /api/v1/knowledge-bases` 재사용

- 권한 필터 **이미 구현 확인**: admin은 `find_all_active`, 일반 사용자는 `find_accessible(user.id, dept_ids)` (`src/application/knowledge_base/use_case.py:94-100`). 신규 엔드포인트 불요.
- 응답 `KbInfoResponse`에 드롭다운 필요 필드(`kb_id`, `name`, `scope`, `collection_name`, `description`) 모두 존재 — 백엔드 무변경.

### D5. kb_id 형식 검증 수준

- 도메인 VO(`RagToolConfig`)는 형식 검증 **안 함** (UUID 정규식 과검증 지양 — 존재 검증이 상위에서 수행되므로 중복). 빈 문자열은 저장 UseCase에서 None 취급으로 정규화.
- 존재·권한 검증은 D3대로 UseCase 책임.

### D6. ToolFactory 병합 방식

- `create()`의 `internal_document_search` 분기에서 `rag_config.kb_id`가 있으면 `metadata_filter`에 병합해 전달. `InternalDocumentSearchTool` 시그니처·내부 로직 무수정.
- routed 경로 회귀 없음: `kb_id`는 `_ROUTED_SCOPE_KEYS` 소속이라 병합돼도 강등 사유가 아니며 `RoutedScope.kb_id`로 승격된다 (`tools.py:170-186`).

### D7. scope clamp 확장

- `CreateAgentUseCase._resolve_visibility`(`create_agent_use_case.py:313`)의 scopes 수집을 확장: 기존 `_extract_collection_names` + 신규 `_extract_kb_ids` → `kb_repo.find_by_id`(존재 검증 겸용) → `kb.scope.value`를 scopes 목록에 합류.
- `UpdateAgentUseCase`(`update_agent_use_case.py:203-209`)도 동일 helper 적용.
- DI: 두 UseCase에 `kb_repo: KnowledgeBaseRepositoryInterface | None = None` 주입(기존 `dept_repo` 선례와 동일한 optional 패턴). **단, kb_id가 지정된 요청에서 kb_repo가 None이면 명시적 에러** — 격리 우회 방지(조용한 skip 금지).

---

## 4. Backend 상세 설계 (idt/)

### 4.1 `src/domain/agent_builder/rag_tool_config.py`

```python
@dataclass(frozen=True)
class RagToolConfig:
    collection_name: str | None = None
    ...
    use_routed_search: bool = False
    # kb-rag-filter D5: 논리 지식베이스 필터 opt-in.
    #   None = 미사용(기존 동작). 존재/권한 검증은 저장 UseCase 책임.
    kb_id: str | None = None
```

- `__post_init__`/`RagToolConfigPolicy` 변경 없음 (D5).
- `_parse_rag_config`의 `RagToolConfig(**tool_config)`가 그대로 수용 — 저장된 기존 config(kb_id 없음)와 완전 호환.

### 4.2 `src/application/agent_builder/schemas.py`

- `RagToolConfigRequest`(`:24`)에 `kb_id: str | None = None` 추가. 응답 쪽은 `tool_config: dict` 통과라 무변경.

### 4.3 `src/application/agent_builder/create_agent_use_case.py`

- 신규 helper (둘 다 `@staticmethod`/instance method, 40줄 규칙 준수):
  - `_extract_kb_ids(workers) -> list[str]` — `tool_config.get("kb_id")` 수집 (`_extract_collection_names` `:332` 패턴 복제)
  - `_resolve_kb(kb_id, request_id) -> KnowledgeBase` — 미존재 시 `ValueError(f"Knowledge base not found: {kb_id}")`
- `_resolve_visibility` 확장: KB scopes를 컬렉션 scopes에 합류 후 clamp (기존 반환 계약 `(vis, was_clamped, max_vis)` 유지).
- **canonicalize**: worker 순회 시 `kb_id` 있는 tool_config에 `collection_name = kb.collection_name` 주입 (KB 조회 결과 재사용, 요청당 KB별 1회 조회 — 중복 kb_id는 dict 캐시).
- 생성자에 `kb_repo` 파라미터 추가.

### 4.4 `src/application/agent_builder/update_agent_use_case.py`

- 4.3과 동일한 helper 적용 (공통화가 자연스러우면 `VisibilityPolicy` 옆 helper 모듈로 추출 — 단 레이어 이동 금지, application 내부 유지).

### 4.5 `src/infrastructure/agent_builder/tool_factory.py`

```python
case "internal_document_search":
    rag_config = self._parse_rag_config(tool_config)
    effective_filter = dict(rag_config.metadata_filter)
    if rag_config.kb_id:
        effective_filter["kb_id"] = rag_config.kb_id  # D2: 필드 우선
    ...
    metadata_filter=effective_filter,
```

### 4.6 `src/api/main.py` (DI)

- `create_agent_use_case` factory(`:2210`)와 `update_agent_use_case` factory(`:2227`)에 `kb_repo=KnowledgeBaseRepository(session, app_logger)` 추가 — 동일 요청 세션 공유(db-session 규칙 준수, `kb_use_case_factory :2642` 선례).

### 4.7 변경 없음 (명시)

- `InternalDocumentSearchTool`, hybrid/routed 검색 경로, KB 라우터/UseCase/Repository, DB 스키마(마이그레이션 불요 — tool_config는 JSON 컬럼).

---

## 5. Frontend 상세 설계 (idt_front/)

### 5.1 타입 — `src/types/ragToolConfig.ts`

```typescript
export interface RagToolConfig {
  ...
  /** kb-rag-filter: 논리 지식베이스 필터 opt-in — 설정 시 컬렉션은 KB 것으로 자동 고정 */
  kb_id?: string;
}

export interface KnowledgeBaseInfo {
  kb_id: string;
  name: string;
  description?: string | null;
  scope: CollectionScope;
  collection_name: string;
}
```

- `DEFAULT_RAG_CONFIG` 무변경 (optional 필드).

### 5.2 API 연동

- `constants/api.ts`: `KNOWLEDGE_BASES: '/api/v1/knowledge-bases'`
- `services/knowledgeBaseService.ts`: `getKnowledgeBases(): Promise<KnowledgeBaseInfo[]>` (`ragToolService` 패턴, 응답 envelope는 `KbListResponse` 구조 확인 후 매핑)
- `lib/queryKeys.ts`: `knowledgeBases.list()` 키 추가
- `hooks/useKnowledgeBases.ts`: `useQuery` + `staleTime 5분` (`useCollections` 패턴)

### 5.3 `RagConfigPanel.tsx`

- **Section 0 (신규, 컬렉션 섹션 위)**: "검색 대상 지식베이스" 드롭다운
  - 옵션: `{ value: '', label: '선택 안 함' }` + KB 목록 (`[개인]/[부서]/[공개]` scope 라벨 프리픽스 — 기존 `SCOPE_LABELS` 재사용)
  - 선택 시: `onChange({ ...config, kb_id, collection_name: undefined, metadata_filter: {} })` — 컬렉션 변경 핸들러와 동일하게 필터 초기화
  - 개인/부서 KB 선택 시 기존 컬렉션과 동일한 "에이전트 공개 범위가 자동 제한됩니다" 안내 재사용
  - 로딩/에러/재시도 UI는 컬렉션 섹션 패턴 복제
- **Section 1 (기존 컬렉션)**: `config.kb_id` 존재 시 드롭다운 `disabled` + "지식베이스 선택 시 해당 KB의 컬렉션이 자동 적용됩니다" 안내 (D2)
- **메타데이터 필터 키 자동완성**: KB 선택 시 `useMetadataKeys(선택 KB의 collection_name)`로 연동 (KB 목록 응답에 collection_name 포함되므로 프론트에서 해석 가능)

### 5.4 `LeftConfigPanel.tsx` — 요약 배지

- `RagConfigSummaryBadge`(`:476`): `config.kb_id` 있으면 KB 이름을 최우선 라벨로 표시 (`KB이름 · 하이브리드 · top_k 5`), 없으면 기존 컬렉션 라벨 로직 유지. `useKnowledgeBases` 데이터 전달.

---

## 6. 테스트 설계 (TDD — 구현 전 작성)

### 6.1 Backend (pytest)

| 테스트 | 검증 대상 | FR |
|--------|----------|-----|
| `test_rag_tool_config_kb_id_default_none` | kb_id 기본 None, 기존 dict로 생성 시 무회귀 | FR-02 |
| `test_tool_factory_merges_kb_id_into_filter` | kb_id → metadata_filter 병합, 수동 kb_id 키 덮어씀 | FR-03, D2 |
| `test_tool_factory_without_kb_id_unchanged` | kb_id 없으면 filter 원본 그대로 | FR-02, FR-06 |
| `test_create_agent_kb_scope_clamps_visibility` | 개인/부서 KB → visibility clamp (컬렉션 scope와 합산) | FR-05 |
| `test_create_agent_canonicalizes_collection_from_kb` | 저장된 tool_config.collection_name == kb.collection_name | FR-04, D1 |
| `test_create_agent_unknown_kb_raises` | 미존재 kb_id → ValueError | D3 |
| `test_create_agent_kb_without_repo_raises` | kb_id 지정 + kb_repo=None → 명시적 에러 | D7 |
| `test_update_agent_kb_scope_clamps_visibility` | 수정 경로 동일 clamp | FR-05 |

- 기존 `tests/` 중 agent_builder·tool_factory 테스트 무회귀 확인 (Windows 이벤트 루프 flakiness — 격리 실행).

### 6.2 Frontend (Vitest + RTL + MSW)

| 테스트 | 검증 대상 |
|--------|----------|
| `useKnowledgeBases` 훅 — 목록 조회/에러 | 5.2 |
| `RagConfigPanel` — KB 드롭다운 렌더/선택 시 kb_id 설정 + collection/filter 초기화 | 5.3 |
| `RagConfigPanel` — KB 선택 시 컬렉션 드롭다운 disabled + 안내 노출 | D2 |
| `RagConfigPanel` — 개인 KB 선택 시 공개범위 제한 안내 | FR-07 |
| `RagConfigSummaryBadge` — kb_id 있으면 KB 이름 표시 | 5.4 |

- MSW는 **파일별 `server.listen` 3종 훅 직접 선언** (전역 setup 없음 — 프로젝트 규칙).

---

## 7. 구현 순서

1. **[BE-1]** 도메인: `RagToolConfig.kb_id` (+테스트) — 4.1
2. **[BE-2]** ToolFactory 병합 (+테스트) — 4.5
3. **[BE-3]** create/update UseCase: 검증·canonicalize·clamp (+테스트) — 4.3, 4.4
4. **[BE-4]** API 스키마 + main.py DI — 4.2, 4.6
5. **[FE-1]** 타입/상수/서비스/훅 (+테스트) — 5.1, 5.2
6. **[FE-2]** RagConfigPanel KB 섹션 (+테스트) — 5.3
7. **[FE-3]** 요약 배지 (+테스트) — 5.4
8. **[E2E]** 수동 검증: KB 문서 업로드 → KB 선택 에이전트 생성 → 검색 격리 + clamp 확인

---

## 8. 영향 범위 / 주의사항

- **무회귀 보장 지점**: `kb_id=None`이면 모든 신규 분기 미진입 — 기존 에이전트/설정 화면 동작 불변 (FR-06).
- `agent_composer`(NL 컴포저)와 `auto_fork_service`가 tool_config를 생성/복사하는 경로는 kb_id를 모르는 채 통과(dict 복사) — 무변경으로 안전하나, Do 단계에서 composer가 tool_config를 화이트리스트 필터링하는지 1회 확인.
- 사전 실패 테스트(tests/api 28건 등 기준선)와 신규 회귀를 혼동하지 말 것.
- 레이어 규칙: KB 조회는 UseCase(application)에서 인터페이스(domain) 경유 — domain은 무의존 유지.

---

## 9. Acceptance 매핑

| Plan 완료 기준 | 검증 방법 |
|----------------|----------|
| KB 격리 검색 | E2E: KB A/B 각 1문서 업로드 → KB A 에이전트 질의 → A 문서만 등장 |
| 기존 에이전트 무영향 | 6.1 무회귀 테스트 + kb_id 미설정 화면 스냅샷 비교 |
| scope clamp (생성·수정) | 6.1 clamp 테스트 4건 |
| 프론트 테스트 통과 | 6.2 전건 (`--pool=threads`) |
