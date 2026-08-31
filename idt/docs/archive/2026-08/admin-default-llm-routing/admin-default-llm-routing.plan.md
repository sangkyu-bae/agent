# admin-default-llm-routing Planning Document

> **Summary**: 범용 캐시 포트를 아래단에 신설하고, 그 위에 LLM 모델 리졸버를 올려 하드코딩 `ChatOpenAI` 어댑터 9곳이 관리자 설정 모델을 **재시작 없이** 따라가게 한다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.2.0
> **Author**: 배상규
> **Date**: 2026-08-29
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `LLMFactory`는 `base_url`로 self-host를 이미 지원하는데, **의도 판정·웹검색 판단·환각 검사·프롬프트 합성·메모리 추출·위키 정제 어댑터 9곳이 생성자 안에서 `ChatOpenAI`를 직접 만든다.** 관리자가 기본 모델을 NPU로 바꿔도 이 경로는 `api.openai.com`으로 나가, "NPU에 붙었다"고 해도 **절반만 붙은 상태**로 측정하게 된다. 게다가 `_default_llm_model`은 부팅 1회 로드라 모델 교체에 **서버 재시작**이 필요하다 |
| **Solution** | 아래단에 **범용 KV 캐시 포트**(`CachePort`)를 뚫고 인메모리 어댑터를 붙인다. 그 위에 `LlmModelResolver`를 얹어 요청 시점에 모델을 해석하고, 관리자 변경 UseCase가 캐시를 무효화한다. 어댑터 9곳은 완성된 LLM이 아니라 **provider 포트**를 주입받는다 |
| **Function/UX Effect** | 관리자가 화면에서 기본 모델을 NPU Gemma로 바꾸면 **재시작 없이 다음 요청부터** 9개 경로 전부가 NPU로 흐른다 |
| **Core Value** | NPU 검증의 전제 조건이자, 네 번째로 중복될 뻔한 캐시 구현을 **재사용 가능한 공용 자산**으로 만드는 작업 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | NPU 실측을 하려면 LLM 호출이 한 군데로 모여야 하는데 9곳이 팩토리를 우회하고, 모델 교체마다 재시작이 필요하다 |
| **WHO** | P2 — 자사 인프라(NPU)에서 에이전트를 운영하려는 KB 운영자 / 플랫폼 관리자 |
| **RISK** | LangChain 객체는 직렬화 불가 → 캐시 계층을 잘못 나누면 Redis 전환 시 통째로 못 쓴다 |
| **SUCCESS** | 관리자 화면에서 기본 모델 변경 → 재시작 없이 9경로 전부 새 엔드포인트로 요청 |
| **SCOPE** | 범용 캐시 포트 + 인메모리 어댑터 + LLM 리졸버 + 배선 9곳. 기존 중복 3건 흡수·Redis 어댑터는 제외 |

---

## 1. Overview

### 1.1 Purpose

NPU 위 Gemma 실측 테스트의 **선행 과제**다.

붙는 것 자체는 코드 변경이 필요 없다 — `LLMFactory._create_openai`가 `base_url`을 이미 지원하고(`llm_factory.py:44-46`), 인증 없는 self-host용 더미키 경로까지 있다(`llm_factory.py:69-83`). 문제는 **메인 대화 경로만 따라간다**는 것과, 그마저도 **재시작을 요구한다**는 것이다.

### 1.2 Background

#### D-1 — 팩토리를 우회하는 어댑터가 9곳 배선돼 있다

```
main.py:961   HallucinationEvaluatorAdapter()                    ← 인자 없음, gpt-4o-mini 고정
main.py:966   LLMSearchDecisionAdapter(logger=app_logger)
main.py:4873  LLMIntentAnalyzerAdapter(logger=logger)
main.py:4090  LLMPromptGeneratorAdapter(logger=app_logger, config=config)
main.py:2241  MemoryCandidateExtractor.from_openai(settings.memory_extraction_model_name, ...)
main.py:2267  FeedbackWikiDistiller.from_openai(settings.openai_llm_model, ...)
main.py:4227  FolderSummaryDistiller.from_openai(...)
main.py:4265  WikiDistiller.from_openai(...)
main.py:3340  OpenAIQAGenerator(model_name=settings.eval_qa_gen_model)
```

아홉 곳 모두 `settings` 문자열이나 리터럴에서 모델명을 받고, **`base_url`을 실을 자리가 없다.**

#### D-2 — 바로 옆 줄에 주입 패턴이 이미 있다

```python
# main.py:969-975
if _default_llm_model is not None:
    excel_viz_llm = _llm_factory.create(_default_llm_model, temperature=0)
    excel_chart_builder = LangChainChartBuilder(llm=excel_viz_llm, ...)
```

같은 함수 안 세 줄 위(`:961`, `:966`)가 이 패턴을 쓰지 않는다. 다만 이 선례도 **부팅 시 1회 고정**이라 재시작 문제는 그대로 안고 있다.

#### D-3 — 어댑터가 3가지 패턴으로 갈린다

| 패턴 | 대상 | 현재 시그니처 |
|------|------|---------------|
| **C. 이미 `llm` 주입식** | `memory/extractor.py:59`, `wiki/wiki_distiller.py:46`, `wiki/feedback_distiller.py`, `wiki/folder_summary_distiller.py` | `__init__(self, llm, logger)` + `from_openai()` 클래스메서드 |
| **B. `chain` 주입 seam 있음** | `intent/adapter.py:100`, `prompt_composer/adapter.py:123` | `__init__(self, logger, config=None, chain=None)`, 내부 `_build_chain()`이 `ChatOpenAI` 생성 |
| **A. `model_name: str` 고정** | `hallucination/adapter.py:24`, `search_decision/adapter.py:27`, `eval_testset/qa_generator.py:34` | `__init__(self, model_name="gpt-4o-mini", temperature=0.0)` |

**공통 함정**: 세 패턴 모두 생성자에서 `prompt | llm.with_structured_output(...)`로 chain을 **미리 조립**한다. 런타임 해석을 하려면 조립 시점을 옮겨야 한다 (§7.2 AD-2).

#### D-4 — 어댑터마다 temperature가 다르다

단일 인스턴스를 공유할 수 없다. 캐시 키에 temperature가 들어가야 한다.

```
hallucination 0.0 / search_decision 0.0 / memory 0 / wiki distiller 3종 0
intent        IntentConfig.INTENT_ANALYZER_TEMPERATURE
prompt_composer  PromptComposerConfig.PROMPT_COMPOSER_TEMPERATURE
eval qa_generator 0.2
```

#### D-5 — 기존 테스트가 `ChatOpenAI` 심볼을 patch 중이다

```python
# tests/infrastructure/hallucination/test_adapter.py:24
with patch("src.infrastructure.hallucination.adapter.ChatOpenAI") as mock_chat:
```

어댑터에서 임포트를 제거하면 `AttributeError`로 깨진다. 하위호환 유지가 **회귀 방지 조건**이다.

#### D-6 — 같은 캐시 패턴이 이미 3곳에 중복 구현돼 있다

| 기존 구현 | 위치 | 캐시 | 무효화 |
|-----------|------|------|--------|
| `CostCalculator` | `application/agent_run/cost_calculator.py:33` | `LlmModel` 가격, TTL 5분, monotonic clock 주입 | `invalidate(id\|None)` |
| `ModelNameResolver` | `application/agent_run/model_name_resolver.py:26` | `LlmModel` id 매핑, **TTL 없음** | `invalidate()` |
| `InMemoryChatStreamCache` | `infrastructure/general_chat/stream_cache.py` | TTL 300s + max_sessions | — |

셋 다 `dict`를 각자 굴린다. 공용 모듈 없이 만들면 **네 번째 중복**이 된다.

#### D-7 — 포트/무효화/Redis 선례가 모두 갖춰져 있다

```python
# domain/tool_selection/interfaces/selection_cache_port.py — 포트 선례
# "인터페이스를 먼저 뚫어두는 이유는 나중에 TTL 캐시로 교체할 때
#  셀렉터 코드를 건드리지 않기 위함이다"

# application/llm_model/update_llm_model_pricing_use_case.py:57 — 무효화 책임 위치
# ★ 핵심: invalidate 의무 호출을 use case 안에 캡슐화
self._cost_calc.invalidate(model_id)
```

`src/infrastructure/redis/redis_client.py`(`redis.asyncio` + pool)와 설정(`config.py:66-70`)이 **이미 존재**한다. "추후 Redis"는 신규 도입이 아니라 기존 자산 연결이다.

#### D-8 — `is_default` 변경 경로에 무효화 훅이 비어 있다

`update_llm_model_pricing_use_case`만 `invalidate`를 호출한다. 일반 수정(`update_llm_model_use_case.py`), 생성, 비활성화 경로에는 무효화가 **없다**. 관리자가 기본 모델을 바꾸는 바로 그 경로다.

#### D-9 — LangChain 객체는 직렬화할 수 없다 ★

캐시 설계의 핵심 제약이다. `BaseChatModel`은 소켓·클라이언트 핸들을 안고 있어 JSON/pickle 직렬화가 불가능하다. **LLM 인스턴스를 `CachePort`에 담으면 인메모리에선 동작하지만 Redis 어댑터로 교체하는 순간 전부 깨진다.** 캐시를 2계층으로 갈라야 한다 (§7.2 AD-1).

### 1.3 Related Documents

| Document | Path | Relation |
|----------|------|----------|
| LLM 모델 레지스트리 | `LLM-MODEL-REG-001 / 002` | `base_url`·`api_key_env` 계약 |
| 에이전트 관측 | `AGENT-OBS-001 §3-2 / §14-6` | TTL 캐시 + invalidate 의무 호출 선례 |
| 도구 선별 | tool-recommender Design §4.2 | `SelectionCachePort` 포트 선례 |
| DB 세션 규칙 | `docs/rules/db-session.md` | 리졸버의 세션 취급 |
| 로깅 규칙 | `docs/rules/logging.md` | 폴백·캐시 미스 로깅 |

---

## 2. Scope

### 2.1 In Scope

**A. 공통 캐시 모듈 (아래단, 재사용 대상)**

1. `src/domain/cache/interfaces.py` — `CachePort` (async get/set/delete/clear, TTL)
2. `src/infrastructure/cache/in_memory_cache.py` — 프로세스 로컬 TTL 어댑터 (clock 주입)
3. 저장 값은 **JSON 직렬화 가능해야 한다**는 포트 계약 명시 (Redis 전환 대비)

**B. LLM 리졸버 (공통 모듈의 첫 소비자)**

4. `LlmModelResolver` — 기본/보조 `LlmModel` 해석 + `CachePort` 경유 + 2단 폴백
5. `UtilityLLMProviderPort` — 어댑터가 주입받을 포트. 인스턴스 캐시(L2)는 프로세스 로컬
6. `settings.utility_llm_model_name`, `settings.llm_model_cache_ttl_seconds`

**C. 무효화 배선**

7. `create` / `update` / `deactivate` / `pricing` UseCase 4곳에서 캐시 무효화 (D-8 구멍 포함)

**D. 어댑터 전환**

8. 패턴 C 4곳 — `main.py` 호출부 교체 (어댑터 무수정)
9. 패턴 B 2곳 + 패턴 A 3곳 — provider 파라미터 추가 (additive, 미주입 시 기존 동작)
10. TDD 테스트 (Red → Green) + 하위호환 회귀 테스트

### 2.2 Out of Scope

| 제외 항목 | 이유 |
|-----------|------|
| 기존 중복 3건 흡수 (`CostCalculator`, `ModelNameResolver`, `stream_cache`) | 공통 모듈이 실전 검증된 뒤 별도 사이클. AGENT-OBS-001 관측 경로 회귀 위험 |
| Redis 어댑터 구현 | 현재 단일 서버. 포트만 정확히 뚫어두고 다중 서버 전환 시 어댑터 1개 추가 |
| 무효화 pub/sub 전파 | Redis 어댑터와 함께. 그때까지는 TTL이 수렴을 보장 (R-2) |
| `query_rewrite`, `multi_query`, `research_agent/*` | `main.py` 배선 미확인. 죽은 코드 정리가 섞이면 NPU 테스트가 늦어진다 |
| 임베딩 (`embedding_factory.py:22`) | 모델 교체 시 Qdrant 전면 재색인 필요 |
| `ragas/target_executor.py:118` | 평가 대상 모델 문자열 지정이 **의도된 설계** |
| `llm_adapter.py:15` | 사용처 확인 필요. 리터럴 하드코딩이라 별도 처리 |
| 관리자 UI / API 계약 변경 | 기존 `is_default` 토글로 충분 |
| vLLM 기동·NPU 벤더 설정 | 인프라 영역 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-1 | `CachePort`는 async `get`/`set(ttl)`/`delete`/`clear`를 제공한다 | P0 |
| FR-2 | 인메모리 어댑터는 TTL 만료를 clock 주입으로 테스트 가능하게 구현한다 | P0 |
| FR-3 | 관리자가 `is_default`로 지정한 모델이 9개 어댑터 전부의 LLM이 된다 | P0 |
| FR-4 | `utility_llm_model_name` 설정 시 9곳은 보조 모델을, 미설정 시 기본 모델을 쓴다 | P0 |
| FR-5 | 모델 변경 시 **재시작 없이** 다음 요청부터 반영된다 | P0 |
| FR-6 | `create`/`update`/`deactivate`/`pricing` UseCase가 캐시 무효화를 의무 호출한다 | P0 |
| FR-7 | 보조 모델명이 DB에 없거나 비활성이면 warning 후 기본 모델로 폴백한다 | P0 |
| FR-8 | 기본 모델 해석 실패 시 기존 `settings` 폴백을 유지해 서비스가 죽지 않는다 | P0 |
| FR-9 | 어댑터에 provider 미주입 시 기존 `ChatOpenAI` 동작을 유지한다 | P0 |
| FR-10 | 각 어댑터의 기존 temperature가 캐시 키와 팩토리 호출에 그대로 전달된다 | P1 |
| FR-11 | 캐시 미스 시에도 요청은 성공한다 (캐시 장애가 기능을 막지 않는다) | P0 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 | 측정 |
|----|----------|------|
| NFR-1 | 요청당 LLM 해석 오버헤드는 캐시 히트 시 DB 조회 0회 | 쿼리 로그 |
| NFR-2 | Redis 어댑터 추가 시 **소비자 코드 무수정** | 포트 계약 리뷰 |
| NFR-3 | 아키텍처 불변 — domain은 순수 ABC만, infrastructure→application 참조 없음 | `/verify-architecture` |
| NFR-4 | 기존 테스트 전량 통과 (특히 `ChatOpenAI` patch 테스트) | `pytest` |
| NFR-5 | 폴백·캐시 미스 로깅에 `request_id` 포함 | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `CachePort` + `InMemoryCache` TDD 완료 (TTL 만료·삭제·clear 테스트)
- [ ] `LlmModelResolver` 2단 폴백 + 캐시 히트/미스 테스트
- [ ] UseCase 4곳 무효화 의무 호출 + 테스트
- [ ] 9개 배선 지점 전환, 어댑터 5곳 provider 파라미터 추가
- [ ] 기존 테스트 전량 통과
- [ ] **재시작 없이** 기본 모델 교체 → 9경로 반영 실측
- [ ] self-host `base_url` 모델 지정 시 OpenAI 호출 0건 확인

### 4.2 Quality Criteria

| 항목 | 기준 |
|------|------|
| 하위호환 | provider 미주입 호출이 기존과 동일 동작 |
| Redis 전환 가능성 | `CachePort`에 담기는 값이 전부 JSON 직렬화 가능 |
| 폴백 안전성 | 캐시·보조 모델 오설정이 요청을 실패시키지 않음 |
| 관측성 | 어떤 모델로 해석·폴백됐는지 로그로 판별 가능 |

---

## 5. Risks and Mitigation

| ID | 리스크 | 영향 | 완화 |
|----|--------|------|------|
| **R-1** | **LangChain 객체 직렬화 불가**를 놓치고 LLM 인스턴스를 `CachePort`에 담음 | Redis 전환 시 전면 재작업 | **2계층 분리 (AD-1)**. L1=값(직렬화 가능), L2=인스턴스(프로세스 로컬 전용). 포트 docstring에 계약 명시 |
| **R-2** | 다중 워커/서버 전환 시 무효화가 자기 프로세스에만 적용 | 워커별로 다른 모델 사용 | TTL 안전장치 기본 탑재(기본 60초) → 최대 TTL 후 수렴. 완전 해결은 Redis pub/sub |
| **R-3** | 런타임 해석으로 매 호출 chain 재조립 → 지연 증가 | 응답 지연 | L2 인스턴스 캐시 + 어댑터의 chain 메모이제이션. `updated_at`을 키에 포함해 변경 시에만 재조립 |
| **R-4** | Gemma가 `with_structured_output`을 못 받음 | 9곳 중 구조화 출력 다수 실패 | 착수 **전** vLLM tool-calling 검증(§9 Step 0). 실패 시 `method="json_schema"` 폴백 검토 |
| **R-5** | `ChatOpenAI` 임포트 제거로 기존 patch 테스트 붕괴 | 테스트 대량 실패 | 임포트·기본 경로 유지. provider는 additive (FR-9) |
| **R-6** | 보조 작업까지 대형 모델로 가서 비용·지연 상승 | 프로덕션 회귀 | 2단 구조 — `utility_llm_model_name=gpt-4o-mini`로 현행 복원 |
| **R-7** | 캐시 조회 실패가 요청 실패로 전파 | 서비스 중단 | FR-11 — 캐시는 부가. 미스/에러 시 DB 직행 |
| **R-8** | `stream_usage=True`를 vLLM이 무시해 토큰 원장이 빔 | 비용 관측 공백 | self-host는 가격 0 등록이라 영향 제한. 별건 분리 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| 자원 | 유형 | 변경 |
|------|------|------|
| `src/domain/cache/interfaces.py` | **신규** | `CachePort` |
| `src/infrastructure/cache/in_memory_cache.py` | **신규** | TTL 인메모리 어댑터 |
| `src/domain/llm/interfaces.py` | 추가 | `UtilityLLMProviderPort` |
| `src/application/llm_model/resolver.py` | **신규** | `LlmModelResolver` (기본/보조 해석 + 캐시) |
| `src/config.py` | 설정 | `utility_llm_model_name`, `llm_model_cache_ttl_seconds` |
| `src/application/llm_model/{create,update,deactivate}_*.py` | 무효화 | `cache.delete(...)` 의무 호출 추가 |
| `src/api/main.py` | DI | 캐시·리졸버 조립, 9개 배선 교체 |
| `hallucination`/`search_decision`/`qa_generator`/`intent`/`prompt_composer` 어댑터 | 어댑터 | provider 파라미터 추가 (additive) |
| `memory/extractor.py`, `wiki/*_distiller.py` | 어댑터 | **무수정** (호출부만) |
| `.env.example` | 문서 | 신규 변수 |

DB 마이그레이션 **없음**. API 계약 변경 **없음** → 프론트 동기화 불필요.

### 6.2 Current Consumers

| 소비처 | 영향 |
|--------|------|
| 의도 판정 / 웹검색 판단 / 환각 검사 | LLM 교체. 판정 품질 재확인 필요 |
| 프롬프트 합성 (agent-create-pipeline) | 동일 |
| 메모리 추출 / 위키 정제 3종 | 동일 |
| eval QA 생성 | 평가셋 생성 모델 변경 — **기준선 이동 주의** |
| 기존 `CostCalculator` / `ModelNameResolver` | **무영향** (흡수 제외) |

### 6.3 Verification

```bash
pytest tests/domain/cache tests/infrastructure/cache tests/application/llm_model -q
pytest tests/infrastructure tests/api -q          # 회귀
/verify-architecture
/verify-logging
```

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

**Dynamic** — 신규 포트 1개와 어댑터 1개를 아래단에 추가하되, 기존 레이어 구조·스키마는 유지한다.

### 7.2 Key Architectural Decisions

#### AD-1 ★ — 캐시를 2계층으로 가른다 (R-1 / D-9 대응)

```
L1  값 캐시 — CachePort 경유, Redis 교체 대상
    key    "llm_model:default"  /  "llm_model:name:<name>"
    value  LlmModel  (dataclass → JSON 직렬화 가능)
    TTL    settings.llm_model_cache_ttl_seconds (기본 60s)

L2  인스턴스 캐시 — 프로세스 로컬 전용, 절대 CachePort에 담지 않는다
    key    (llm_model.id, llm_model.updated_at, temperature)
    value  BaseChatModel
    이유   LangChain 객체는 직렬화 불가 (D-9)
```

**`updated_at`을 L2 키에 넣는 것이 핵심이다.** 관리자가 모델을 수정하면 L1이 갱신되며 새 `updated_at`이 들어오고, L2는 자동으로 다른 키가 되어 **별도 무효화 없이 자연 만료**된다. Redis 전환 시 L1만 어댑터를 갈아끼우면 되고 L2는 그대로 둔다.

#### AD-2 — 어댑터는 `BaseChatModel`이 아니라 provider 포트를 받는다

런타임 해석을 하려면 어댑터가 LLM 인스턴스를 생성자에 고정할 수 없다(D-3 공통 함정). 대신:

```python
class UtilityLLMProviderPort(ABC):
    @abstractmethod
    async def get(self, temperature: float = 0.0) -> BaseChatModel | None:
        """현재 유효한 보조 LLM. 해석 불가 시 None (호출부는 기존 경로로 낙하)."""
```

어댑터는 호출 시점에 `llm = await self._provider.get(temp)`를 받고, **직전 호출과 동일 객체이면 chain을 재사용**한다(R-3 완화). L2 캐시가 같은 객체를 돌려주므로 모델이 안 바뀌면 재조립이 일어나지 않는다.

#### AD-3 — 무효화 책임은 UseCase에 둔다

`update_llm_model_pricing_use_case.py:57`의 확립된 패턴을 따른다. 라우터가 아니라 UseCase가 `cache.delete(...)`를 의무 호출한다. D-8의 빈 구멍(`create`/`update`/`deactivate`)을 이번에 채운다.

#### AD-4 — TTL은 무효화의 대체가 아니라 안전장치다

단일 서버 현재는 명시적 무효화가 즉시 반영을 보장한다. TTL(기본 60초)은 **다중 워커/서버 전환 시 무효화가 전파되지 않는 구간**을 수렴시키기 위한 보험이다(R-2). Redis pub/sub이 붙으면 TTL을 늘릴 수 있다.

#### AD-5 — provider 파라미터는 additive, 기본값 `None`

R-5 완화이자 하위호환 계약. `None`이면 기존 `ChatOpenAI` 경로가 그대로 산다.

### 7.3 Clean Architecture Approach

```
domain/cache/interfaces.py          CachePort            (순수 ABC)
domain/llm/interfaces.py            +UtilityLLMProviderPort
        ↑ 의존
application/llm_model/resolver.py   LlmModelResolver     (repo + CachePort 조합)
        ↑ 주입
infrastructure/cache/in_memory_cache.py                  (CachePort 구현)
infrastructure/*/adapter.py         provider 포트에만 의존
        ↑ 조립
api/main.py                         구현체를 포트에 결선
```

어댑터(infrastructure)는 **포트(domain)에만** 의존한다. 구현 주입은 `main.py`가 하므로 infrastructure → application 참조는 발생하지 않는다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- 포트를 먼저 뚫고 구현을 나중에 교체 (`SelectionCachePort` 선례)
- 캐시 무효화는 UseCase가 의무 호출 (`update_llm_model_pricing_use_case` 선례)
- 어댑터는 앱 수명 싱글톤 (`main.py:4870` 주석)
- 부가 기능 조립 실패가 본 기능을 막지 않는다 (`_build_tool_filter()` 선례)
- config 하드코딩 금지, `print()` 금지

### 8.2 Conventions to Define/Verify

- **`CachePort` 저장 값은 JSON 직렬화 가능해야 한다** — docstring에 명문화 (R-1)
- 캐시 키 네임스페이스: `<도메인>:<식별자>` (예: `llm_model:default`)
- 폴백 로그 레벨은 **warning** (에러 아님 — 폴백이 정상 경로), `model_name`·`fallback_to` 포함

### 8.3 Environment Variables Needed

```bash
# 보조 LLM 모델명. 미설정이면 기본 모델(is_default=True)을 사용한다.
# NPU 전면 테스트 시 비워둘 것 → 모든 보조 호출이 기본 모델로 흐른다.
UTILITY_LLM_MODEL_NAME=

# LLM 모델 해석 캐시 TTL(초). 다중 워커 전환 시 무효화 미전파 구간의 안전장치.
LLM_MODEL_CACHE_TTL_SECONDS=60
```

### 8.4 Pipeline Integration

Phase 8(review) 대상. 신규 엔드포인트가 없어 Phase 4/6은 해당 없음.

---

## 9. Next Steps

| Step | 작업 | 산출물 |
|------|------|--------|
| **0** | **NPU vLLM tool-calling 사전 검증** — `/v1/chat/completions`에 `tools` 실어 확인 | R-4 판정. 실패 시 착수 전 설계 재검토 |
| 1 | Design 문서 작성 (`/pdca design`) | `docs/02-design/features/admin-default-llm-routing.design.md` |
| 2 | `CachePort` + `InMemoryCache` TDD | 포트 + 어댑터 + 테스트 |
| 3 | `LlmModelResolver` + `UtilityLLMProviderPort` TDD (2단 폴백 · L2 캐시) | 리졸버 + 테스트 |
| 4 | UseCase 4곳 무효화 배선 (D-8 구멍 포함) | UseCase diff + 테스트 |
| 5 | 패턴 C 4곳 배선 교체 (어댑터 무수정, 최저 리스크) | `main.py` diff |
| 6 | 패턴 B 2곳 (`intent`, `prompt_composer`) | 어댑터 + 테스트 |
| 7 | 패턴 A 3곳 (`hallucination`, `search_decision`, `qa_generator`) | 어댑터 + 테스트 |
| 8 | 회귀 + `/verify-architecture` + `/verify-logging` | 검증 리포트 |
| 9 | self-host 모델 등록 → **무재시작** 전환 실측 | NPU 전환 확인 |

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-08-29 | 배상규 | 최초 작성 — 배선 9곳/3패턴 조사, 부팅 시 주입 설계 |
| 0.2.0 | 2026-08-29 | 배상규 | 재시작 요구 철회 → 범용 `CachePort` + 런타임 리졸버로 전환. LangChain 직렬화 불가(D-9) 발견에 따른 2계층 캐시(AD-1), 무효화 구멍(D-8), 기존 중복 3건(D-6) 반영 |
