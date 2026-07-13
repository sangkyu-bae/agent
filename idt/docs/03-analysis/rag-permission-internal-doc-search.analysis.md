# Analysis: 내부문서 검색(VectorDB) 접근권한 처리 구조

> Analyzed: 2026-07-06
> Phase: Analysis (코드 구조 분석 — 설계 갭 검증 아님)
> Scope: 에이전트 실행 시 내부문서 하이브리드 검색(ES + Qdrant)의 권한 검증·필터링 경로
> Related Design: agent-user-context (§3.1~§7.2)

---

## 1. 요약

에이전트가 내부문서 DB(Qdrant + Elasticsearch)를 검색할 때 "권한이 없으면 없다고 처리"하는
동작은 단일 지점이 아니라 **3중 방어(Defense in Depth)** 구조로 구현되어 있다.
실제 "없다" 응답이 만들어지는 지점은 `InternalDocumentSearchTool._arun()` 내부의 두 곳이다.

| 단계 | 조건 | 결과 |
|------|------|------|
| 1차 차단 | `USE_RAG_SEARCH` 권한 없음 | 검색 미실행, `"RAG 검색 권한이 없습니다."` 반환 |
| 2차 필터 | `READ_DEPARTMENT_DOCS` 유무에 따라 metadata_filter 강제 보강 | 매칭 0건 시 `"관련 내부 문서를 찾지 못했습니다."` 반환 |
| 3차 방어 | Repository가 필터를 ES/Qdrant 쿼리 조건으로 적용 | 필터 밖 문서는 검색 자체에서 배제 |

DB에 별도의 "권한 검사 쿼리"가 있는 것이 아니라, **도구가 AuthContext를 보고 스스로 거부하거나
검색 필터를 조이는 방식**이다. LLM은 도구가 반환한 거부/미발견 문자열을 관찰하고
"접근 권한이 없다 / 문서가 없다"고 답변하게 된다.

---

## 2. 전체 흐름 (요청 → 거부/축소까지)

### 2-1. AuthContext 조립 (요청당 1회)

- `src/application/permission/assemble_auth_context.py` — `AssembleAuthContextUseCase`가
  User를 받아 DB 3회 조회(프로필, 부서, 권한)로 `AuthContext`를 조립한다.
- 권한 해석: `src/domain/permission/resolver.py:16` — `PermissionResolver.resolve()`가
  **role 기본 권한 ∪ 사용자 개별 grant** 합집합(frozenset)을 만든다.
- 권한 코드 정의: `src/domain/permission/value_objects.py` — `USE_RAG_SEARCH`,
  `READ_DEPARTMENT_DOCS` 등 8종 (단일 진실 공급원).
- DB 시드: `db/migration/V029__seed_permissions.sql` — **user/admin role 모두
  `USE_RAG_SEARCH` + `READ_DEPARTMENT_DOCS`를 기본 보유**한다.
- `AuthContext`(`src/domain/agent_run/auth_context.py`)는 frozen dataclass이며,
  `has(code)`가 모든 권한 체크의 단일 진입점이다.
  - `AuthContext.public_anonymous()` — auth 누락 시 안전 디폴트(Fail-Closed).
    `permissions=frozenset()`이므로 어떤 권한 체크도 통과하지 못한다.

### 2-2. 에이전트 실행 경로로 전파

```
router (Depends(get_auth_context))
  → RunAgentUseCase.stream(auth_ctx=...)
      ├─ set_current_auth_context(auth_ctx)      # ContextVar 세팅 (finally에서 reset)
      └─ WorkflowCompiler.compile(auth_ctx=...)
          ├─ tool_factory.bind_auth_ctx(auth_ctx) # ToolFactory에 주입
          │    └─ create("internal_document_search") → Tool에 auth_ctx 명시 주입
          └─ sub-agent 재귀 compile에도 auth_ctx 그대로 전달 (수퍼바이저 구조)
```

- 라우터: `src/api/routes/agent_builder_router.py:281` — `auth_ctx: AuthContext = Depends(get_auth_context)`
  로 받아 use case에 키워드 전용 인자로 전달.
- ContextVar: `src/application/agent_run/auth_context.py` — RunContext(관측성)와 분리된
  비즈니스 컨텍스트. graph 밖에서 실행되는 Tool이 fallback으로 조회한다.
  `RunAgentUseCase.stream()`(`run_agent_use_case.py:214`)에서 세팅, finally에서 reset.
- ToolFactory: `src/infrastructure/agent_builder/tool_factory.py:96` —
  `InternalDocumentSearchTool(auth_ctx=self._auth_ctx, ...)` 명시 주입.
- 수퍼바이저(수퍼에이전트): `src/application/agent_builder/workflow_compiler.py:486` —
  sub-agent 재귀 compile 시 `auth_ctx`를 그대로 넘기므로 하위 워커의 RAG 도구도
  동일한 사용자 권한으로 동작한다. supervisor 프롬프트 앞에는
  `render_user_context_block(auth_ctx)`가 prepend된다 (`include_user_context=False`면 생략).

### 2-3. 도구 내부의 권한 처리 — `src/application/rag_agent/tools.py`

```python
# tools.py:74 — 컨텍스트 해석 순서 (Defense in Depth)
def _resolve_auth_ctx(self) -> AuthContext:
    if isinstance(self.auth_ctx, AuthContext):   # 1) 명시 주입 (ToolFactory)
        return self.auth_ctx
    from_var = get_current_auth_context()        # 2) ContextVar fallback
    if from_var is not None:
        return from_var
    return AuthContext.public_anonymous()        # 3) Fail-Closed 디폴트

# tools.py:122 — ★ 1차 차단: 검색 자체를 실행하지 않는다
if not ctx.has(PermissionCode.USE_RAG_SEARCH.value):
    return _RAG_DENIED_MSG                       # "RAG 검색 권한이 없습니다."

# tools.py:96 — ★ 2차 필터: 권한에 따라 metadata_filter 강제 보강
def _apply_auth_filter(self, ctx, base_filter):
    eff = dict(base_filter)
    if not ctx.has(PermissionCode.READ_DEPARTMENT_DOCS.value):
        eff["visibility"] = "public"                              # 공개 문서만
    else:
        eff["viewer_department_ids"] = ",".join(ctx.department_ids)
    return eff
```

- 스케줄 실행·스크립트 등 **인증 없는 호출 경로**는 `public_anonymous()`로 떨어지고,
  권한 집합이 비어 있어 1차 차단에서 자동 거부된다.
- 검색이 실행되었으나 결과 0건이면 `"관련 내부 문서를 찾지 못했습니다."` 반환
  (`tools.py:148`, `tools.py:178`).
- `metadata_filter`는 Pydantic 필드라 직접 변경하지 않고, `_arun` 시점에
  `_effective_metadata_filter`로 합성해 사용한다 (`tools.py:128`).

### 2-4. 3차 방어 (Repository 레벨)

보강된 `metadata_filter`의 **모든 키**가 exact-match 조건으로 그대로 적용된다.

- ES: `src/application/hybrid_search/use_case.py:100-108` —
  `{"term": {key: value}}` filter clause로 변환.
- Qdrant: `src/infrastructure/vector/qdrant_vectorstore.py:171-174` —
  `FieldCondition(key=key, match=MatchValue(value=value))`, `Filter(must=...)`.

---

## 3. ⚠️ 발견 이슈 — 2차 필터가 의도보다 과하게 작동할 가능성

### 3-1. 현상

설계 주석(`tools.py:110-111`)은 "`viewer_department_ids`는 **Repository 미지원 시 무시**된다"고
가정하지만, 실제 `HybridSearchUseCase`는 metadata_filter의 모든 키를 필터 조건으로
그대로 적용한다 (무시하는 로직 없음).

인제스트 경로(`advanced_ingest`, `unified_upload`, `infrastructure/pipeline/`)를 확인한 결과
**문서 payload에 `visibility`도 `viewer_department_ids`도 저장하지 않는다.**

### 3-2. 영향

| 사용자 | 주입되는 필터 | 예상 결과 |
|--------|--------------|-----------|
| `READ_DEPARTMENT_DOCS` 보유 (= V029 시드상 모든 user/admin) | `viewer_department_ids="dept1,dept2"` | 존재하지 않는 payload 필드에 대한 exact-match → **ES/Qdrant 모두 0건** → 항상 "관련 내부 문서를 찾지 못했습니다" |
| 권한 미보유 | `visibility="public"` | 문서에 `visibility` 필드가 없으면 동일하게 0건 |

즉 현재 "권한 없으면 없다고 처리"로 보이는 동작은:

1. **① 명시적 거부 메시지** (1차 차단 — 의도된 동작)
2. **② 필터가 어떤 문서와도 매칭되지 않아 0건이 되는 효과** (2차 필터 — 의도보다 과함,
   권한 있는 사용자도 못 찾게 됨)

두 가지가 섞여 있을 가능성이 크다.

관련 테스트(`tests/application/rag_agent/test_internal_document_search_auth.py:83`)는
필터가 **주입되는지**만 검증하고, 주입된 필터가 실제 검색에서 어떤 결과를 내는지는
mock이라 검증하지 못한다.

### 3-3. 권장 조치 (후속 작업 후보)

1. **운영 Qdrant payload 확인** — 실제 색인 문서에 `visibility` /
   `viewer_department_ids` 필드가 존재하는지 샘플 조회로 진단.
2. 필드가 없다면 둘 중 하나:
   - (a) 인제스트 시 `visibility` / 부서 필드를 payload·ES 매핑에 저장하고,
     Repository에서 `viewer_department_ids`를 OR(should/MatchAny) 조건으로 처리
     (설계 §7.2가 원래 의도한 방향).
   - (b) Repository가 지원할 때까지 `_apply_auth_filter`에서
     `viewer_department_ids` 주입을 제거 (visibility 필터도 색인 필드 추가 전까지 보류).
3. 어느 쪽이든 통합 수준 테스트(실제 필터 → 검색 결과)로 회귀 방지.

---

## 4. 참조 파일 맵

| 역할 | 파일 |
|------|------|
| 권한 코드 enum | `src/domain/permission/value_objects.py` |
| 권한 합성 정책 | `src/domain/permission/resolver.py` |
| AuthContext VO (Fail-Closed) | `src/domain/agent_run/auth_context.py` |
| AuthContext 조립 UseCase | `src/application/permission/assemble_auth_context.py` |
| AuthContext ContextVar | `src/application/agent_run/auth_context.py` |
| 실행 진입 라우터 | `src/api/routes/agent_builder_router.py` |
| 실행 UseCase (ContextVar 세팅) | `src/application/agent_builder/run_agent_use_case.py` |
| 컴파일러 (auth_ctx 전파) | `src/application/agent_builder/workflow_compiler.py` |
| ToolFactory (도구 주입) | `src/infrastructure/agent_builder/tool_factory.py` |
| **RAG 검색 도구 (1·2차 방어)** | `src/application/rag_agent/tools.py` |
| 하이브리드 검색 (3차 — ES 필터) | `src/application/hybrid_search/use_case.py` |
| Qdrant 벡터스토어 (3차 — 벡터 필터) | `src/infrastructure/vector/qdrant_vectorstore.py` |
| 권한 시드 | `db/migration/V029__seed_permissions.sql` |
| 권한 주입 테스트 | `tests/application/rag_agent/test_internal_document_search_auth.py` |
