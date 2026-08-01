# Builtin Tools Design Document

> **Summary**: 빌트인 도구의 런타임 SoT는 `tool_catalog.is_builtin`(V054)이며, 프레시 DB 시드는 `ToolMeta.builtin_default`(INSERT 시에만 적용)로 이원화한다(D1). 부팅 sync의 UPDATE 분기는 현행대로 `is_builtin`을 건드리지 않아 관리자 설정이 자연 보존된다(D2). 관리자 토글은 `PATCH /api/v1/tool-catalog/builtin`(`require_role("admin")`)(D3), 주입은 `CreateAgentUseCase`에서 정책 검증 **후** 별도 리스트로 합류시켜 상한(MAX_TOOLS=5)에서 제외한다(D5/D6). 프론트는 `excludedBuiltinTools` 전용 폼 상태를 `ToolPickerModal`에서만 토글 가능하게 하여 Fix 에이전트(채팅) 경로의 구조적 우회 불가를 완성한다(D8).
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-01
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/builtin-tools.plan.md`

---

## 1. Design Overview

```
[관리자]                          [에이전트 생성자]
AdminToolsPage (신규 /admin/tools)   AgentBuilderPage (폼/Fix 채팅)
  │ PATCH /tool-catalog/builtin        │ POST /agents
  ▼                                    │   tool_ids (사용자 선택)
tool_catalog.is_builtin  ◄─ V054       │   exclude_builtin_tool_ids (폼 수동 해제만)
  ▲ 보존                               ▼
부팅 sync (internal/MCP upsert)     CreateAgentUseCase
  └ INSERT 시에만 builtin_default      ├ Step 1   스켈레톤 (사용자 도구)
    (wiki_read/wiki_list=True)         ├ Step 2   정책 검증 (사용자 선택분만 — 상한 5)
                                       ├ Step 2.7 빌트인 주입 ← list_builtin(active)
                                       │           dedup·exclude·MCP 격하
                                       └ Step 4   agent_tool 저장 (스냅샷)
```

- 실행 경로(WorkflowCompiler)·수정 경로(UpdateAgentUseCase)는 **무변경** — 주입된 빌트인
  워커는 저장 후 기존 워커와 동일하게 취급된다.
- Fix 에이전트(compose)는 무저장 초안 → 저장은 POST /agents 단일 수렴 지점이므로
  백엔드 주입 + 프론트 전용 상태(D8)로 "채팅이 빌트인을 뺄 수 없음"이 구조적으로 보장된다.

---

## 2. D1 — 빌트인 SoT와 시드 이원화

### 2.1 결정

| 층 | 역할 |
|----|------|
| `tool_catalog.is_builtin` (DB) | **런타임 SoT** — 관리자 토글 대상, 주입 판정 기준 |
| `ToolMeta.builtin_default` (코드) | **INSERT 시드 전용** — 카탈로그에 행이 처음 생길 때만 초기값 제공. 이후 DB 값이 항상 우선 |

**프레시 DB 문제 해결**: V054의 UPDATE 시드는 기존 DB에서만 유효하다(프레시 DB는
마이그레이션 시점에 카탈로그 행이 없어 no-op). `builtin_default`가 첫 부팅 sync의
INSERT 경로에서 시드를 대신하므로 두 경우 모두 wiki 2종이 빌트인으로 시작한다.

| 시나리오 | V054 UPDATE | sync INSERT (builtin_default) | 결과 |
|----------|-------------|------------------------------|------|
| 기존 DB (wiki 행 존재) | 적용됨 | 미발생 (UPDATE 분기) | 빌트인 ✓ |
| 프레시 DB | no-op | 적용됨 | 빌트인 ✓ |
| 관리자가 해제 후 재부팅 | — | 미발생 (UPDATE 분기 = 보존) | 해제 유지 ✓ |

### 2.2 V054 마이그레이션

```sql
-- builtin-tools D1: 에이전트 생성 시 자동 주입되는 빌트인 도구 플래그.
-- 런타임 SoT는 본 컬럼(관리자 토글). 부팅 sync는 UPDATE 시 본 컬럼을 건드리지 않는다.
ALTER TABLE tool_catalog
    ADD COLUMN is_builtin TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '빌트인 여부 — 에이전트 생성 시 자동 주입. 관리자 토글, sync 보존, INSERT 시 ToolMeta.builtin_default 시드';

-- 초기 시드 (기존 DB 전용 — 프레시 DB는 첫 sync INSERT가 builtin_default로 시드)
UPDATE tool_catalog SET is_builtin = 1
WHERE tool_id IN ('internal:wiki_read', 'internal:wiki_list');
```

> `tests/db/test_migration_ddl_comments.py`가 V054+를 검사하므로 COMMENT 필수 (CLAUDE.md 3장).

### 2.3 코드 변경

- `src/domain/agent_builder/schemas.py` `ToolMeta`: `builtin_default: bool = False` 추가
- `tool_registry.py`: `wiki_read`/`wiki_list`에 `builtin_default=True`
- `src/domain/tool_catalog/entity.py` `ToolCatalogEntry`: `is_builtin: bool = False` 추가
- `src/infrastructure/tool_catalog/models.py`: `is_builtin: Mapped[bool] = mapped_column(default=False, comment='...')` (DDL과 동일 코멘트)
- `SyncInternalToolsUseCase.execute()`: entry 생성 시 `is_builtin=meta.builtin_default` 전달
  (INSERT 경로에서만 유효 — D2). `_deactivate_stale`의 entry 재구성에도 `is_builtin=entry.is_builtin` 유지
- `SyncMcpToolsUseCase`: 무변경 (entry 기본값 False → INSERT 시 False, UPDATE 시 보존)

---

## 3. D2 — 부팅 sync의 is_builtin 보존 (기존 코드 성질 활용)

`ToolCatalogRepository.upsert_by_tool_id`의 UPDATE 분기는 현재
`name/description/is_active/updated_at`만 `.values()`에 명시한다 → **is_builtin은 수정하지
않아도 자연 보존**된다. 설계 원칙: **UPDATE 분기 `.values()`에 is_builtin을 추가하지 않는다.**

- 구현 변경: `save()`(INSERT)에 `is_builtin=entry.is_builtin` 전달, `_to_domain`에 매핑 추가.
- 이 성질은 암묵이므로 **보존 단언 테스트로 계약화**한다:
  "set_builtin(True) → SyncInternalToolsUseCase 재실행 → is_builtin 여전히 True".
- `_deactivate_stale`(레지스트리 이탈 도구 비활성화)도 UPDATE 분기를 타므로 보존 유지.

---

## 4. D3 — 관리자 토글 API

### 4.1 엔드포인트

```
PATCH /api/v1/tool-catalog/builtin          (require_role("admin") — /sync와 동일 선례)
Body:     { "tool_id": "internal:wiki_read", "is_builtin": true }
200:      { "tool_id": "internal:wiki_read", "is_builtin": true }
404(400): 존재하지 않는 tool_id → ValueError("Unknown catalog tool_id: ...")
403:      비관리자 (require_role 기존 동작)
```

tool_id를 path가 아닌 body로 받는 이유: 카탈로그 tool_id는 `mcp:{uuid}:{tool}` 형식으로
콜론·임의 도구명을 포함하여 path 세그먼트로 부적합. 기존 `/sync`(POST+body) 스타일과 정합.

### 4.2 구성 요소

| 레이어 | 신규/수정 | 내용 |
|--------|-----------|------|
| domain | `ToolCatalogRepositoryInterface` | `set_builtin(tool_id, is_builtin, request_id) -> ToolCatalogEntry`, `list_builtin(request_id) -> list[ToolCatalogEntry]` 추상 메서드 추가 |
| infrastructure | `ToolCatalogRepository` | `set_builtin`: 대상 UPDATE(is_builtin, updated_at) — 미존재 시 None 반환이 아닌 상위 판단용 조회 선행. `list_builtin`: `is_builtin==True AND is_active==True` 필터 |
| application | `SetBuiltinToolUseCase` (신규) | find_by_tool_id로 존재 검증(없으면 ValueError) → set_builtin → 로깅. 비활성 도구도 플래그 지정 허용(주입 시 active 필터가 방어) |
| application | `schemas.py` | `SetBuiltinRequest {tool_id, is_builtin}`, `SetBuiltinResponse`, `ToolCatalogItemResponse.is_builtin: bool = False` 추가 (D4) |
| interfaces | `tool_catalog_router.py` | PATCH 라우트 + DI 플레이스홀더 `get_set_builtin_use_case` |
| DI | `main.py create_tool_catalog_factories` | SetBuiltin 팩토리 추가 + override 배선 |

### 4.3 D4 — 목록 응답 노출

`ListToolCatalogUseCase`가 entity → `ToolCatalogItemResponse` 매핑 시 `is_builtin` 포함.
프론트 타입 동기화는 §7.

---

## 5. D5 — CreateAgentUseCase 빌트인 주입

### 5.1 주입 위치와 순서

기존 Step 번호 기준 **Step 2.7**(정책 검증·visibility 확정 후, 저장 직전)에 주입한다.

```python
# Step 2.7 (builtin-tools D5): 빌트인 도구 주입 — 정책 검증(사용자 선택분) 이후이므로
# 상한(MAX_TOOLS)에서 제외된다(D6). visibility/KB 해석은 사용자 워커 기준 유지
# (빌트인은 tool_config 없음 — Plan Out of Scope).
builtin_workers = await self._build_builtin_workers(
    all_workers, request.exclude_builtin_tool_ids, request_id
)
all_workers = all_workers + builtin_workers
```

| 순서 결정 | 근거 |
|-----------|------|
| 정책 검증(Step 2) **후** 주입 | D6: 빌트인은 상한 제외 — `validate_tool_count`/`validate_worker_count`는 사용자 선택분만 검증 |
| visibility/KB 해석(Step 2.5) **후** 주입 | 빌트인은 tool_config 없음 → 컬렉션/KB scope에 영향 없음. 해석 대상에서 제외해 기존 로직 무변경 |
| 템플릿 바인딩(Step 1.75)과 무관 | `document_template`은 skeleton.workers에서 extractor를 찾음 — 빌트인 주입분은 대상 아님(설계 제약: config 필요 도구의 빌트인화는 후속) |

### 5.2 `_build_builtin_workers` 알고리즘

```
1. self._tool_catalog_repo가 None이면 [] 반환 (optional 의존성 무회귀 패턴)
2. entries = tool_catalog_repo.list_builtin(request_id)     # active AND builtin
3. exclude = { _normalize_tool_id(x) for x in (exclude_builtin_tool_ids or []) }
4. seen = { w.tool_id for w in existing_workers (worker_type=="tool") }
5. for entry in entries:
     storage_id = _normalize_tool_id(entry.tool_id)         # internal:x→x, mcp:s:t→mcp_s
     if storage_id in exclude or storage_id in seen: continue
     description = _resolve_builtin_description(storage_id)  # 헬퍼 추출 (40줄 규칙)
       # mcp_* → _resolve_mcp_description / internal → get_tool_meta
       # ValueError 시 warning 로그 후 None 반환 → 해당 도구만 continue
       #   (FR-07: MCP 비활성·레지스트리 이탈 잔재가 생성을 차단하면 안 됨)
     if description is None: continue
     seen.add(storage_id)                                    # 해석 성공 후 추가 — 빌트인 간
                                                             # 중복(동일 MCP 서버) 방지 (Check G3 정정)
     workers.append(WorkerDefinition(
         tool_id=storage_id, worker_id=f"{storage_id}_worker",
         description=description,
         sort_order=len(existing_workers) + len(workers),    # 기존 워커 뒤에 연속 배정
     ))
```

- **dedup 기준은 정규화(저장 형식) ID** — 사용자가 이미 선택한 도구(`internal:wiki_read` →
  `wiki_read`)와 빌트인이 중복 워커를 만들지 않는다. 동일 MCP 서버의 빌트인 도구 여러 개도
  `mcp_{srv}` 워커 1개로 병합(기존 D5 규약과 동일).
- **flow_hint 미포함**: flow_hint는 사용자 선택 도구의 순서 힌트 — 빌트인은 보조 도구로
  supervisor 워커 목록으로만 인지시킨다(기존 스켈레톤 flow_hint 무변경).
- `exclude_builtin_tool_ids`는 카탈로그 형식·저장 형식 모두 수용(`_normalize_tool_id` 통과).
- exclude에 있으나 빌트인이 아닌 ID는 무시(에러 아님 — 관리자가 빌트인을 해제한 직후의
  낡은 프론트 상태와의 경합을 무해화).

### 5.3 스키마·DI 변경

- `CreateAgentRequest.exclude_builtin_tool_ids: list[str] | None = None` (additive)
- `CreateAgentUseCase.__init__`에 `tool_catalog_repo: ToolCatalogRepositoryInterface | None = None`
  추가 (optional — 기존 테스트 무회귀, agent-memory 선례 패턴)
- `main.py`의 CreateAgentUseCase 조립 지점에 기존 세션의 `ToolCatalogRepository` 주입
  (**동일 세션 사용** — 한 UseCase 내 repository 세션 분리 금지 규칙)
- `CreateAgentResponse`는 무변경 — `workers`/`tool_ids`에 주입분이 자연 포함되어
  프론트가 저장 결과에서 빌트인 포함을 확인 가능

### 5.4 D6 — 상한 정책 확정 (FR-10)

- `AgentBuilderPolicy.validate_tool_count(len(skeleton.workers))` — **사용자 선택분만** (현행 호출 유지)
- `validate_worker_count(all_workers)` — 서브에이전트 경로도 **주입 전** 리스트로 검증 (호출 위치가 Step 2로 주입보다 앞이므로 코드 변경 없음)
- 결과 불변식: 저장되는 tool 워커 수 ≤ MAX_TOOLS(5) + 빌트인 수. 정책 클래스 수정 없음 —
  검증 시점만으로 달성. Design 근거: 빌트인은 플랫폼이 부여하는 표준 장비로 사용자 선택권
  5개를 잠식하면 안 됨

### 5.5 D7 — wiki_list 단독 워커 중복 점검 (Plan 이월)

- 폴더 모드에서 `WorkflowCompiler`가 wiki_read 워커에 wiki_list **도구**를 동봉하므로,
  wiki_list **워커**가 별도 존재하면 도구 레벨 중복이 생긴다 → **무해로 판정**:
  워커 이름은 `wiki_list_worker`로 유일(그래프 노드 충돌 없음), supervisor 라우팅 선택지가
  하나 늘어날 뿐이며 카테고리 미지정 react 경로로 정상 동작.
- 비폴더 모드(폴더 요약 off — 현재 기본)에서는 동봉이 없으므로 wiki_list 워커가
  폴더 탐색을 단독 제공 — 사용자 결정(둘 다 빌트인)이 유효한 시나리오.
- 운영 중 중복이 소음으로 판명되면 **관리자가 wiki_list 빌트인만 해제**하면 됨(코드 무변경)
  — 이 유연성이 본 기능의 목적과 정합.

---

## 6. 백엔드 테스트 설계 (TDD 순서)

| # | 테스트 파일 | 케이스 (Red 선행) |
|---|-------------|-------------------|
| T1 | `tests/db/test_migration_ddl_comments.py` | V054 COMMENT 검사 (기존 테스트가 자동 커버) |
| T2 | `tests/application/tool_catalog/test_sync_internal_tools_use_case.py` (기존 확장) | ① 신규 INSERT 시 builtin_default 반영(wiki 2종 True, 그 외 False) ② set_builtin(True) 후 재sync → 보존 ③ 관리자 해제 후 재sync → False 유지 |
| T3 | `tests/application/tool_catalog/test_set_builtin_use_case.py` (신규) | ① 정상 토글 ② 미존재 tool_id → ValueError ③ 비활성 도구 플래그 허용 |
| T4 | `tests/api/test_tool_catalog_router.py` (기존 확장) | ① GET 응답에 is_builtin 포함 ② PATCH admin 200 ③ 비관리자 403 |
| T5 | `tests/application/agent_builder/test_create_agent_builtin.py` (신규) | ① 미선택 시 wiki 2종 워커 주입 ② 사용자가 wiki_read 선택 시 중복 없음 ③ exclude 지정분 미주입(카탈로그/저장 형식 모두) ④ 사용자 도구 5개 + 빌트인 → 상한 통과 ⑤ MCP 빌트인 서버 비활성 → 제외+생성 성공 ⑥ tool_catalog_repo 미주입 → 주입 생략(무회귀) ⑦ flow_hint에 빌트인 미포함 |
| T6 | fake repo 갱신 | 테스트 fake들의 인터페이스 신메서드(set_builtin/list_builtin) 구현 |

> Windows 관례: 백엔드 pytest 격리 실행, 사전 실패분(tests/api 28건 등)은 회귀로 오인 금지.

---

## 7. 프론트엔드 설계 (idt_front)

### 7.1 D8 — 생성 폼: 전용 excluded 상태로 "수동 해제만" 보장

| 항목 | 설계 |
|------|------|
| 타입 | `CatalogTool.is_builtin: boolean` 추가 (`src/types/toolCatalog.ts`), `AgentBuilderFormData.excludedBuiltinTools: string[]` 추가(카탈로그 형식), `CreateBuilderAgentRequest.exclude_builtin_tool_ids?: string[]` (`src/types/agentBuilder.ts`) |
| ToolPickerModal | 빌트인 카드: `is_builtin && !excluded` → 선택 상태 + "기본" 배지(Tailwind 인라인 span 관례, violet 계열). 토글 시 `onToggleBuiltin(toolId)` **별도 콜백** → `excludedBuiltinTools` add/remove. 일반 도구 토글(`onToggle`)과 상태 경로 분리 |
| form.tools 불변식 | **빌트인은 form.tools에 넣지 않는다** — 표시는 카탈로그 `is_builtin` − `excludedBuiltinTools` 파생값. Fix 초안 적용(`handleApplyDraft`)이 form.tools를 전체 교체해도 빌트인 표시·전송에 영향 없음(채팅 우회 구조 차단의 프론트 절반) |
| 초안 적용 경합 | `mapDraftToolIdsToCatalog` 결과에 빌트인 카탈로그 ID가 포함되면 form.tools에서 필터링(중복 칩 방지 — 서버도 dedup하므로 이중 방어) |
| LeftConfigPanel | 선택 칩 목록에 빌트인 칩("기본" 배지 부착, 파생값) 추가 표시 |
| handleSave | create 분기 payload에 `exclude_builtin_tool_ids: form.excludedBuiltinTools` (빈 배열이면 생략) |
| edit 모드 | PUT이 tool_ids 미지원(기존 Out of Scope)이므로 빌트인 UI는 create 모드 전용. edit 진입 시 excluded 초기화 불필요. ToolPickerModal은 `onToggleBuiltin` 미전달 시 빌트인도 일반 도구로 취급(격하) — edit 모드에선 저장된 워커가 form.tools로 매핑되므로 일반 칩/카드로 동작 |

### 7.2 D9 — 관리자 도구 관리 화면

- **신규 `AdminToolsPage`** (`src/pages/AdminToolsPage/index.tsx`), 라우트 `/admin/tools` —
  `App.tsx`의 `AdminRoute > AdminLayout` 블록에 추가 + `ADMIN_NAV_ITEMS`(adminNav.ts) 항목 추가
  (기존 목업 `ToolAdminPage(/tool-admin)`는 무변경 — 별개 자리표시자).
- 구성: `useToolCatalog()` 재사용 목록 테이블(이름/소스 배지/설명/빌트인 — "활성"
  컬럼은 미표시: `GET /tool-catalog`가 active만 반환하고 응답에 `is_active`가 없어
  현 계약으론 불가·실익 없음, Check G2 정정) + 빌트인 스위치(`role="switch"` 패턴,
  SchedulePanel 선례). 토글 → 신규 `useSetToolBuiltin` mutation
  (`PATCH TOOL_CATALOG_BUILTIN`) → 성공 시 `queryKeys.toolCatalog.all` invalidate.
  이중 클릭 방어는 행 단위 `pendingToolId` 가드(같은 행 재클릭만 차단).
- 상수: `api.ts`에 `TOOL_CATALOG_BUILTIN: '/api/v1/tool-catalog/builtin'` 추가.
- 서비스: `toolCatalogService.setBuiltin(toolId, isBuiltin)` 추가.

### 7.3 프론트 테스트

| 파일 | 케이스 |
|------|--------|
| `ToolPickerModal.test.tsx` (확장) | 빌트인 카드 기본 선택+배지 / 해제 토글 → onToggleBuiltin 호출 / 일반 도구와 콜백 분리 |
| `AgentBuilderPage/index.test.tsx` (확장) | ① 빌트인 해제 후 저장 → payload에 exclude 포함 ② 미해제 저장 → exclude 생략 ③ Fix 초안 적용 → excludedBuiltinTools 불변 + form.tools에 빌트인 미혼입 |
| `AdminToolsPage/index.test.tsx` (신규) | 목록 렌더 / 토글 mutation 호출 / 실패 시 에러 표시. MSW 핸들러 + per-file server.listen 3종 훅, vitest --pool=threads 관례 |

---

## 8. 구현 순서

```
Phase A (백엔드 기반):  V054 + entity/models/ToolMeta → T1·T2 (sync 시드/보존)
Phase B (관리자 API):   set_builtin repo/UseCase/라우터/DI → T3·T4
Phase C (주입):         CreateAgentRequest 필드 + _build_builtin_workers → T5·T6
Phase D (프론트 계약):  types/service/hook/상수 동기화 (api-contract-sync)
Phase E (프론트 UI):    ToolPickerModal·LeftConfigPanel·handleSave → AdminToolsPage
Phase F (검증):         verify-architecture / verify-tdd / 격리 회귀 → E2E 수동 시나리오(Plan §8.2)
```

---

## 9. 리스크 재점검 (Plan §5 대비 확정 사항)

| Plan 리스크 | Design 해소 |
|-------------|-------------|
| sync가 플래그 덮어씀 | UPDATE 분기 현행 성질 유지 + T2 보존 계약 테스트 (D2) |
| 프레시 DB 시드 no-op | builtin_default INSERT 시드로 커버 (D1) |
| MCP 빌트인 장애 시 생성 실패 | try/except 격하 + warning 로그 (D5 §5.2) |
| 상한 초과 | 검증 시점 분리로 빌트인 상한 제외 (D6) |
| wiki_list 중복 | 무해 판정 + 관리자 해제 우회로 확보 (D7) |
| 채팅 초안이 빌트인 누락 표시 | 프론트 파생 표시(형태 무관) + 저장 응답 workers에 포함 (D8) |

**신규 식별 리스크**: `_normalize_tool_id`는 CreateAgentUseCase의 staticmethod — 주입 로직도
동일 메서드를 재사용해 정규화 규칙 분기를 방지한다(이중 네임스페이스 회귀 방어).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-01 | Initial draft — Plan 이월 4건(시드/상한/wiki_list/관리자 UI) 확정, 백엔드·프론트 실코드 조사 기반 | 배상규 |
| 0.2 | 2026-08-01 | Check G2/G3 정정(활성 컬럼 삭제·seen.add 시점·pendingToolId 가드) + §7.1 edit 모드 격하 동작 명시 — 코드가 진실 원칙 | 배상규 |
