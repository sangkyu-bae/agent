# RAG Auth Filter Fix Design Document

> **Summary**: 권한 필터 키 3분류(hard/lenient/ignored)로 검색 0건 해소 + 검색 파이프라인 사용자 컨텍스트 주입 + tool_name 폴백·0건 경고 로그·BM25 컬렉션 격리 상세 설계
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-22
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/rag-auth-filter-fix.plan.md`

---

## 1. Design Overview

모든 변경은 **additive** — 신규 API·DB 마이그레이션·프론트 변경 0. 기존 필드/시그니처는 기본값 있는 파라미터 추가만 허용한다.

| Scope | 대상 파일 | 변경 성격 |
|-------|----------|----------|
| S1·S2 (필터 3분류) | `application/rag_agent/tools.py` | 키 분류 상수 + `_hybrid_filters()` 신설, 요청 구성 변경 |
| S2 (lenient 표현) | `domain/hybrid_search/schemas.py`, `domain/vector/value_objects.py` | frozen dataclass에 기본값 있는 필드 추가 |
| S2 (변환) | `application/hybrid_search/use_case.py`, `infrastructure/vector/qdrant_vectorstore.py` | lenient → ES bool·Qdrant should+IsEmpty 변환 |
| S2 (multi-query 경유) | `application/multi_query/use_case.py`, `workflow.py` | `lenient_filter` 옵션 파라미터 passthrough |
| S3 (경고 로그) | `application/rag_agent/tools.py` | 0건 + 주입 키 존재 시 warning |
| S4 (tool_name 폴백) | `domain/agent_builder/rag_tool_config.py`, `infrastructure/agent_builder/tool_factory.py` | `fallback` 파라미터 추가 |
| S5 (BM25 격리) | `application/hybrid_search/use_case.py` | `collection_name` term 필터 (opt-in) |
| S6 (사용자 컨텍스트) | `application/agent_builder/search_pipeline.py`, `workflow_compiler.py` | `user_context_block` 파라미터 배선 + 프롬프트 규칙 |

**실측 근거 확정 사실** (설계 전제):
- ES `documents` 인덱스 매핑: `collection_name`=keyword(term 가능), `visibility`=매핑 자체 없음(전 문서 필드 부재), `kb_id`=text+keyword 서브필드
- Qdrant 페이로드: `visibility`/`viewer_department_ids` 필드 부재, `collection_name`/`kb_id`는 존재
- multi_query 경로도 최종적으로 `HybridSearchRequest`로 수렴 (`multi_query/workflow.py:139-144`)

---

## 2. S1·S2 — 권한 필터 키 3분류 (D1)

### 2.1 결정: routed 경로 선례(키 3분류)를 hybrid 경로에 일반화

`tools.py`의 routed 상수(`_ROUTED_SCOPE_KEYS`/`_ROUTED_IGNORED_KEYS`) 옆에 hybrid용 분류 추가:

```python
# rag-auth-filter-fix D1: hybrid 경로 필터 키 3분류.
# ignored — 색인 페이로드에 없어 must 적용 시 전멸하는 키. 검색에 미적용.
#   (원 주석 "Repository 미지원 시 무시"의 의도를 코드로 실현)
# lenient — 보안 의미는 유지하되 "값 일치 OR 필드 부재" 완화 매칭.
#   후속 rag-auth-payload-indexing에서 색인 시 자연 엄격화.
_HYBRID_IGNORED_KEYS = frozenset({"viewer_department_ids"})
_HYBRID_LENIENT_KEYS = frozenset({"visibility"})
```

### 2.2 `_hybrid_filters()` 신설 — hard/lenient 분리

```python
def _hybrid_filters(self) -> tuple[dict[str, str], dict[str, str]]:
    """effective filter → (hard, lenient). ignored 키는 버린다."""
    hard, lenient = {}, {}
    for key, value in self._get_effective_filter().items():
        if key in _HYBRID_IGNORED_KEYS:
            continue
        if key in _HYBRID_LENIENT_KEYS:
            lenient[key] = value
        else:
            hard[key] = value
    return hard, lenient
```

- `_effective_metadata_filter`(auth 주입 결과)는 **그대로 유지** — routed 분류·로그·후속 실효화의 단일 소스
- `_single_query_search`: `HybridSearchRequest(metadata_filter=hard, lenient_filter=lenient, ...)`
- `_multi_query_search`: `multi_query_use_case.execute(..., metadata_filter=hard or None, lenient_filter=lenient or None)`
- routed 경로(`_routed_scope`)는 **무변경** — visibility 존재 시 기존대로 강등(legacy 경로가 이제 정상 동작하므로 강등 결과도 복구됨)

### 2.3 스키마 확장 (additive, 기본값 보장 하위호환)

```python
# domain/hybrid_search/schemas.py — HybridSearchRequest
lenient_filter: dict[str, str] = field(default_factory=dict)
# "key == value OR key 필드 부재" 완화 매칭 (rag-auth-filter-fix D1)

# domain/vector/value_objects.py — SearchFilter
metadata_lenient: Dict[str, str] = field(default_factory=dict)
# is_empty()에 len(self.metadata_lenient) == 0 조건 추가
```

### 2.4 Qdrant 변환 (`_build_qdrant_filter`)

키별 중첩 Filter로 표현 — 키가 늘어도 키 간 AND, 키 내 OR 의미 보존:

```python
for key, value in search_filter.metadata_lenient.items():
    conditions.append(
        models.Filter(should=[
            models.FieldCondition(key=key, match=models.MatchValue(value=value)),
            models.IsEmptyCondition(is_empty=models.PayloadField(key=key)),
        ])
    )
```

- qdrant-client `Condition` union에 `Filter`/`IsEmptyCondition` 포함 — 중첩 허용 확인됨
- `IsEmptyCondition`은 "필드 부재 OR null OR 빈 배열" 매칭 → 완화 의미와 정확히 일치
- `_fetch_vector`(use_case)에서 `SearchFilter(metadata=request.metadata_filter, metadata_lenient=request.lenient_filter)` 구성. **필터 구성 조건을 `if request.metadata_filter or request.lenient_filter`로 확장** (기존은 metadata_filter만 검사)

### 2.5 ES 변환 (`_fetch_bm25`)

lenient 키당 bool should 절을 filter 목록에 추가:

```python
for key, value in request.lenient_filter.items():
    filter_clauses.append({
        "bool": {
            "should": [
                {"term": {key: value}},
                {"bool": {"must_not": [{"exists": {"field": key}}]}},
            ],
            "minimum_should_match": 1,
        }
    })
```

- `visibility`는 현재 매핑 자체가 없음 → `exists`=false로 전 문서 통과 (검증 완료 전제)
- bool 래핑 조건: `metadata_filter or lenient_filter or collection_name` 중 하나라도 있으면 `bool.must+filter` 구조 사용

---

## 3. S3 — 0건 강등 경고 로그 (D2)

위치: `tools.py._single_query_search`/`_multi_query_search`의 빈 결과 분기 (기존 `"관련 내부 문서를 찾지 못했습니다."` 반환 직전).

```python
def _log_empty_with_auth_filter(self, query: str, mode: str) -> None:
    injected = sorted(set(self._get_effective_filter()) - set(self.metadata_filter))
    if self.logger is None or not injected:
        return
    self.logger.warning(
        "Internal search empty with auth-injected filter",
        request_id=self.request_id,
        mode=mode,                      # "single" | "multi_query"
        query=query[:100],
        injected_keys=injected,          # 예: ["viewer_department_ids"]
        hard_filter=..., lenient_filter=...,
    )
```

- injected 키 산출 = effective − 원본 `metadata_filter` (auth가 주입한 키만 정확히 식별)
- LOG-001 준수: structured 키워드 인자 + request_id, 예외 아님(warning)

---

## 4. S4 — tool_name sanitize 폴백 (D3)

```python
# domain/agent_builder/rag_tool_config.py
def sanitize_tool_name(name: str, fallback: str = "unnamed_tool") -> str:
    ...
    return sanitized.strip("_") or fallback

# infrastructure/agent_builder/tool_factory.py:94
name=sanitize_tool_name(rag_config.tool_name, fallback="internal_document_search"),
```

- 기본값 `"unnamed_tool"` 유지 → 기존 호출부·테스트 무영향 (additive)
- ToolFactory만 의미 있는 폴백 지정 → LLM 노출 이름·`ai_tool_call.tool_name` 기록 동시 정상화
- MCP 쪽 `MCPConnectionPolicy.sanitize_tool_name`(별개 함수)은 범위 외

---

## 5. S5 — BM25 컬렉션 격리 (D4)

`_fetch_bm25`에서 opt-in term 필터:

```python
if request.collection_name:
    filter_clauses.append({"term": {"collection_name": request.collection_name}})
```

- ES 매핑 `collection_name`=keyword 확정 → term 정확 일치 동작
- `collection_name` 미지정 요청(전역 검색 사용처)은 **기존 동작 그대로** — 회귀 0
- 주의: 구(舊) 색인 문서 중 `collection_name` 필드가 없는 ES 문서는 필터 시 제외됨 — 대상 KB 검색이라는 의미상 올바른 방향이며, Qdrant 축(컬렉션 물리 격리)과 대칭이 됨

---

## 6. S6 — 검색 파이프라인 사용자 컨텍스트 주입 (D5)

### 6.1 배선: 파라미터 방식 (ContextVar 아님)

supervisor prepend와 동일한 게이팅(`include_user_context`)을 지키기 위해 **compile 시점에 렌더된 블록을 파라미터로 전달**한다 (analysis 노드의 ContextVar 방식과 달리 게이트 필요):

```python
# workflow_compiler.py compile() — 기존 block 계산(169-173행) 재사용
user_block = ""
if include_user_context:
    user_block = render_user_context_block(auth_ctx)   # 기존 계산과 통합

# create_search_pipeline_node 호출부(242행)에 추가
worker_map[...] = create_search_pipeline_node(
    ..., user_context_block=user_block,
)
```

### 6.2 search_pipeline: 3단계 LLM 모두 주입

rewrite뿐 아니라 **validate/compress에도 주입**한다. 근거: 쿼리에 "배상규"가 들어가면 검색 결과도 배상규 데이터인데, validate가 "나의 질문 ↔ 배상규 결과"의 동일성을 모르면 관련성 오판 → 불필요 재검색 루프. compress도 본인 행 보존 판단에 이름 문맥 필요.

```python
def create_search_pipeline_node(
    worker_id, tool, pipeline_llm, policy, logger,
    user_context_block: str = "",          # 신규 — 기본값으로 하위호환
):
    ...
    # 각 단계 호출 시 system prompt에 prepend:
    system = user_context_block + REWRITE_SYSTEM_PROMPT   # validate/compress 동일 패턴
```

구현은 `_rewrite_query`/`_validate_result`/`_compress_result`에 `user_context: str = ""` 파라미터 추가 후 `{"role": "system", "content": user_context + PROMPT}`로 합성 (기본값 ""면 기존과 바이트 동일).

### 6.3 REWRITE_SYSTEM_PROMPT 규칙 추가 (D6)

규칙 블록에 1인칭 치환 규칙 추가 — **개인 데이터 질의에 한정**:

```
- 질문이 사용자 본인에 대한 것('나', '내', '본인')이고 [현재 사용자 정보]가 주어졌다면,
  1인칭 표현을 사용자 이름으로 치환해 쿼리에 포함한다
- 일반 지식·정책·업무 절차 질문에는 사용자 이름을 넣지 않는다

예시:
질문: "나의 남은 휴가 개수와 월별 사용 현황 그래프로 보여줄 수 있겠니?"
([현재 사용자 정보] 이름: 배상규)
쿼리: "배상규 남은 휴가 개수 월별 사용 현황"
```

- 기존 예시(실업률)는 유지 — "이름 넣지 않는 경우"의 대조 예시 역할
- PII (FR-07): 주입 블록은 `render_user_context_block` 산출물 그대로 재사용 — whitelist(이름·부서·역할)만 포함, user_id/사번/이메일 금지 필드는 함수 차원에서 이미 차단됨. search_pipeline은 자체적으로 사용자 필드에 접근하지 않는다 (블록 문자열만 수신)

---

## 7. 테스트 설계 (TDD 순서)

| # | 테스트 파일 | 케이스 | 검증 FR |
|---|------------|--------|---------|
| T1 | `tests/application/rag_agent/test_tools_auth_filter.py` (신규) | `viewer_department_ids` 주입 시 HybridSearchRequest.metadata_filter에 미포함 / `visibility`는 lenient_filter로 이동 / 일반 키는 hard 유지 | FR-01, FR-02 |
| T2 | 〃 | 0건 + 주입 키 존재 시 warning 1회 (injected_keys 단언), 주입 키 없으면 로그 없음 | FR-03 |
| T3 | `tests/application/hybrid_search/test_hybrid_search_use_case.py` (확장) | lenient_filter → ES bool should(term+must_not exists) 본문 생성 / SearchFilter.metadata_lenient 전달 / collection_name term 필터 opt-in·미지정 시 부재 | FR-02, FR-05 |
| T4 | `tests/infrastructure/vector/test_qdrant_vectorstore.py` (확장) | `metadata_lenient` → 중첩 Filter(should=[FieldCondition, IsEmptyCondition]) 변환 / 기존 metadata must 변환 무회귀 | FR-02 |
| T5 | `tests/domain/agent_builder/test_rag_tool_config.py` (확장) | 한글 이름 + fallback 지정 → fallback 반환 / fallback 미지정 → 기존 `unnamed_tool` / 정상 영문명 무변경 | FR-04 |
| T6 | `tests/application/agent_builder/test_search_pipeline.py` (확장) | user_context_block 전달 시 rewrite/validate/compress system 프롬프트에 블록 포함 / 빈 블록이면 기존 프롬프트와 동일 | FR-06 |
| T7 | 〃 (통합 시나리오) | 사용자 블록("이름: 배상규") + "나의 휴가..." 질문 → mock LLM 프롬프트에 치환 규칙·이름 존재 단언 | FR-06, FR-07 |
| T8 | E2E 수동 (DoD) | 휴가 질문 → 검색 히트 → 차트 생성, `ai_tool_call` 쿼리에 "배상규"·tool_name 정상 기록 | FR-08 |

- 실행: Windows 이벤트 루프 flakiness 관례에 따라 모듈 격리 실행으로 검증
- SearchFilter `is_empty()` 확장은 T4에서 함께 단언

---

## 8. 구현 순서

```
1. T1 작성 → 실패 확인 → tools.py 키 3분류 + _hybrid_filters + 스키마 필드 추가 → 통과
2. T3·T4 작성 → 실패 → use_case/qdrant 변환 구현 → 통과
3. T2 작성 → 실패 → 경고 로그 구현 → 통과
4. T5 작성 → 실패 → sanitize 폴백 + ToolFactory 지정 → 통과
5. T3(컬렉션 필터 케이스) → _fetch_bm25 opt-in 필터 → 통과
6. T6·T7 작성 → 실패 → search_pipeline 파라미터 + 프롬프트 규칙 + compiler 배선 → 통과
7. multi_query passthrough (T1 확장 케이스) → 통과
8. 전체 pytest 격리 실행 + E2E 수동 (T8) — Qdrant/ES 로컬 기동 상태에서 재현 시나리오 확인
```

---

## 9. 리스크·영향 재확인

| 항목 | 설계상 처리 |
|------|------------|
| 기존 HybridSearchRequest 사용처 회귀 | frozen dataclass에 default_factory 필드 추가만 — 기존 생성부 무수정 컴파일 |
| routed 경로 상호작용 | 무변경. visibility 주입 시 routed는 기존대로 강등하고, 강등 목적지(legacy hybrid)가 이번 수정으로 정상화 |
| 완화 필터의 보안 의미 | "값 일치 OR 부재"라 visibility가 **색인된** 문서에는 즉시 엄격 적용 — 후속 색인 기능에서 코드 변경 없이 fail-closed 복귀 |
| 이름 포함 쿼리의 일반 질의 오염 | 프롬프트 규칙을 개인 데이터 질의로 한정 + 대조 예시 유지 (T7에서 일반 질의 케이스 추가 검토) |
| 사용자 블록 이중 주입 (supervisor+pipeline) | 서로 다른 LLM 호출(그래프 노드 vs 경량 파이프라인 LLM)이라 중복 아님 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-22 | Initial draft — 키 3분류·lenient 변환·사용자 컨텍스트 배선 상세 설계, ES 매핑 실측 반영 | 배상규 |
