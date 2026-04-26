# Design: agent-collection-visibility-sync

> Feature: 에이전트 생성 시 컬렉션 scope 기반 visibility 자동 상속
> Plan: `docs/01-plan/features/agent-collection-visibility-sync.plan.md`
> Created: 2026-04-26
> Status: Design

---

## 1. 설계 목표

에이전트의 `visibility`가 참조하는 컬렉션의 `scope`보다 넓을 수 없도록
**생성/수정 시점에 자동 상속** 규칙을 적용한다.

| 컬렉션 scope | → 에이전트 최대 visibility |
|---|---|
| `PERSONAL` | `private` |
| `DEPARTMENT` | `department` |
| `PUBLIC` | `public` |

복수 컬렉션 참조 시 **가장 제한적인 scope**가 상한이 된다.

---

## 2. 용어 매핑

현재 코드에서 에이전트와 컬렉션이 서로 다른 명명을 쓴다. 이 설계에서는 변환 규칙을 명시한다.

```
CollectionScope.PERSONAL   ↔  Visibility.PRIVATE     (rank 0)
CollectionScope.DEPARTMENT ↔  Visibility.DEPARTMENT   (rank 1)
CollectionScope.PUBLIC     ↔  Visibility.PUBLIC        (rank 2)
```

---

## 3. Domain Layer 변경

### 3.1 VisibilityPolicy 확장

**파일**: `src/domain/agent_builder/policies.py`

기존 `VisibilityPolicy` 클래스에 두 개의 static method를 추가한다.

```python
# --- 추가할 상수 ---
SCOPE_TO_VISIBILITY: dict[str, str] = {
    "PERSONAL": "private",
    "DEPARTMENT": "department",
    "PUBLIC": "public",
}

VISIBILITY_RANK: dict[str, int] = {
    "private": 0,
    "department": 1,
    "public": 2,
}


class VisibilityPolicy:
    # ... 기존 can_access, can_edit, can_delete 유지 ...

    @staticmethod
    def max_visibility_for_scopes(scopes: list[str]) -> str:
        """컬렉션 scope 목록 중 가장 제한적인 scope를 visibility로 변환.
        
        Args:
            scopes: CollectionScope 값 리스트 (예: ["PUBLIC", "DEPARTMENT"])
        
        Returns:
            최대 허용 visibility (예: "department")
        
        Raises:
            ValueError: scopes가 비어있거나 알 수 없는 scope 포함 시
        """

    @staticmethod
    def clamp_visibility(requested: str, scopes: list[str]) -> str:
        """요청된 visibility를 컬렉션 scope 상한으로 제한.
        
        requested가 max보다 넓으면 max로 조정, 아니면 그대로 반환.
        
        Args:
            requested: 사용자가 ���청한 visibility
            scopes: 참조 컬렉션들의 scope 리스트
        
        Returns:
            조정된 (또는 그대로인) visibility
        """
```

**로직 상세**:

```
max_visibility_for_scopes(["PUBLIC", "DEPARTMENT"]):
  → 각 scope를 visibility로 변환: ["public", "department"]
  → rank 최소값: min(2, 1) = 1
  → rank 1 = "department" 반환

clamp_visibility("public", ["PUBLIC", "DEPARTMENT"]):
  → max = "department" (rank 1)
  → requested = "public" (rank 2)
  → 2 > 1 이므로 → "department" 반환

clamp_visibility("private", ["PUBLIC"]):
  → max = "public" (rank 2)
  → requested = "private" (rank 0)
  → 0 <= 2 이므로 → "private" 그대로 반환
```

### 3.2 RAG 컬렉션 없는 에이전트 처리

RAG 도구를 사용하지 않는 에이전트는 컬렉션 참조가 없다.
이 경우 **visibility 제한 없이** 사용자가 요청한 값을 그대로 사용한다.

```
scopes가 빈 리스트 → clamp_visibility는 requested를 그대로 반환
```

---

## 4. Application Layer 변경

### 4.1 CreateAgentUseCase 수정

**파일**: `src/application/agent_builder/create_agent_use_case.py`

**변경 사항**: DI에 `CollectionPermissionRepositoryInterface` 추가, Step 2.5에 visibility 검증 삽입.

```
현재 흐름:
  Step 0: LLM 모델 결정
  Step 1: 도구 선택 + tool_configs 적용
  Step 2: Policy 검증 (tool_count, name)
  Step 3: 시스템 프롬프트 생성
  Step 4: AgentDefinition 저장

변경 후:
  Step 0: LLM 모델 결정
  Step 1: 도구 선택 + tool_configs 적용
  Step 2: Policy 검증 (tool_count, name)
  ★ Step 2.5: 컬렉션 scope ��회 → visibility 자동 조정
  Step 3: 시스템 프롬프트 생성
  Step 4: AgentDefinition 저장 (조정된 visibility 사용)
```

**Step 2.5 상세**:

```python
async def _resolve_visibility(
    self,
    request: CreateAgentRequest,
    workers: list[WorkerDefinition],
    request_id: str,
) -> str:
    """컬렉션 scope 기반으로 visibility를 자동 조정."""
    collection_names = self._extract_collection_names(workers)
    if not collection_names:
        return request.visibility

    scopes = await self._lookup_collection_scopes(
        collection_names, request_id
    )
    return VisibilityPolicy.clamp_visibility(
        request.visibility, scopes
    )
```

**컬렉션 이름 추출 로직**:

```python
@staticmethod
def _extract_collection_names(
    workers: list[WorkerDefinition],
) -> list[str]:
    """workers의 tool_config에서 collection_name 추출."""
    names: list[str] = []
    for w in workers:
        if w.tool_config and w.tool_config.get("collection_name"):
            names.append(w.tool_config["collection_name"])
    return names
```

**scope 조회 로직**:

```python
async def _lookup_collection_scopes(
    self,
    collection_names: list[str],
    request_id: str,
) -> list[str]:
    """컬렉션 이름 목록으로 scope 조회. permission 없는 컬렉션은 PERSONAL 취급."""
    scopes: list[str] = []
    for name in collection_names:
        perm = await self._perm_repo.find_by_collection_name(
            name, request_id
        )
        scopes.append(perm.scope.value if perm else "PERSONAL")
    return scopes
```

> **주의**: permission이 없는 컬렉션(레거시 데이터)은 가장 제한적인 `PERSONAL`로 간주한다. 안전한 기본값.

**DI 변경**:

```python
class CreateAgentUseCase:
    def __init__(
        self,
        tool_selector: ToolSelector,
        prompt_generator: PromptGenerator,
        repository: AgentDefinitionRepositoryInterface,
        llm_model_repository: LlmModelRepositoryInterface,
        perm_repo: CollectionPermissionRepositoryInterface,  # ★ 추가
        logger: LoggerInterface,
    ) -> None:
```

### 4.2 UpdateAgentUseCase 수정

**파일**: `src/application/agent_builder/update_agent_use_case.py`

현재 `UpdateAgentUseCase`��� visibility만 변경 가능하고 tool_config(컬렉션)는 변경하지 않는다.
따라서 **기존 에이전트의 workers에서 컬렉션을 추출**하여 검증한다.

```python
# visibility 변경 요청 시에만 검증
if request.visibility is not None:
    collection_names = self._extract_collection_names(agent.workers)
    if collection_names:
        scopes = await self._lookup_collection_scopes(
            collection_names, request_id
        )
        clamped = VisibilityPolicy.clamp_visibility(
            request.visibility, scopes
        )
        if clamped != request.visibility:
            raise ValueError(
                f"컬렉션 scope 제한으로 visibility를 "
                f"'{request.visibility}'로 설정할 수 없습니다. "
                f"최대 허용: '{clamped}'"
            )
```

> CreateAgent는 **자동 조정** (silent clamp), UpdateAgent는 **에러 반환** (explicit reject).
> 이유: 생성 시에는 UX 편의를 위해 자동 조정이 적절하고, 수정 시에는 기존 설정을 의도적으로 변경하는 것이므로 명시적 에러가 적절하다.

### 4.3 CreateAgentResponse 확장

**파일**: `src/application/agent_builder/schemas.py`

```python
class CreateAgentResponse(BaseModel):
    # ... 기존 필드 유지 ...
    visibility: str
    visibility_clamped: bool = False  # ★ 추가: 자동 조정 여부
    max_visibility: str | None = None  # ★ 추가: 컬렉션 기반 상한값
```

프론트엔드에서 `visibility_clamped == True`일 때 안내 메시지를 표시할 수 있다.

---

## 5. Infrastructure Layer 변경

### 5.1 rag_tool_router 권한 필터 + scope 추가

**파일**: `src/api/routes/rag_tool_router.py`

**변경 1**: `CollectionInfo` 응답에 `scope` 필드 추가

```python
class CollectionInfo(BaseModel):
    name: str
    display_name: str
    vectors_count: int | None = None
    scope: str | None = None  # ★ 추가: "PERSONAL" | "DEPARTMENT" | "PUBLIC"
```

**변경 2**: `list_collections` 엔드포인트에 권한 필터 적용

```python
@router.get("/collections", response_model=CollectionsResponse)
async def list_collections(
    current_user: User = Depends(get_current_user),       # ★ 추가
    qdrant_client=Depends(get_qdrant_client),
    aliases: dict = Depends(get_collection_aliases),
    perm_service=Depends(get_collection_permission_service),  # ★ 추가
):
    request_id = str(uuid.uuid4())
    result = await qdrant_client.get_collections()

    # 접근 가능한 컬렉�� 필터링
    accessible = await perm_service.get_accessible_collection_names(
        current_user, request_id
    )
    is_admin = current_user.role == UserRole.ADMIN

    collections = []
    for c in result.collections:
        # admin이면 전체, 아니면 accessible에 포함된 것만
        if not is_admin and accessible and c.name not in accessible:
            continue
        # scope 조회
        perm = await perm_service.find_permission(c.name, request_id)
        collections.append(
            CollectionInfo(
                name=c.name,
                display_name=aliases.get(c.name, c.name),
                vectors_count=getattr(c, "vectors_count", None),
                scope=perm.scope.value if perm else None,
            )
        )

    return CollectionsResponse(collections=collections)
```

**DI 추가 필요**:
- `get_current_user` (기존 `src/interfaces/dependencies/auth.py`)
- `get_collection_permission_service` (신규 DI 플레이스홀더, `main.py`에서 override)

### 5.2 main.py DI 연결

**파일**: `src/api/main.py`

```python
# CreateAgentUseCase에 perm_repo 주입
# rag_tool_router에 perm_service DI override
```

기존 DI 패턴(Depends override)을 따라 `main.py`에서 연결한다.

---

## 6. API 계약 ��경

### 6.1 GET /api/v1/rag-tools/collections

**Before**:
```json
{
  "collections": [
    { "name": "documents", "display_name": "문서", "vectors_count": 1523 }
  ]
}
```

**After**:
```json
{
  "collections": [
    { "name": "documents", "display_name": "문서", "vectors_count": 1523, "scope": "PUBLIC" }
  ]
}
```

- `scope` 필드 추가 (nullable — permission 미등록 컬렉션은 null)
- 권한 필터 적���으로 접근 불가 컬렉션은 목록에서 제외
- 하위 호환: 기존 필드 유지, scope는 optional 추가

### 6.2 POST /api/v1/agents (CreateAgent)

**Request**: 변경 없음 (기존 `visibility` 필드 그대로 사용)

**Response 추가 필드**:
```json
{
  "visibility": "department",
  "visibility_clamped": true,
  "max_visibility": "department"
}
```

### 6.3 PATCH /api/v1/agents/{id} (UpdateAgent)

**변경 없음**. visibility가 컬렉션 scope 상한을 초과하면 `400 Bad Request`:

```json
{
  "detail": "컬렉션 scope 제한으로 visibility를 'public'로 설정할 수 없습니다. 최대 허용: 'department'"
}
```

---

## 7. Frontend 변경

### 7.1 타입 업데이트

**파일**: `idt_front/src/types/ragToolConfig.ts`

```typescript
interface CollectionInfo {
  name: string;
  display_name: string;
  vectors_count?: number;
  scope?: 'PERSONAL' | 'DEPARTMENT' | 'PUBLIC';  // ★ 추가
}
```

### 7.2 RagConfigPanel 컬렉션 선택 UI

**파일**: `idt_front/src/components/agent-builder/RagConfigPanel.tsx`

컬렉션 드롭다운 옵션에 scope 뱃지를 추가한다:

```
┌──────────────────────────────────────────┐
│ 컬렉션 선택                  ▼          │
├��─────────────────────────────────���───────┤
│ 금리보고서     [개인]    1,523 vectors  │
│ 정책자료       [부서]      452 vectors  │
│ 공개문서       [공개]      891 vectors  │
└────��────���────────────────────────────────┘
```

scope 뱃지 색상은 기존 `SCOPE_LABELS` 재사용:
- `PERSONAL` → 보라색 "개인"
- `DEPARTMENT` → 파란색 "부서"
- `PUBLIC` → 초록색 "공개"

### 7.3 AgentBuilderPage visibility 연동

**파일**: `idt_front/src/pages/AgentBuilderPage/index.tsx`

현재 프론트엔드에는 **에이전트 visibility 선택 UI가 없다** (mock 데이터만 존재).
따라서 이번 설계에서는:

1. 백엔드에서 `clamp_visibility`를 수행하므로, 프론트에서 별도 visibility 드롭다운 없이도 안전
2. `CreateAgentResponse`의 `visibility_clamped`가 `true`이면 toast로 안내:
   > "선택한 컬렉션이 [개인/부서]용이므로 에이전트 공개 범위가 자동 조정되었습니다."

**향후 확장**: visibility 드롭다운 UI 추가 시, 선택된 컬렉션의 scope에 따라 옵션 비활성화.

---

## 8. Sequence Diagram

### 8.1 에이전트 생성 (CreateAgent)

```
Frontend                    Router              CreateAgentUseCase          PermRepo
  │                           │                        │                       │
  ├──POST /agents─────────────►                        │                       │
  │  {visibility:"public",    │                        │                       │
  │   tool_configs:{RAG:{     ├──execute()──────────────►                       │
  │     collection_name:      │                        │                       │
  │     "my-docs"}}}          │                        ├──_extract_collection   │
  │                           │                        │  _names(workers)       │
  │                           │                        │  → ["my-docs"]         │
  │                           │                        │                       │
  │                           │                        ├──find_by_collection    │
  │                           │                        │  _name("my-docs")─────►
  │                           │                        │                       │
  │                           │                        │◄──{scope: "PERSONAL"}──┤
  │                           │                        │                       │
  │                           │                        ├──clamp_visibility      │
  │                           │                        │  ("public",["PERSONAL"])│
  │                           │                        │  → "private"           │
  │                           │                        │                       │
  │                           │                        ├──save(AgentDefinition  │
  │                           │                        │  {visibility:"private"})│
  │                           │                        │                       │
  │◄──{visibility:"private",──┤◄──────────���──────────┤                       │
  │    visibility_clamped:    │                        │                       │
  │    true,                  │                        │                       │
  │    max_visibility:        │                        │                       │
  │    "private"}             │                        │                       │
```

### 8.2 컬렉션 목록 조회 (with 권한 필터)

```
Frontend                    rag_tool_router        PermService            PermRepo
  │                           │                        │                       │
  ├──GET /rag-tools/          │                        │                       │
  │  collections──────────────►                        │                       │
  │                           ├──get_accessible_       │                       │
  │                           │  collection_names()────►                       │
  ���                           │                        ├──find_accessible()────►
  │                           │                        │◄─[perm1, perm2]───────┤
  │                           │◄──{"my-docs","pub"}────┤                       │
  │                           │                        │                       │
  │                           ├──qdrant.get_           │                       │
  │                           │  collections()         │                       │
  │                           │  → [my-docs,pub,other] │                       │
  ��                           │                        │                       │
  │                           ├──filter: accessible    │                       │
  │                           │  → [my-docs, pub]      │                       │
  │                           │                        │                       │
  │                           ├──find_permission()     │                       │
  │                           │  per collection────────►                       │
  │                           │◄──scope per coll───────┤                       │
  │                           │                        │                       │
  │◄──{collections:[          │                        │                       │
  │    {name:"my-docs",       │                        │                       │
  │     scope:"PERSONAL"},    │                        │                       │
  │    {name:"pub",           │                        │                       │
  │     scope:"PUBLIC"}]}─────┤                        │                       │
```

---

## 9. 에러 처리

| 시나리오 | 위치 | 처리 |
|----------|------|------|
| 컬렉션 permission 미등록 | `_lookup_collection_scopes` | `PERSONAL`로 간주 (안전한 기본값) |
| scopes 빈 리스트 (RAG 미사용) | `clamp_visibility` | requested 그대로 반환 |
| 알 수 없는 scope 값 | `max_visibility_for_scopes` | `ValueError` raise |
| Update 시 scope 초과 | `UpdateAgentUseCase` | `ValueError` → 400 Bad Request |
| PermRepo DB 에러 | UseCase | 기존 에러 핸들링 (로깅 + raise) |

---

## 10. 구현 파일 목록

### 수정 대상

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `src/domain/agent_builder/policies.py` | `SCOPE_TO_VISIBILITY`, `VISIBILITY_RANK` 상수, `max_visibility_for_scopes()`, `clamp_visibility()` 추가 |
| 2 | `src/application/agent_builder/create_agent_use_case.py` | DI에 `perm_repo` 추가, `_resolve_visibility()`, `_extract_collection_names()`, `_lookup_collection_scopes()` 추가, Step 2.5 삽입 |
| 3 | `src/application/agent_builder/update_agent_use_case.py` | DI에 `perm_repo` 추가, visibility 변경 시 scope 검증 |
| 4 | `src/application/agent_builder/schemas.py` | `CreateAgentResponse`에 `visibility_clamped`, `max_visibility` 필드 추가 |
| 5 | `src/api/routes/rag_tool_router.py` | `CollectionInfo.scope` 추가, `list_collections`에 권한 필터 + scope 조회 |
| 6 | `src/api/main.py` | DI 연결 (CreateAgentUseCase → perm_repo, rag_tool_router → perm_service) |
| 7 | `idt_front/src/types/ragToolConfig.ts` | `CollectionInfo.scope` 추가 |
| 8 | `idt_front/src/components/agent-builder/RagConfigPanel.tsx` | scope 뱃지 표시 |
| 9 | `idt_front/src/pages/AgentBuilderPage/index.tsx` | visibility_clamped 시 toast 안내 |

### 테스트 파일

| # | 파일 | 테스트 내용 |
|---|------|------------|
| T1 | `tests/domain/agent_builder/test_visibility_policy.py` | `max_visibility_for_scopes`, `clamp_visibility` 단위 테스트 |
| T2 | `tests/application/agent_builder/test_create_agent_use_case.py` | scope 기반 visibility 자동 조정 통합 테스트 |
| T3 | `tests/application/agent_builder/test_update_agent_use_case.py` | visibility 초과 시 에러 반환 테스트 |
| T4 | `tests/api/routes/test_rag_tool_router.py` | 컬렉션 권한 필터링 + scope 포함 테스트 |
| T5 | `idt_front/src/components/agent-builder/RagConfigPanel.test.tsx` | scope 뱃지 렌더링 테스트 |

---

## 11. 구현 순서

```
[T1] test_visibility_policy.py (RED)
  ↓
[1] policies.py — max_visibility_for_scopes, clamp_visibility (GREEN)
  ↓
[T2] test_create_agent_use_case.py (RED)
  ↓
[2] create_agent_use_case.py — DI + _resolve_visibility (GREEN)
[4] schemas.py — visibility_clamped, max_visibility 추가
[6] main.py — DI 연결
  ↓
[T3] test_update_agent_use_case.py (RED)
  ↓
[3] update_agent_use_case.py — scope 검증 (GREEN)
  ↓
[T4] test_rag_tool_router.py (RED)
  ↓
[5] rag_tool_router.py — 권한 필터 + scope (GREEN)
[6] main.py — rag_tool_router DI 연결
  ↓
[7] ragToolConfig.ts — CollectionInfo.scope 타입
[8] RagConfigPanel.tsx — scope 뱃지
[9] AgentBuilderPage — toast 안내
  ↓
[T5] RagConfigPanel.test.tsx
  ↓
브라우저 통합 테스트
```

---

## 12. CLAUDE.md 규칙 준수

| 규칙 | 준수 |
|------|------|
| domain → infrastructure 참조 금지 | ✅ VisibilityPolicy는 순수 문자열만 처리 |
| router에 비즈니스 로직 금지 | ✅ rag_tool_router는 PermService 호출만, 로직은 Policy/Service에 |
| TDD 필수 | ✅ 각 단계 RED → GREEN 순서 명시 |
| 함수 40줄 미만 | ✅ 각 메서드 10줄 이내 |
| API 계약 동기화 | ✅ CollectionInfo.scope 백엔드↔프론트 동시 수정 |
| Repository 내부 commit/rollback 금지 | ✅ find_by_collection_name은 조회만 |
| print() 금지, logger 사용 | ✅ 기존 logger 패턴 유지 |

---

## 13. 다음 단계

1. [ ] Do phase 시작 (`/pdca do agent-collection-visibility-sync`)
2. [ ] TDD 순서대로 구현
3. [ ] 브라우저 통합 테스트
