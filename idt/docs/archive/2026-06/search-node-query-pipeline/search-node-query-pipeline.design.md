# Design: search-node-query-pipeline

> Created: 2026-06-10
> Phase: Design
> Plan: `docs/01-plan/features/search-node-query-pipeline.plan.md`
> Scope: `idt/` 백엔드 — Supervisor 그래프 search 노드에 rewrite → search → validate(루프) → compress 파이프라인 내장

---

## 0. 확정된 설계 결정

| # | 결정 사항 | 내용 |
|---|----------|------|
| **D1** | 검증 호출 절약 | 검색 시도는 총 3회(최초 1 + 재시도 2). **마지막(3번째) 시도 후에는 validate를 생략** — 결과를 어차피 채택하므로 무의미한 LLM 호출 제거. 최악 LLM 호출 = rewrite 1 + validate 2 + compress 1 = **4회** (Plan NFR ≤5 충족·개선) |
| **D2** | 메시지 규약 중앙화 | `[{worker_id} 검색결과]` prefix 규약·식별 predicate를 신설 모듈 `search_pipeline.py`에 정의하고 `workflow_compiler.py`가 import (의존 방향: compiler → pipeline 단방향, 순환 없음) |
| **D3** | 파이프라인 LLM 수명 | WorkflowCompiler **인스턴스당 1회 생성·캐시**(`_pipeline_llm_cache`) — compile 재귀(sub_agent)·반복 호출 간 재사용. `pipeline_llm_model=None`이거나 생성 실패 시 per-run 에이전트 LLM으로 fallback + warning 로그 (하위호환: 주입 없으면 기존과 동일 모델 사용) |
| **D4** | 도구 예외 시 재시도 | 검색 도구 자체 예외 발생 시 validate 생략하고 같은 쿼리로 즉시 재시도. 한도 소진 시 기존 동작대로 `"검색 실패: {e}"` 메시지 반환 (그래프 비중단) — 일시 장애 자동 복구 효과 |
| **D5** | rewrite 입력 | `latest_user_question(messages)` + 최근 대화 맥락(워커 산출물 제외, 최대 6개, 각 500자 truncate). `messages[-1]` 직접 사용 금지 — 마지막 메시지가 quality_gate 피드백일 수 있음 |
| **D6** | SupervisorState 불변 | 루프가 노드 함수 내부에서 완결되므로 **state 키 추가 없음**. 시도 횟수·재작성 쿼리는 step output_summary(`STEP_OUTPUT_SUMMARY_KEY`)로만 노출 |

---

## 1. 설계 개요

### 1-1. 현재 vs 목표

```
[현재] _create_search_node (workflow_compiler.py:563)
  query = state["messages"][-1].content      ← 대화체 원문/피드백 메시지가 그대로 쿼리
  result = await tool.ainvoke({"query": query})
  → AIMessage("[{worker_id} 검색결과]\n{원문 전체}")   ← 검증·압축 없음

[목표] search_pipeline.create_search_pipeline_node
  ① question = latest_user_question(messages); context = 최근 대화 맥락
  ② query = rewrite(question, context)                  # 경량 LLM, 실패 시 question
  ③ loop (시도 1..3):
       result = tool.ainvoke({"query": query})
       - 도구 예외 → 재시도 (validate 생략, D4)
       - 마지막 시도 → 결과 채택 (validate 생략, D1)
       - verdict = validate(question, query, result)    # 경량 LLM, 실패 시 통과 처리
       - relevant → 채택 / 부적합 → query = improved_query 후 재검색
  ④ len(result) > threshold → result = compress(question, result)  # 경량 LLM
  → AIMessage("[{worker_id} 검색결과]\n{result}", name=worker_id)
    + token_usage 반영 + step summary 기록
```

### 1-2. 그래프 구조 (변경 없음)

`supervisor → search 워커 → quality_gate → supervisor` 라우팅·엣지·SupervisorState 모두 불변.
파이프라인은 search 워커 노드 함수 내부에서만 동작한다.

---

## 2. 변경 상세

### 2-1. `src/domain/agent_builder/policies.py` — `SearchPipelinePolicy` 추가

```python
class SearchPipelinePolicy:
    """search 노드 파이프라인 도메인 규칙 (search-node-query-pipeline).

    순수 규칙만 보관 — LLM/도구 호출 없음.
    """

    MAX_SEARCH_ATTEMPTS = 3            # 최초 1 + 재시도 2
    DEFAULT_COMPRESS_THRESHOLD = 4000  # 압축 발동 임계 길이(자)

    def __init__(self, compress_threshold: int | None = None) -> None:
        self.compress_threshold = (
            compress_threshold
            if compress_threshold and compress_threshold > 0
            else self.DEFAULT_COMPRESS_THRESHOLD
        )

    def is_last_attempt(self, attempt: int) -> bool:
        """attempt(1-base)가 마지막 시도인가 — True면 validate 생략(D1)."""
        return attempt >= self.MAX_SEARCH_ATTEMPTS

    def needs_compression(self, text: str) -> bool:
        return len(text) > self.compress_threshold
```

### 2-2. `src/application/agent_builder/search_pipeline.py` — 신설 (핵심)

#### (a) 메시지 규약 (D2 — 규약의 단일 출처)

```python
SEARCH_RESULT_MARKER = "검색결과"

def format_search_result(worker_id: str, body: str) -> str:
    """search 워커 산출 메시지 본문 규약. _is_search_result 식별과 쌍."""
    return f"[{worker_id} {SEARCH_RESULT_MARKER}]\n{body}"

def is_search_result(msg) -> bool:        # workflow_compiler._is_search_result 이동
def is_worker_output(msg) -> bool:        # workflow_compiler._is_worker_output 이동
def latest_user_question(messages: list) -> str:
    # WorkflowCompiler._latest_user_question 이동 (모듈 함수화)
```

`workflow_compiler.py`는 위 4개를 import해 기존 사용처(final_answer/analysis)를 유지한다
(기존 `_is_search_result`/`_is_worker_output`/`_latest_user_question` 정의 삭제).

#### (b) LLM 구조화 출력 스키마

```python
class RewrittenQuery(BaseModel):
    query: str = Field(description="검색 엔진에 보낼 최적화 쿼리 (핵심 키워드 중심 한 문장)")
    reasoning: str = Field(default="", description="재작성 근거")

class SearchResultVerdict(BaseModel):
    relevant: bool = Field(description="검색 결과가 질문과 관련 있으면 true. 명백히 무관할 때만 false")
    reason: str = Field(default="")
    improved_query: str = Field(default="", description="relevant=false일 때 개선 검색 쿼리")
```

#### (c) 파이프라인 단계 함수 — 모두 graceful fallback

| 함수 | 동작 | 실패 시 fallback |
|------|------|-----------------|
| `_rewrite_query(llm, question, context, logger) -> str` | `with_structured_output(RewrittenQuery)` 호출, `query` 공백이면 fallback | 원본 `question` 반환 + warning |
| `_validate_result(llm, question, query, result, logger) -> SearchResultVerdict` | `with_structured_output(SearchResultVerdict)` 호출. 결과는 head 3,000자만 판정에 사용 | `relevant=True`(통과 처리) + warning |
| `_compress_result(llm, question, result, logger) -> str` | 압축 프롬프트로 `ainvoke`, 빈 응답이면 fallback | 원문 `result` 반환 + warning |
| `_collect_context(messages) -> str` | 워커 산출물(`is_worker_output`) 제외한 최근 6개 메시지를 `role: content[:500]` 형태로 직렬화 | — (순수 함수) |
| `_safe_search(tool, query, logger) -> tuple[bool, str]` | `tool.ainvoke({"query": query})`. 예외 시 `(False, "검색 실패: {e}")` + error 로그(스택 포함) | — |

각 함수는 40줄 이하 단일 책임. LLM 응답 길이는 호출부에서 누적해 토큰 추정에 사용.

#### (d) `create_search_pipeline_node` — 노드 팩토리

```python
def create_search_pipeline_node(
    worker_id: str,
    tool,
    pipeline_llm,                  # 경량 LLM (BaseChatModel)
    policy: SearchPipelinePolicy,
    logger: LoggerInterface,
):
    async def search_node(state: SupervisorState) -> dict:
        messages = state["messages"]
        question = latest_user_question(messages) or _last_message_text(messages)
        context = _collect_context(messages)

        llm_chars = 0  # 파이프라인 LLM 응답 누적(토큰 추정용)
        query = await _rewrite_query(pipeline_llm, question, context, logger)

        attempt, result_str, validated = 0, "", False
        while True:
            attempt += 1
            ok, result_str = await _safe_search(tool, query, logger)
            if policy.is_last_attempt(attempt):
                break                          # D1: 마지막 시도 — 그대로 채택
            if not ok:
                continue                       # D4: 도구 예외 — validate 생략 재시도
            verdict = await _validate_result(pipeline_llm, question, query, result_str, logger)
            if verdict.relevant:
                validated = True
                break
            query = verdict.improved_query or query

        compressed = False
        if ok and policy.needs_compression(result_str):
            result_str = await _compress_result(pipeline_llm, question, result_str, logger)
            compressed = True

        result_msg = AIMessage(
            content=format_search_result(worker_id, result_str), name=worker_id,
        )
        token_delta = (len(result_str) + llm_chars) // 4
        summary = (
            f"query='{query}' attempts={attempt} "
            f"validated={validated} compressed={compressed} len={len(result_str)}"
        )[:512]
        return {
            "messages": [result_msg],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + token_delta,
            STEP_OUTPUT_SUMMARY_KEY: summary,
        }

    return search_node
```

> 주: 위 의사코드의 `llm_chars` 누적·`ok` 스코프 등은 구현 시 helper 반환값으로 정리한다
> (함수 40줄 제한 — 루프 본체를 `_search_with_validation` helper로 분리 권장).

#### (e) 프롬프트 (모듈 상수)

```python
REWRITE_SYSTEM_PROMPT = """당신은 검색 쿼리 작성 전문가입니다.
사용자 질문과 대화 맥락에서 '검색해야 할 정보'만 추출해 검색 엔진에 최적화된 쿼리 하나를 작성하세요.

규칙:
- 그래프/차트/표 등 출력 형식 요구는 제거한다 (검색 대상이 아님)
- 핵심 주제·기간·지역·지표를 보존한다
- 대화 맥락의 지시어(그거, 아까 그 자료)는 실제 대상으로 치환한다
- 한 문장, 명사구 중심으로 작성한다

예시:
질문: "대한민국 2025년 실업률 정보를 가지고 월별 %별 그래프를 그려줄 수 있니?"
쿼리: "대한민국 2025년 월별 실업률 통계"
"""

VALIDATE_SYSTEM_PROMPT = """검색 결과가 질문에 답하는 데 쓸 수 있는지 판정하세요.

규칙:
- 결과가 질문 주제와 명백히 무관하거나, 오류/빈 내용일 때만 relevant=false
- 부분적으로라도 유용하면 relevant=true (과도한 재검색 방지)
- relevant=false면 improved_query에 더 정확한 대안 쿼리를 제안하세요
"""

COMPRESS_SYSTEM_PROMPT = """검색 결과에서 질문에 답하는 데 필요한 정보만 추려 압축하세요.

규칙:
- 수치, 날짜, 단위, 출처(URL/기관명)는 반드시 보존한다
- 질문과 무관한 광고·내비게이션·중복 문장은 제거한다
- 원문에 없는 내용을 추가하거나 추측하지 않는다
- 목록/표 형태로 구조화해 작성한다
"""
```

### 2-3. `src/application/agent_builder/workflow_compiler.py` 변경

**(a) 생성자 — 파이프라인 LLM 모델·임계값 주입**

```python
def __init__(
    self,
    ...,
    chart_max_count: int = 0,
    pipeline_llm_model: LlmModel | None = None,   # ★ 신규: 경량 모델 (None=per-run LLM)
    search_compress_threshold: int | None = None, # ★ 신규: None=Policy 기본값(4000)
) -> None:
    ...
    self._pipeline_llm_model = pipeline_llm_model
    self._search_compress_threshold = search_compress_threshold
```

**(b) `compile()` — search 워커 존재 시 파이프라인 LLM 1회 생성 (D3)**

```python
pipeline_llm = None  # search 워커 첫 등장 시 lazy 생성

def _get_pipeline_llm():
    # self._pipeline_llm_model 있으면 llm_factory.create(model, temperature=0.0)
    # RuntimeError(API 키 부재) 등 실패 → warning 로그 + per-run llm 반환
    # None이면 per-run llm 그대로 (하위호환)
```

**(c) `_create_search_node` 대체**

```python
if category == "search":
    worker_map[worker_def.worker_id] = create_search_pipeline_node(
        worker_id=worker_def.worker_id,
        tool=tool,
        pipeline_llm=self._resolve_pipeline_llm(llm),
        policy=SearchPipelinePolicy(self._search_compress_threshold),
        logger=self._logger,
    )
    function_node_ids.add(worker_def.worker_id)
```

기존 `_create_search_node` 메서드는 삭제. `_is_search_result`/`_is_worker_output`/
`_latest_user_question`은 search_pipeline import로 대체(D2).

### 2-4. `src/config.py` — 신규 설정 3종

```python
# Search Pipeline (search-node-query-pipeline)
# rewrite/validate/compress용 경량 LLM. 빈 값이면 per-run 에이전트 LLM 사용.
search_pipeline_provider: str = "openai"
search_pipeline_model_name: str = "gpt-4o-mini"
# 검색결과 압축 발동 임계 길이(자). 이하면 원문 그대로 전달.
search_compress_threshold: int = 4000
```

### 2-5. `src/api/main.py` (composition root) — 파이프라인 LlmModel 구성·주입

```python
_PIPELINE_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "",          # ollama는 키 불필요 (LLMFactory가 api_key 미사용)
}

def _build_search_pipeline_llm_model() -> LlmModel | None:
    provider = settings.search_pipeline_provider
    model_name = settings.search_pipeline_model_name
    if not provider or not model_name:
        return None        # 미설정 → per-run LLM fallback
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="search-pipeline-llm",  # DB 미등록 인라인 엔티티 (LLMFactory는 provider/model_name/api_key_env만 사용)
        provider=provider,
        model_name=model_name,
        display_name=f"Search Pipeline ({model_name})",
        description=None,
        api_key_env=_PIPELINE_API_KEY_ENV.get(provider, "OPENAI_API_KEY"),
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )

workflow_compiler = WorkflowCompiler(
    ...,
    chart_max_count=settings.chart_max_count,
    pipeline_llm_model=_build_search_pipeline_llm_model(),       # ★
    search_compress_threshold=settings.search_compress_threshold, # ★
)
```

> LLMFactory는 `provider`/`model_name`/`api_key_env`만 사용하므로(`llm_factory.py:21-67`)
> 나머지 필드는 형식상 채움. API 키 미설정 시 `create()`가 RuntimeError → compile()의
> fallback 경로(D3)가 per-run LLM으로 흡수.

### 2-6. `.env.example` — 신규 환경변수 문서화

```
# Search Pipeline (search 노드 쿼리 재작성/검증/압축용 경량 LLM)
SEARCH_PIPELINE_PROVIDER=openai
SEARCH_PIPELINE_MODEL_NAME=gpt-4o-mini
SEARCH_COMPRESS_THRESHOLD=4000
```

---

## 3. 실패 분기 매트릭스 (graceful degradation)

| 단계 | 실패 상황 | 처리 | 결과 |
|------|----------|------|------|
| 파이프라인 LLM 생성 | API 키 부재 등 RuntimeError | warning 로그 → per-run LLM 사용 | 파이프라인 정상 동작(모델만 교체) |
| rewrite | LLM 예외 / 빈 query | warning → 원본 질문으로 검색 | 기존 동작과 동일 수준 |
| 검색 도구 | tool.ainvoke 예외 | error 로그(스택) → 재시도(D4), 소진 시 "검색 실패: {e}" | 기존 동작 보존 |
| validate | LLM 예외 | warning → relevant=True 통과 처리 | 재검색 없이 진행 |
| compress | LLM 예외 / 빈 응답 | warning → 원문 그대로 전달 | 정보 손실 없음 |

모든 분기에서 그래프는 중단되지 않고 `[{worker_id} 검색결과]` 메시지가 반환된다.

---

## 4. 테스트 설계 (TDD — 구현 전 작성)

### 4-1. `tests/domain/agent_builder/test_search_pipeline_policy.py`

| Case | 검증 |
|------|------|
| `is_last_attempt` | 1,2 → False / 3,4 → True |
| `needs_compression` | threshold 경계(== False, +1 True) |
| 생성자 | None/0/음수 → DEFAULT(4000), 양수 → 해당 값 |

### 4-2. `tests/application/agent_builder/test_search_pipeline.py`

Fake 객체: `FakeStructuredLLM`(with_structured_output(schema).ainvoke 시나리오 큐),
`FakeTool`(ainvoke 응답/예외 큐), `FakeLogger`.

| Case | 시나리오 | 기대 |
|------|---------|------|
| 정상 1회 통과 | rewrite OK → search OK → validate relevant | 검색 1회, AIMessage prefix `[w1 검색결과]`, name=w1 |
| 재검색 루프 | validate 부적합(improved_query) ×1 → 2번째 relevant | tool이 받은 쿼리가 improved_query로 교체됨, attempts=2 |
| 3회 소진 | validate 부적합 ×2 | 검색 3회·validate 2회(D1), 마지막 결과 채택, warning 로그 |
| rewrite 실패 | structured output 예외 | 원본 질문으로 검색 진행 |
| validate 실패 | LLM 예외 | 통과 처리(재검색 없음) |
| 도구 예외 재시도 | search 예외 ×1 → 2번째 성공 | validate 생략 재시도(D4), 최종 정상 결과 |
| 도구 예외 소진 | search 예외 ×3 | content에 "검색 실패" 포함, 그래프 비중단 |
| 압축 발동 | 결과 길이 > threshold | compress 호출 1회, 압축본으로 메시지 구성 |
| 압축 미발동 | 결과 길이 ≤ threshold | compress 미호출, 원문 유지 |
| 압축 실패 | compress LLM 예외 | 원문 그대로 전달 |
| token_usage | 결과+LLM 응답 chars//4 누적 | state 대비 증가량 일치 |
| step summary | 반환 dict의 `STEP_OUTPUT_SUMMARY_KEY` | attempts/compressed 포함 |
| rewrite 입력 | messages 마지막이 quality_gate 피드백 | question은 마지막 user 메시지에서 추출(D5) |

### 4-3. `tests/application/agent_builder/test_workflow_compiler*.py` (기존 보강)

| Case | 기대 |
|------|------|
| pipeline_llm_model 주입 시 | llm_factory.create가 해당 모델로 호출(temperature=0.0) |
| 생성 실패 시 | per-run LLM으로 fallback + warning |
| 미주입(None) 시 | per-run LLM 사용 — 기존 테스트 회귀 없음 |
| `is_search_result` import 이동 | final_answer/analysis 컨텍스트 분류 기존 테스트 통과 |

> 실행 주의: Windows 이벤트 루프 teardown 산발 실패 이력 — 모듈 격리 실행으로 검증.

---

## 5. 구현 순서 (Do 체크리스트)

1. [x] **Red**: `test_search_pipeline_policy.py` 작성 → 실패 확인 (ImportError)
2. [x] **Green**: `SearchPipelinePolicy` 구현 (policies.py) — 10 passed
3. [x] **Red**: `test_search_pipeline.py` 작성 → 실패 확인 (ModuleNotFoundError)
4. [x] **Green**: `search_pipeline.py` 구현 — 22 passed
5. [x] **Refactor + Integration**: workflow_compiler 위임 교체, predicate import 이동, `_create_search_node` 삭제, `test_search_node.py`를 wiring 테스트로 대체
6. [x] config.py 설정 3종 + main.py `_build_search_pipeline_llm_model` 구성·주입 + `.env.example`
7. [x] 기존 테스트 회귀 확인: tests/application/agent_builder 307 passed, test_analyze_user_context 9 passed
8. [x] 금지 패턴 수동 검증: print() 없음, search_pipeline의 infrastructure import 없음, domain policy 순수성 유지 (스킬 기반 정밀 검증은 Check 단계에서 gap-detector와 병행 가능)

---

## 6. 영향 범위 / 주의사항

- **프론트엔드 영향 없음**: 메시지 규약(`[{worker_id} 검색결과]`)·state 스키마 불변.
- **하위호환**: `pipeline_llm_model` 미주입 시 per-run LLM으로 파이프라인 동작 — 단, 기존 대비 "rewrite/validate가 추가된다"는 동작 변화는 모든 경로에 적용됨(의도된 변경).
- **sub_agent 경로**: 서브 에이전트 내부의 search 워커도 동일 compiler를 타므로 파이프라인 자동 적용 (compile 재귀 시 동일 `_resolve_pipeline_llm` 사용).
- **비용**: 검색 워커 호출당 경량 LLM 2~4회 추가. gpt-4o-mini 기준 무시 가능 수준이나, ollama 등 로컬 모델 사용 시 지연 주의.
- **금지 사항 준수**: 대화 기록 vector DB 저장 없음, Parent/Child 문서 구조 무관, 레이어 규칙(domain 순수성) 유지.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-10 | Initial design — D1~D6 결정, 실패 분기 매트릭스, 테스트 설계 | 배상규 |
