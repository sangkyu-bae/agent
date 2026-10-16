# judgment-backend Plan Document

> **Summary**: Jev(TypeSafe 호스팅)와 AnyJev(폐쇄망 오픈모델)를 같은 포트 뒤에 두고 `.env`/DI로 갈아타는 "타입 판정(typed judgment)" 모듈 + 첫 소비 지점(`search_decision`) 결선
>
> **Feature**: judgment-backend
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-10-15
> **Status**: Plan
> **Type**: 신규 공용 모듈(포트 + 어댑터 2종 + 팩토리) + 소비 지점 1곳 교체(폴백 유지)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 백엔드의 "예/아니오·N지선다" 판정 15곳 이상이 전부 범용 LLM `with_structured_output`으로 구현돼 있다(`search_decision`, `relevance_adapter`, `prompt_guard/llm_judge`, `visualization/llm_classifier` 등). 판정 1회에 생성 모델 비용·지연을 그대로 치르고, 확률·confidence가 없어 임계값 정책을 코드가 가질 수 없다. Jev 같은 판정 전용 모델을 쓰고 싶어도 어댑터가 ChatOpenAI에 묶여 있고, 폐쇄망에서는 Jev 호스팅 API 자체에 닿을 수 없다. |
| **Solution** | 프레임워크 독립 `judgment` 모듈을 만든다. ① `domain/judgment/`에 `JudgmentPort`(state + Noul/Choice 질문 → 확률 분포)와 VO, ② `infrastructure/judgment/`에 Jev 어댑터(`typesafe-sdk`)와 AnyJev 어댑터(`anyjev.serve` HTTP), ③ `JUDGMENT_BACKEND=jev\|anyjev\|off` 한 키로 고르는 팩토리(off·조립 실패 시 `None`). 첫 소비 지점 `search_decision`을 Noul 1개로 교체하되, 백엔드가 없거나 실패하면 **기존 LLM 어댑터로 폴백**해 동작이 바뀌지 않게 한다. |
| **Function/UX Effect** | 사용자 화면 변화 0, API 스키마 변화 0. 운영자는 `.env` 한 줄로 Jev ↔ AnyJev ↔ 기존 LLM을 바꾼다. 판정이 성공하면 웹검색 필요 여부가 생성 LLM 대신 판정 모델 1회로 결정되고, 실패하면 지금과 동일하게 동작한다. 폴백 발생은 warning 로그로 남아 운영자가 추적할 수 있다. |
| **Core Value** | 판정 백엔드를 **교체 가능한 데이터(설정)** 로 만들어 코어가 특정 벤더·망 환경에 묶이지 않게 한다. 이후 소비 지점(RAG 관련성·인젝션 판정·차트 분류)은 같은 포트에 Noul/Choice 질문만 얹으면 된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 판정형 LLM 호출이 전부 생성 모델에 묶여 있어 판정 전용 모델(Jev)로 못 바꾸고, 폐쇄망에서는 대체(AnyJev)가 필요한데 포트가 없다 |
| **WHO** | 1차: 운영자/배포 담당 — `.env` 한 줄로 백엔드 교체. 2차: 후속 개발자 — 포트에 질문만 얹어 다음 소비 지점 교체. 3차: 최종 사용자 — 동작 불변(폴백) |
| **RISK** | AnyJev HTTP 계약(`/v1/decide` 요청·응답 스키마)이 미검증이고 두 백엔드 모두 지금 실호출 불가 → 어댑터는 전송 계층 픽스처로 계약 고정, 실호출은 이월 체크리스트 |
| **SUCCESS** | `JUDGMENT_BACKEND=off`에서 기존 테스트 전량 무변경 통과, `jev`/`anyjev`에서 search_decision이 Noul 확률+임계값으로 결정, 백엔드 실패 시 폴백 100%(LLM 어댑터 호출 단언), AST 경계 테스트 통과, 회귀 `FAILED` diff 0 |
| **SCOPE** | 이번: 포트(Noul+Choice) + Jev/AnyJev 어댑터 + 팩토리 + config + search_decision 교체·폴백 + 테스트. 제외: Score, 인프로세스 AnyJev, 다른 소비 지점, 관리자 UI, DB 레지스트리 |

---

## 1. Overview

### 1.1 Purpose

"이 질문에 대한 답은 예인가", "이 N개 중 무엇인가"를 묻는 판정 호출을 **타입이 정해진 포트** 하나로 모으고, 그 뒤에 Jev(호스팅)와 AnyJev(폐쇄망) 어댑터를 둔다. 백엔드 선택은 설정값 하나로 하고, 어느 쪽도 못 쓰는 환경에서는 지금의 LLM 경로가 그대로 남는다. 첫 소비 지점으로 `search_decision`(엑셀 분석 답변에 웹검색 보강이 필요한가)을 교체해 "포트가 실제로 통하는가"를 결선까지 확인한다.

### 1.2 Background

- **판정 호출의 현재 모양.** 탐색 결과 판정형 호출은 거의 전부 `llm.with_structured_output(PydanticModel)` 체인이다. 대표 예: `infrastructure/search_decision/adapter.py:25 LLMSearchDecisionAdapter.decide`(Noul 성격), `infrastructure/research_agent/relevance_adapter.py:15`(문서별 관련성), `infrastructure/prompt_guard/llm_judge.py:35`(인젝션 판정), `infrastructure/visualization/llm_classifier.py:27`(차트 유형 Choice). 모두 포트(ABC/Protocol)를 갖고 있어 어댑터만 바꾸면 된다.
- **Jev.** TypeSafe의 System One 모델. `POST /v1/systemone`에 `state`(문자열/객체)와 `questions{noul|choice|score}`를 보내면 `noul`은 0~1 확률, `choice`는 선택값+`probabilities`+`confidence`를 돌려준다. Python SDK `typesafe-sdk`는 `AsyncTypeSafeClient(api_key, base_url, model, timeout, retry, http_client)`를 제공하고 `TYPESAFE_API_KEY`/`TYPESAFE_BASE_URL`/`TYPESAFE_DEFAULT_MODEL` 환경변수를 읽는다. 모델 별칭 `jev-latest`(현재 1.13), `jev-preview`(1.14). 한국어 성능은 공식 문서에 명시가 없다(jaggedness 문서만 존재).
- **AnyJev.** TypeSafe 제품이 아니라 Nokia Applied Research의 Apache-2.0 라이브러리. 오픈 모델(Tacit-9B 등 자체 증류본, 또는 Qwen3 류 훈련 없이)을 transformers/vLLM로 돌려 Jev식 typed decision을 낸다. 인프로세스 API(`Tacit.decide(state, question, options, kind=choice|yes_no|score)` → `{"answer", "probs", "route"}`)와 HTTP 서버(`python -m anyjev.serve` → `POST /v1/decide`, `GET /v1/stats`, 인증 없음, 127.0.0.1 바인딩)가 있다. **TypeSafe API와 호환이 아니다** — 응답 shape가 다르고 Noul은 로드맵. 따라서 우리 쪽 공통 VO로 정규화해야 하고, Noul은 2지 선택(yes/no)으로 에뮬레이션한다.
- **재사용할 기반.** `<feature>_provider/_model_name/_enabled` 평면 config 관행(`config.py`), `main.py` 단일 조립 + 킬스위치 off·조립 실패 시 `None` 반환 팩토리(`get_prompt_guard`, tool_filter), 포트/어댑터 짝(`domain/search_decision/interfaces.py` ↔ `infrastructure/search_decision/adapter.py`), enum+`from_string` 팩토리(`embeddings/embedding_factory.py`), AST import 경계 테스트(`tests/infrastructure/prompt_guard/test_module_boundaries.py`), `pytest -m llm` 실호출 마커.
- **사용자 결정(2026-10-15).** ① 범위는 모듈 + 소비 지점 1곳 결선, ② 첫 소비 지점은 `search_decision`, ③ AnyJev는 별도 HTTP 서비스로만 지원(인프로세스 제외), ④ 백엔드 실패·미설정 시 기존 LLM 경로로 폴백, ⑤ 프리미티브는 Choice + Noul(Score는 예약만), ⑥ Jev는 `typesafe-sdk` 사용, ⑦ 지금은 두 백엔드 모두 실호출 불가 → 픽스처 계약 테스트 + 실호출 이월, ⑧ 임계값은 config 키 1개(기본 0.5).

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` — 특화 vs 일반화 충돌 시 일반화 우선(판정 백엔드는 코어 일반 모듈, 벤더 특성은 어댑터에 격리)
- 위키(필수 참조):
  - `docs/wiki/backend/patterns/detachable-module-seam.md` — 킬스위치 off·조립 실패 시 팩토리 None, "off = 없던 상태", AST 경계 테스트
  - `docs/wiki/conventions/config-single-source-at-consumption.md` — 새 config 키는 소비 지점 파일:라인을 docstring에 명기, 같은 의미의 값 이원화 금지
  - `docs/wiki/backend/patterns/degradation-vs-failure-boundary.md` — 판정 실패는 degraded(폴백), 흡수는 어댑터 한 곳
  - `docs/wiki/backend/patterns/grounding-rewrite-loop.md` — 판정 모델 벤치는 양성 대조군 필수(실호출 가능해지면 적용)
  - `docs/wiki/backend/patterns/structured-output-strict-schema.md` — fake만으로 완료 처리 금지(실호출 1회가 DoD) → 이번엔 불가하므로 **명시적 이월**
  - `docs/wiki/conventions/explicit-gap-carryover.md` — 미달 항목은 후속 소형 사이클로 회수
  - `docs/wiki/conventions/false-green-quality-gates.md` — 회귀는 정렬 `FAILED` 목록 diff
  - `docs/wiki/backend/patterns/structured-logger-warning-exception.md` — 폴백 경로 warning은 `exception=e`
- 외부 문서: TypeSafe API `https://docs.typesafe.ai/api.md`, Python SDK 클라이언트 `https://docs.typesafe.ai/sdk/python/api/clients/async.md`, 프리미티브 `https://docs.typesafe.ai/primitives.md`, 모델 `https://docs.typesafe.ai/models.md`, AnyJev `https://github.com/nokia-applied-research/anyjev`
- 선례 Plan: `docs/archive/2026-10/prompt-guard/prompt-guard.plan.md`(포트 + 판정기 + 킬스위치 + 배선), `docs/archive/2026-08/admin-default-llm-routing/`(provider 교체·지연 생성)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1 도메인 모듈** `src/domain/judgment/`: 질문 VO(`NoulQuestion(instructions)`, `ChoiceQuestion(instructions, criteria: 순서 있는 라벨→설명)`), 답 VO(`NoulAnswer(probability)`, `ChoiceAnswer(choice, probabilities, confidence)`), 요청/응답 VO(`JudgmentRequest(state, questions)`, `JudgmentResponse(answers, model, backend)`), `JudgmentBackendKind` enum(`jev`/`anyjev`/`off`), 포트 `JudgmentPort.judge(request) -> JudgmentResponse`. Score는 enum/타입 자리만 두고 구현하지 않는다
- [ ] **S2 Jev 어댑터** `src/infrastructure/judgment/jev/`: `typesafe-sdk` `AsyncTypeSafeClient` 래핑. `api_key`·`base_url`·`model`·`timeout`을 **명시 인자**로 주입(환경변수 암묵 의존 금지), `http_client` 주입 가능(테스트는 `httpx.MockTransport`). SDK 응답 → 도메인 VO 변환
- [ ] **S3 AnyJev 어댑터** `src/infrastructure/judgment/anyjev/`: `httpx.AsyncClient`로 `POST {base_url}/v1/decide`. Choice는 그대로, Noul은 `options=["yes","no"]` 2지 선택으로 보내 `probs["yes"]`를 확률로 변환. 요청/응답 스키마는 Design에서 README·`anyjev.serve` 소스로 확정
- [ ] **S4 팩토리** `src/infrastructure/judgment/factory.py` + `main.py get_judgment_backend()`: `judgment_backend=off` → `None`, 필수 설정 누락(Jev 키 없음·AnyJev URL 없음)·SDK 미설치·조립 예외 → `None` + `logger.warning(..., exception=e)`. 앱 수명 1회 조립(`_judgment_backend_built` 플래그), 클라이언트는 앱 수명 싱글턴
- [ ] **S5 설정** `config.py`: `judgment_backend: str = "off"`, `judgment_timeout_seconds: float = 3.0`, `typesafe_api_key: str | None`, `typesafe_base_url: str | None`, `typesafe_model: str = "jev-latest"`, `anyjev_base_url: str | None`, `anyjev_model: str | None`, `search_decision_judgment_threshold: float = 0.5`. 각 키 docstring에 소비 지점 명기. `.env.example` 갱신
- [ ] **S6 소비 지점 교체** `src/infrastructure/search_decision/judgment_adapter.py`: `JudgmentSearchDecisionAdapter(SearchDecisionInterface)` — state `{question, analysis_text}` + Noul 1개 → `probability >= threshold`로 `WebSearchDecision(needs_web_search, reason="judgment p=0.xx")`. 생성자에 `fallback: SearchDecisionInterface`(기존 `LLMSearchDecisionAdapter`)를 받아 포트 예외·타임아웃·응답 누락 시 폴백 호출. `main.py:1144` 조립에서 백엔드가 `None`이면 기존 어댑터 그대로
- [ ] **S7 관측** 판정 1회당 debug 로그(backend, model, latency_ms, probability), 폴백 시 warning(`exception=e`, backend, request_id). 원문 state는 로그에 남기지 않는다
- [ ] **S8 의존성** `pyproject.toml` `[project.optional-dependencies] judgment = ["typesafe-sdk>=X"]`(버전은 Design에서 고정). AnyJev는 기존 `httpx`만 사용(추가 의존 0)
- [ ] **S9 테스트** 도메인 VO 검증, 두 어댑터 전송 계층 픽스처 계약 테스트(정상·4xx·5xx·타임아웃·스키마 불일치), 팩토리(off/누락/미설치/예외 → None), search_decision 어댑터(임계값 경계·폴백 시 LLM 호출 단언·성공 시 LLM 미호출 단언), AST 경계 테스트, `pytest -m llm` 실호출 스모크 2종(환경변수 없으면 skip)

### 2.2 Out of Scope (후속 사이클)

- Score 프리미티브 구현(랭킹·리랭크 용도) — enum 자리만
- AnyJev 인프로세스 모드(transformers/vLLM 직접 로드, torch 의존)
- `search_decision` 이외 소비 지점 교체(`relevance_adapter`, `prompt_guard/llm_judge`, `visualization/llm_classifier`, 빈 `infrastructure/reranker/`)
- 판정 모델 DB 레지스트리·관리자 화면·에이전트별 토글(현재 `llm_model` 테이블은 생성 모델 전용이며 건드리지 않는다)
- 백엔드별 임계값 분리·캘리브레이션 보정(실호출 벤치가 가능해진 뒤 결정)
- 이미지 입력(Jev `assets`), 장문 컨텍스트 헤더(262k)
- 두 백엔드 실호출 벤치(양성 대조군 포함) — 환경 확보 후 이월 체크리스트로

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `domain/judgment/`는 표준 라이브러리·pydantic·자기 패키지 외 아무것도 import하지 않는다(LangChain·typesafe-sdk·httpx 금지). AST 테스트로 고정 | High | Pending |
| FR-02 | `JudgmentPort.judge(JudgmentRequest) -> JudgmentResponse`는 같은 state에 대한 여러 질문을 한 번에 받는다(병렬 질문). 답은 질문 id로 매핑된다 | High | Pending |
| FR-03 | `NoulAnswer.probability`는 0.0~1.0, `ChoiceAnswer.probabilities`는 criteria 라벨 전부를 키로 갖고 합이 1±0.01. 어댑터가 이를 보장하며 위반 시 `JudgmentProtocolError`를 던진다(폴백 대상) | High | Pending |
| FR-04 | Jev 어댑터는 `typesafe-sdk` 클라이언트를 `api_key`·`base_url`·`model`·`timeout` 명시 인자로 만들고, 환경변수에 암묵 의존하지 않는다. `http_client`(httpx) 주입을 허용한다 | High | Pending |
| FR-05 | Jev 어댑터는 SDK 응답의 `model` 필드(실제 버전 id)를 `JudgmentResponse.model`에 담는다 | Medium | Pending |
| FR-06 | AnyJev 어댑터는 `POST {anyjev_base_url}/v1/decide`를 호출하고, Noul 질문은 `kind:"noul"`로 보내 응답 `probs`의 `Yes` 확률을 `NoulAnswer`로 돌려준다(Design D1 정정 — AnyJev가 noul을 네이티브 지원함을 소스로 확인, 에뮬레이션 불필요). Choice는 criteria 라벨을 `options`로 보낸다 | High | Pending |
| FR-07 | AnyJev 응답에 `probs`가 없거나 라벨이 빠지면 `JudgmentProtocolError`(폴백). `route`/`level` 같은 부가 필드는 `JudgmentResponse.extra`에 보존만 한다 | Medium | Pending |
| FR-08 | 두 어댑터 모두 `judgment_timeout_seconds`를 적용하고, 타임아웃·연결 실패·4xx/5xx·스키마 불일치를 `JudgmentError` 계열로 정규화해 던진다(예외를 삼키지 않는다 — 삼키는 곳은 소비 지점 어댑터 한 곳) | High | Pending |
| FR-09 | 팩토리는 `judgment_backend` 값으로 어댑터를 고른다. `off`·알 수 없는 값·필수 설정 누락·SDK 미설치·조립 예외 → `None` + warning 1회. 조립은 앱 수명 1회 | High | Pending |
| FR-10 | `JudgmentSearchDecisionAdapter.decide()`는 Noul 1개로 판정하고 `probability >= search_decision_judgment_threshold`면 `needs_web_search=True`. `reason`에 백엔드·확률을 짧게 남긴다 | High | Pending |
| FR-11 | 판정 백엔드가 `JudgmentError`를 던지면 주입된 `fallback.decide()`를 그대로 호출해 반환하고 warning(`exception=e`)을 남긴다. 판정 성공 시 fallback은 호출하지 않는다 | High | Pending |
| FR-12 | `main.py`는 백엔드가 `None`이면 `LLMSearchDecisionAdapter`를 지금처럼 조립하고, 있으면 `JudgmentSearchDecisionAdapter(backend, fallback=LLMSearchDecisionAdapter(...))`로 감싼다. `ExcelAnalysisWorkflow`와 `SearchDecisionInterface` 시그니처는 변경하지 않는다 | High | Pending |
| FR-13 | 판정 프롬프트(instructions)는 어댑터가 아니라 소비 지점 모듈(`search_decision`)이 소유한다 — 백엔드가 바뀌어도 질문은 같다 | Medium | Pending |
| FR-14 | 로그에 state 원문을 남기지 않는다. 길이·SHA-256 앞 12자·확률·latency만 기록 | Medium | Pending |
| FR-15 | `.env.example`에 신규 키 8개와 주석(어느 백엔드에 필요한지)을 추가한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | `judgment_backend=off`(기본)에서 기존 테스트 전량 **무수정** 통과, 동작·로그 변화 0 | 전체 스위트 + 정렬 `FAILED` 목록 diff |
| 가용성 | 백엔드 장애 시 excel 분석 흐름 중단 0(폴백) | 타임아웃·5xx·스키마 불일치 주입 테스트에서 fallback 호출 단언 |
| 성능 | 판정 호출 타임아웃 기본 3초(`prompt_guard_judge_timeout_seconds`와 동일 수준), 실측 지연은 이월 | 타임아웃 테스트 |
| 의존성 | `typesafe-sdk`는 optional extra. 미설치 환경에서 앱 기동·전체 테스트 통과 | 팩토리 ImportError 테스트, CI 기본 설치본으로 실행 |
| 아키텍처 | domain→infrastructure 0, `judgment` 패키지를 import하는 외부 파일은 `main.py`·`search_decision/judgment_adapter.py`·테스트뿐 | AST 경계 테스트 + `_DECLARED_CONSUMERS` 목록 |
| 보안 | API 키는 로그·예외 메시지에 노출 금지. AnyJev 서버는 인증이 없으므로 `anyjev_base_url`은 내부망 주소만 허용(문서화) | 로그 테스트, `.env.example` 주석 |
| 로깅 | `LoggerInterface`, print 금지, 폴백 warning에 `exception=e` | 코드 리뷰 + 로그 테스트 |
| 회귀 | master 상시 실패 목록 대비 `FAILED` diff 0 | 정렬된 FAILED 목록 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-15 구현 및 테스트 통과(TDD: Red→Green→Refactor)
- [ ] 두 어댑터 전송 계층 픽스처 테스트: 정상·4xx·5xx·타임아웃·스키마 불일치 5케이스 × 2백엔드 × Noul/Choice
- [ ] 팩토리 테스트: `off`/미지정 키/미설치/조립 예외 4케이스 → `None`, `jev`/`anyjev` 정상 조립 2케이스
- [ ] search_decision 테스트: 임계값 경계(0.49/0.50/0.51), 성공 시 fallback 미호출, 실패 3종 시 fallback 호출·결과 그대로 반환
- [ ] `judgment_backend=off`에서 기존 테스트 전량 변경 없이 통과(탈착 계약)
- [ ] AST 경계 테스트 통과, `_DECLARED_CONSUMERS` 근거 주석 포함
- [ ] `pytest -m llm` 스모크 2종 작성(`TYPESAFE_API_KEY`·`ANYJEV_BASE_URL` 없으면 skip) — **실행은 이월**, `docs/wiki/ops/e2e-carryover-checklist.md`에 항목 등록은 사용자 `/wiki update` 시
- [ ] 회귀: `uv run python -m pytest` 정렬 FAILED 목록이 master 기준과 동일
- [ ] Design 문서(`judgment-backend.design.md`): AnyJev `/v1/decide` 요청·응답 스키마 확정, `typesafe-sdk` 버전 고정, search_decision Noul instructions 확정

### 4.2 Quality Criteria

- [ ] 신규 모듈 단위 테스트 커버리지 ≥ 90%(domain 100%)
- [ ] `verify-architecture`·`verify-logging`·`verify-tdd` 스킬 통과
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| AnyJev `/v1/decide` HTTP 스키마가 README에 없다(Python API만 문서화) | High | High | Design 단계에서 `anyjev.serve` 소스를 직접 읽어 확정. 확정 불가 시 어댑터 요청 빌더를 전략 객체로 분리해 스키마만 교체 가능하게 |
| 두 백엔드 모두 지금 실호출 불가 → 픽스처가 실제와 어긋날 수 있다 | High | Medium | 픽스처는 공식 문서 예시 응답 그대로 사용. `-m llm` 스모크를 작성해 두고 실행만 이월. 위키 규칙("fake만으로 완료 금지")에 대한 **명시적 예외**로 기록 |
| Jev 한국어 판정 품질 미확인(공식 문서에 언어 명시 없음) | Medium | Medium | 폴백이 있어 품질 저하가 흐름을 깨지 않음. 실호출 가능 시 양성 대조군 벤치로 임계값 조정 |
| Jev와 AnyJev 확률 캘리브레이션이 달라 같은 임계값이 다른 결과를 낸다 | Medium | High | 이번엔 키 1개로 시작(사용자 결정). 백엔드별 분리는 벤치 후 additive로 추가 |
| `typesafe-sdk` 의존성이 기존 `httpx` 버전과 충돌 | Medium | Low | optional extra로 격리, `uv lock` 확인. 충돌 시 httpx 직접 호출로 전환(어댑터 교체만) |
| AnyJev 서버 무인증·127.0.0.1 기본 바인딩 → 운영 노출 시 보안 구멍 | Medium | Low | 내부망 주소만 허용을 문서화, URL 스킴·호스트 검증은 Design에서 결정 |
| Noul→yes/no Choice 에뮬레이션이 Jev의 Noul과 의미가 다를 수 있다(2지 분포 vs 단일 조건 확률) | Low | Medium | 어댑터 docstring에 명시, `JudgmentResponse.backend`로 소비 지점이 구분 가능 |
| 기본값 `off`라 배선 후에도 운영 미활성 상태로 남는다(intent-analyzer 전례) | Low | High | 의도된 결정(배포와 활성화 분리). 활성화 절차를 Report의 이월 항목으로 명시 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/domain/judgment/` | 신규 패키지 | 포트·VO·enum·예외 |
| `src/infrastructure/judgment/{jev,anyjev}/`, `factory.py` | 신규 패키지 | 어댑터 2종 + 팩토리 |
| `src/infrastructure/search_decision/judgment_adapter.py` | 신규 파일 | `SearchDecisionInterface` 구현(판정 + 폴백) |
| `src/config.py` | Config | 신규 키 8개 추가(기존 키 변경 0) |
| `src/api/main.py` | DI | `get_judgment_backend()` 추가, `search_decision` 조립 1곳(1144행 부근) 조건 분기 |
| `pyproject.toml` | 의존성 | optional extra `judgment` 추가 |
| `.env.example` | 문서 | 신규 키 8개 |
| `tests/domain/judgment/`, `tests/infrastructure/judgment/`, `tests/infrastructure/search_decision/` | 테스트 | 신규 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `SearchDecisionInterface` | READ(호출) | `application/workflows/excel_analysis_workflow.py:236 _search_decision.decide()` | None — 시그니처·반환 타입 불변 |
| `LLMSearchDecisionAdapter` | CREATE | `api/main.py:1144` | Needs verification — 백엔드 있을 때 래핑, 없을 때 그대로 |
| `ExcelAnalysisWorkflow` 인스턴스 2개 | CREATE | `api/main.py:1161`(standalone), `:1183`(supervisor 경로) | None — 같은 `search_decision` 객체 주입 |
| `settings` | READ | 전역 | None — 신규 키만 추가, 기본 `off` |
| `pyproject` 기본 설치본 | INSTALL | CI·개발 환경 | None — extra 미설치 시 팩토리가 ImportError를 None으로 흡수 |
| `UtilityLLMProvider` | READ | 기존 `LLMSearchDecisionAdapter` 폴백 경로 | None — 폴백 어댑터가 기존대로 사용 |

### 6.3 Verification

- [ ] 위 소비자 전부 `judgment_backend=off`에서 기존 테스트 무수정 통과로 검증
- [ ] 인증·권한 변경 없음(API 엔드포인트 추가 0)
- [ ] 스키마·DB 변경 없음(마이그레이션 0)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | SaaS MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 기존 idt Thin DDD | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 포트 위치 | domain ABC / Protocol | `domain/judgment/interfaces.py` ABC | `search_decision`·`vector` 등 기존 다수 포트와 동일, AST 테스트로 미선언 메서드 호출 방지 |
| 백엔드 선택 | enum+factory / 플러그인 레지스트리 | enum(`jev`/`anyjev`/`off`) + factory | `EmbeddingFactory` 관행, 2종이라 레지스트리는 과도 |
| Jev 클라이언트 | typesafe-sdk / httpx 직접 | `typesafe-sdk`(optional extra, 명시 인자) | 재시도·압축·타입 응답 내장(사용자 결정). 환경변수 암묵 의존은 금지해 테스트 가능성 확보 |
| AnyJev 연결 | HTTP 서버 / 인프로세스 | HTTP(`anyjev.serve`)만 | torch 의존을 idt/에 넣지 않음, API 서버에 GPU 불필요(사용자 결정) |
| Noul on AnyJev | 미지원 → 예외 / yes-no Choice 에뮬레이션 | 에뮬레이션 | 포트 계약을 백엔드 능력 차이로 깨지 않기 위해 |
| 폴백 위치 | 포트 내부 / 소비 지점 어댑터 | 소비 지점 어댑터(`JudgmentSearchDecisionAdapter`) | 포트는 예외를 정직하게 던지고, "쓸 수 있는 결과"(기존 LLM 판정)를 아는 곳이 흡수(degradation 경계 규칙) |
| 폴백 대상 | 보수 기본값 / 기존 LLM 어댑터 | 기존 `LLMSearchDecisionAdapter` | "없던 상태"=현재 동작(사용자 결정) |
| 임계값 | 하드코딩 / config 1키 / 백엔드별 | config 1키 `search_decision_judgment_threshold=0.5` | 소비 지점 docstring 명기, 분리는 벤치 후 additive |
| 기본값 | on / off | `off` | 실호출 미검증 상태이므로 배포와 활성화 분리 |
| 질문 소유 | 어댑터 / 소비 지점 | 소비 지점 모듈 상수 | 백엔드 교체 시 질문 불변, 프롬프트 SoT 1곳 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (idt Thin DDD)

src/domain/judgment/
  interfaces.py      JudgmentPort(ABC)
  value_objects.py   NoulQuestion, ChoiceQuestion, NoulAnswer, ChoiceAnswer,
                     JudgmentRequest, JudgmentResponse, JudgmentBackendKind
  exceptions.py      JudgmentError, JudgmentTimeoutError, JudgmentProtocolError,
                     JudgmentUnavailableError
src/infrastructure/judgment/
  factory.py         build_judgment_backend(settings, logger) -> JudgmentPort | None
  jev/adapter.py     JevJudgmentAdapter (typesafe-sdk)
  jev/mapping.py     SDK 응답 → VO
  anyjev/adapter.py  AnyJevJudgmentAdapter (httpx)
  anyjev/mapping.py  Noul→yes/no 변환, probs → VO
src/infrastructure/search_decision/
  judgment_adapter.py  JudgmentSearchDecisionAdapter(backend, fallback, threshold)
  questions.py         SEARCH_DECISION_NOUL (instructions 상수)
src/api/main.py
  get_judgment_backend()  — 1회 조립, None 폴백
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙(레이어·40줄·중첩·config 하드코딩 금지·print 금지)
- [x] `idt/docs/rules/logging.md`, `testing.md`
- [x] 위키 패턴(탈착형 이음매, config 단일 출처, degraded 경계)
- [x] pytest `-m llm` 마커, `uv run python -m pytest`
- [ ] ESLint/Prettier/tsconfig — 해당 없음(백엔드 전용)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Naming | exists | 패키지명 `judgment`, 어댑터 `<Backend>JudgmentAdapter`, 예외 `Judgment*Error` | High |
| Folder structure | exists | §7.3 구조 | High |
| Environment variables | exists(평면 config) | §8.3 신규 키 8개, docstring에 소비 지점 명기 | High |
| Error handling | exists(degraded 경계) | 포트는 던지고 소비 지점 어댑터만 삼킨다 | High |
| Optional dependency | 없음(선례 미확인) | `[project.optional-dependencies] judgment` + ImportError→None | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `JUDGMENT_BACKEND` | `jev` / `anyjev` / `off`(기본) | Server | ☐ |
| `JUDGMENT_TIMEOUT_SECONDS` | 판정 호출 타임아웃(기본 3.0) | Server | ☐ |
| `TYPESAFE_API_KEY` | Jev 인증 키 | Server(jev) | ☐ |
| `TYPESAFE_BASE_URL` | Jev API 루트(기본 SDK 기본값) | Server(jev) | ☐ |
| `TYPESAFE_MODEL` | Jev 모델 id/별칭(기본 `jev-latest`) | Server(jev) | ☐ |
| `ANYJEV_BASE_URL` | `anyjev.serve` 주소(내부망만) | Server(anyjev) | ☐ |
| `ANYJEV_MODEL` | 서버가 복수 모델을 제공할 때 선택(옵션) | Server(anyjev) | ☐ |
| `SEARCH_DECISION_JUDGMENT_THRESHOLD` | Noul 확률 → bool 임계값(기본 0.5) | Server | ☐ |

### 8.4 Pipeline Integration

해당 없음(기존 프로젝트 기능 단위 PDCA).

---

## 9. Next Steps

1. [ ] Design 문서 작성(`judgment-backend.design.md`) — AnyJev `/v1/decide` 스키마 확정(소스 확인), `typesafe-sdk` 버전 고정, VO 필드·예외 계층·search_decision Noul instructions 확정, 3안 비교
2. [ ] 사용자 검토·승인
3. [ ] 구현(TDD): module-1 domain → module-2 어댑터 2종 → module-3 팩토리·config → module-4 search_decision 결선
4. [ ] 실호출 스모크·벤치는 환경 확보 후 후속 소형 사이클로 회수

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-15 | 초안 — 사용자 결정 8건 반영 | 배상규 |
