# intent-analyzer Planning Document

> **Summary**: 사용자 메시지의 의도를 구조화 객체로 판정하는 **탈착 가능한 독립 모듈**. 기존 실행 경로에는 배선하지 않고, 도메인 포트 + 노드 팩토리 + 독립 API로만 출하한다.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-08-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 의도 판정 로직이 `multi_query.classify` · `chart_router` · `supervisor` 프롬프트에 각각 흩어져 있어, 새 경로에 의도 분석을 붙이려면 매번 다시 만든다. 재사용 가능한 단일 모듈이 없다. |
| **Solution** | `domain/intent` 포트 + `infrastructure/intent` LLM 어댑터 + `application/intent` UseCase·노드 팩토리 + 독립 API. **분류 체계(라벨)는 호출자가 주입**하므로 모듈은 라벨 의미를 모른다 → 결합도 0. |
| **Function/UX Effect** | 이번 사이클에선 사용자 화면 변화 **없음**(기존 경로 무변경). P2가 나중에 임의 그래프·임의 부서 라벨로 의도 분석을 꽂을 수 있는 기반이 생긴다. |
| **Core Value** | "끼웠다 뺐다" — 주입 안 하면 그래프에 노드 자체가 추가되지 않고, LLM이 죽어도 `degraded=True`만 반환해 본 흐름을 막지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 의도 판정이 3곳에 중복 산재 — 재사용 가능한 단일 모듈 부재 |
| **WHO** | P2 (에이전트 소유자, 주인공) — 부서별 라벨로 자기 그래프에 꽂는 사람. 1차 소비자는 개발자(백엔드) |
| **RISK** | LLM 전용이라 요청당 비용·지연 발생 / 라벨 목록 프레이밍이 과차단을 유발한 선례(위키 계약 2)와 구조적 긴장 |
| **SUCCESS** | 기존 경로 회귀 0건 · 마이그레이션 0건 · domain→infra import 0건 · LLM 실패 3종 모두 degraded 반환 |
| **SCOPE** | 모듈 + 독립 API만. 기존 supervisor/general_chat/multi_query 배선은 **다음 사이클** |

---

## 1. Overview

### 1.1 Purpose

사용자 요청/질문이 들어왔을 때 **무엇을 원하는가**를 구조화된 객체로 판정하는 단일 모듈을 만든다.
핵심 제약은 기능 자체가 아니라 **결합 형태**다 — 어느 그래프에든 꽂을 수 있고, 빼도 아무것도 깨지지 않아야 한다.

### 1.2 Background

현재 의도 판정에 해당하는 로직은 세 곳에 서로 다른 모양으로 존재한다.

| 위치 | 판정 대상 | 재사용 가능? |
|------|-----------|-------------|
| `src/domain/multi_query/policy.py` → `MultiQueryPolicy.classify` | simple / complex / ambiguous | ✗ 검색 전용 |
| `src/application/visualization/chart_router.py` | visualize / text | ✗ 시각화 전용 |
| `src/domain/search_decision/` | 웹검색 필요 여부 | ✗ 엑셀분석 전용 |
| supervisor 프롬프트 (`supervisor_nodes.py`) | 어느 워커로 위임 | ✗ 프롬프트에 내장 |

셋 다 **판정 대상이 코드에 하드코딩**되어 다른 곳에 못 쓴다.
동시에 이 세 모듈은 이미 좋은 **구조 관례**를 확립해 두었다 —
`domain/{x}/interfaces.py`(포트) + `schemas.py`(VO) + `infrastructure/{x}/adapter.py`(LLM 구현) + 실패 시 보수적 폴백.

본 기능은 그 관례의 **4번째 인스턴스**이되, 유일하게 **판정 대상(라벨)까지 외부 주입**으로 뽑아낸 버전이다.
이것이 재사용성의 전부다.

### 1.3 Related Documents

- 아키텍처 조감도: `docs/wiki/backend/architecture-overview.md` (실행 경로 절단면 4종)
- **Supervisor 그래프 계약 3종**: `docs/wiki/backend/patterns/supervisor-graph-contracts.md` ★ 리스크 R2·R5의 근거
- 계약 확장 관례: `docs/wiki/conventions/additive-contract-extension.md`
- 페르소나·스코프 기준: `docs/USER-SCENARIOS.md` (P2 주인공, 일반화 > 여신 특화)
- 코딩 규칙: `idt/CLAUDE.md`, `idt/docs/rules/logging.md`, `idt/docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `domain/intent` — 포트 1개(`IntentAnalyzerInterface`), VO 4개, 정규화 Policy(순수함수)
- [ ] `infrastructure/intent` — `LLMIntentAnalyzerAdapter` (LangChain `with_structured_output`)
- [ ] `application/intent` — `AnalyzeIntentUseCase` + `create_intent_node()` 노드 팩토리
- [ ] `interfaces/schemas/intent.py` + `api/routes/intent_router.py` — `POST /api/v1/intent/analyze`
- [ ] `api/main.py` 라우터 등록 및 DI (신규 추가만)
- [ ] TDD: domain policy 단위테스트 + UseCase/노드 테스트(LLM fake) + API 통합테스트
- [ ] 구조화 로깅 (label / confidence / degraded / latency_ms)

### 2.2 Out of Scope

- **기존 실행 경로 배선** — supervisor 그래프, general_chat, multi_query 어디에도 꽂지 않는다. 코드 변경 0건.
- **DB 저장·마이그레이션** — 판정 결과를 `ai_run_*`에 기록하지 않는다. 마이그레이션 파일 0건.
- **라벨의 DB 설정화·빌더 UI** — 라벨은 호출 시 인자로만 받는다. 화면 작업 없음.
- **기존 3개 판정 모듈(multi_query / chart_router / search_decision) 통합·대체** — 책임이 겹쳐 보여도 이번엔 건드리지 않는다.
- **휴리스틱 사전 필터** — LLM 전용으로 확정. (근거: §7.2 D2)
- 프론트엔드 변경 일체.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `IntentAnalyzerInterface.analyze(message, spec, history=None) -> IntentResult` 포트를 `domain/intent/interfaces.py`에 정의한다. domain은 LangChain·DB·HTTP를 일절 import 하지 않는다. | High | Pending |
| FR-02 | **분류 체계는 호출자가 주입**한다. `IntentSpec(labels=[IntentLabel(name, description)], slots=[], allow_unknown=True)`. 모듈 코드에 도메인 라벨 상수를 두지 않는다. | High | Pending |
| FR-03 | 산출물은 구조화 객체 `IntentResult(label, confidence, entities, ambiguous, missing_slots, reason, degraded)`. | High | Pending |
| FR-04 | `history: list[Turn] \| None` 를 optional 인자로 받는다. 없으면 현재 메시지만으로 판정한다. 모듈은 대화 상태를 **보유하지 않는다**(순수 호출). | High | Pending |
| FR-05 | 판정 엔진은 **LLM 전용**. `with_structured_output(IntentResult)` 1회 호출. 라벨 `description`이 프롬프트에 그대로 쓰인다. | High | Pending |
| FR-06 | **실패 시 `IntentResult(label=None, confidence=0.0, degraded=True)` 반환**. 예외를 밖으로 던지지 않는다. 대상: 예외 / 타임아웃 / 스키마 위반 3종. | High | Pending |
| FR-07 | `IntentResultPolicy.normalize(raw, spec)` 순수함수 — ① spec에 없는 label은 `None`+`ambiguous=True`로 강등 ② confidence 0.0~1.0 clamp ③ `missing_slots`를 `spec.slots`로 필터 ④ `label is None`이면 confidence 0. | High | Pending |
| FR-08 | `create_intent_node(analyzer, spec, logger, state_key="intent")` 노드 팩토리. 반환 노드는 `{state_key: IntentResult.model_dump()}`만 갱신하고 **다른 state 키를 건드리지 않는다**. | High | Pending |
| FR-09 | **탈착 계약**: `analyzer`가 없으면 호출측은 노드를 `add_node` 하지 않는다. 팩토리는 `analyzer=None`을 받으면 `None`을 반환해 이 분기를 강제한다. | High | Pending |
| FR-10 | `POST /api/v1/intent/analyze` — 인증은 기존 라우터 관례를 따른다. 요청 `{message, spec, history?}`, 응답 `IntentResult`. | Medium | Pending |
| FR-11 | `spec.labels`가 2개 미만이면 422로 거부한다(판정 불가). `description`은 필수. | Medium | Pending |
| FR-12 | 모델명·temperature·timeout은 config/env로 주입한다. 하드코딩 금지. | Medium | Pending |
| FR-13 | 판정 1회마다 구조화 로그 1건: `label`, `confidence`, `degraded`, `latency_ms`, `request_id`. `print()` 금지. | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 결합도 | `domain/intent`가 infrastructure를 import하지 않음. `application/intent`가 `langchain_openai`를 import하지 않음 | `/verify-architecture` 스킬 |
| 탈착성 | 모듈 전체 삭제 시 `api/main.py` 등록부 외 어떤 기존 파일도 컴파일 에러 없음 | 수동 검증 체크리스트 |
| 회귀 안전 | 기존 파일 변경은 `api/main.py` 단 1개 (추가만) | `git diff --stat` |
| 지연 | 판정 timeout 기본 10s, 초과 시 degraded 반환 | 어댑터 테스트 (타임아웃 fake) |
| 관측성 | 실패 시 `logger.error(..., exception=e)` 로 스택 트레이스 기록 | `/verify-logging` 스킬 |
| 테스트 | domain policy 분기 100% 커버 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-13 전부 구현
- [ ] `pytest` 전체 스위트 통과 (기존 테스트 실패 0건)
- [ ] `git diff --name-only`에 `supervisor_nodes.py` / `workflow_compiler.py` / `general_chat/` / `multi_query/` **0건**
- [ ] `db/migration/` 신규 파일 **0건**
- [ ] `/verify-architecture` · `/verify-logging` · `/verify-tdd` 3개 스킬 통과
- [ ] `POST /api/v1/intent/analyze` 실호출 1회 성공 (수동, OPENAI_API_KEY 필요)

### 4.2 Quality Criteria

- [ ] `IntentResultPolicy` 분기 커버리지 100% (순수함수, LLM 미사용)
- [ ] LLM 실패 3종(예외 / 타임아웃 / 스키마 위반) 각각 `degraded=True` 반환 테스트 존재
- [ ] `spec` 밖 라벨을 LLM이 반환한 케이스 → `label=None, ambiguous=True` 강등 테스트 존재
- [ ] API 200 / 401 / 422 케이스 테스트 존재
- [ ] 모든 함수 40줄 이내, if 중첩 2단계 이내 (CLAUDE.md §3)

---

## 5. Risks and Mitigation

| ID | Risk | Impact | Likelihood | Mitigation |
|----|------|--------|------------|------------|
| R1 | **LLM 전용 → 요청당 비용·지연 고정 발생**. 휴리스틱 사전 필터를 포기했으므로 절감 여지가 없다. | Medium | High | 이번 사이클엔 어떤 hot path에도 배선하지 않음 → 실사용 비용 0. 배선 시점에 캐시/사전필터를 별도 사이클로 재검토. 모델은 경량 등급 + timeout config 고정. |
| R2 | **위키 계약 2와의 구조적 긴장** — "프롬프트에 할 수 있는 것 목록을 주면 목록 밖 요청을 과차단한다"(실장애 선례, 커밋 08d37cab). 의도 분석은 **본질적으로 라벨 목록을 프롬프트에 넣는 일**이다. | High | Medium | ① `allow_unknown=True` 기본 + "해당 없으면 label을 비워라"를 프롬프트에 명시 ② 판정 결과는 **조언 전용**이라 과차단이 라우팅을 막지 못함 ③ `ambiguous` 플래그로 호출자가 무시 판단 가능. **배선 시점에 이 리스크를 재평가하는 것을 다음 사이클 진입 조건으로 둔다.** |
| R3 | **판정 품질이 호출자가 쓴 `description`에 종속**된다. 라벨을 뽑아낸 대가. | Medium | High | `description` 필수 + 라벨 2개 이상 강제(FR-11). Design 단계에서 "좋은 description 작성 가이드"를 문서 §에 포함. |
| R4 | **미배선 노드 팩토리가 죽은 코드가 된다** — 아무도 안 쓰는 코드를 지금 만드는 셈. | Medium | Medium | 노드 팩토리는 얇게(state 1키 갱신만) 유지 + 단위테스트 필수. 이것이 "끼웠다 뺐다"의 이음매 자체이므로 미리 만드는 것이 사용자 요구의 본체다. Design에서 **다음 사이클의 1차 배선 지점 1곳을 후보로 명시**한다. |
| R5 | **기존 3개 판정 모듈과 책임이 겹쳐 보인다** — 나중에 "왜 4개나 있나" 혼란. | Low | Medium | Out of Scope에 명시(§2.2) + 위키 갱신은 하지 않음(사용자 명시 호출 시에만). 통합 여부는 실제 소비자 2곳 이상 생긴 뒤 판단. |
| R6 | `history`를 받으면서 상태를 보유하지 않는 계약이 흐려질 수 있다 (세션 캐시 유혹). | Low | Low | 포트 시그니처를 순수 함수로 고정. Repository·세션 의존성 주입 금지를 Design에 명문화. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/api/main.py` | Composition Root | 라우터 등록 1줄 + `LLMIntentAnalyzerAdapter`/`AnalyzeIntentUseCase` 생성 **추가만**. 기존 라인 수정 없음. |
| `src/domain/intent/**` | 신규 모듈 | 신규 생성 — 기존 소비자 없음 |
| `src/application/intent/**` | 신규 모듈 | 신규 생성 — 기존 소비자 없음 |
| `src/infrastructure/intent/**` | 신규 모듈 | 신규 생성 — 기존 소비자 없음 |
| `src/interfaces/schemas/intent.py` | 신규 스키마 | 신규 생성 — 기존 소비자 없음 |
| `src/api/routes/intent_router.py` | 신규 라우터 | 신규 생성 — 신규 엔드포인트 1개 |
| `.env` | Config | `INTENT_ANALYZER_MODEL`, `INTENT_ANALYZER_TIMEOUT_SEC` 추가 (기본값 있음 → 미설정도 동작) |

### 6.2 Current Consumers

변경 리소스 중 **기존 소비자가 존재하는 것은 `src/api/main.py` 하나뿐**이며, 변경 성격이 순수 추가라 기존 소비자에 미치는 영향이 없다.

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `src/api/main.py` | 라우터 등록 (기존 52개) | `app.include_router(...)` 블록 | **None** — 신규 라우터 1개 추가. prefix `/api/v1/intent` 는 기존 라우터와 미충돌 |
| `src/api/main.py` | lifespan 초기화 | `lifespan()` | **None** — 초기화 훅 추가 없음. 어댑터는 lazy/DI 생성 |
| DB 스키마 | — | — | **None** — 마이그레이션 0건 |
| 기존 그래프 (supervisor / general_chat / multi_query) | — | — | **None** — 파일 변경 0건이 성공 기준(§4.1) |
| 프론트엔드 `idt_front/` | — | — | **None** — API 계약 동기화(루트 CLAUDE.md §4-1) **불필요**. 신규 엔드포인트를 프론트가 소비하지 않음 |

### 6.3 Verification

- [ ] `git diff --name-only`로 기존 파일 변경이 `src/api/main.py` 1개뿐임을 확인
- [ ] 신규 prefix `/api/v1/intent`가 기존 라우터 52개와 충돌하지 않음을 확인
- [ ] `db/migration/` 신규 파일 0건 확인
- [ ] 모듈 디렉토리 4개를 통째로 삭제해도 `main.py` 등록부 외 컴파일 에러가 없음을 확인 (탈착성 검증)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | 기능 단위 모듈 | ☐ |
| **Enterprise** | 레이어 분리 + DI (기존 idt/ 구조 = Thin DDD) | ☑ |

기존 `idt/`의 Thin DDD 구조를 그대로 따른다. 새 레이어·새 패턴을 도입하지 않는다.

### 7.2 Key Architectural Decisions

| ID | Decision | Options | Selected | Rationale |
|----|----------|---------|:--------:|-----------|
| D1 | 산출물 계약 | 라벨만 / 구조화 객체 / 재작성 쿼리 포함 / 모호성만 | **구조화 객체** | 라우팅·되묻기·슬롯 추출 세 소비자가 하나를 공유. 쿼리 재작성은 `query_rewrite`의 기존 책임이라 제외 |
| D2 | 판정 엔진 | 휴리스틱+LLM 폴백 / **LLM 전용** / 규칙만 | **LLM 전용** | 라벨을 호출자가 주입(D3)하는 순간 도메인 Policy는 라벨 의미를 모르므로 휴리스틱 매칭이 성립하지 않는다. 키워드까지 주입받으면 계약이 무거워진다 → 계약의 깔끔함을 택함 (대가는 R1) |
| D3 | 분류 체계 출처 | 코드 상수 / **호출자 주입** / DB 설정 | **호출자 주입** | 재사용성의 핵심. 모듈이 라벨 의미를 모름 = 여신 특화가 코어에 침투하지 않음 (USER-SCENARIOS "일반화가 이긴다"). DB 설정화는 마이그레이션+UI로 범위가 커져 후속 |
| D4 | 결합 방식 | **포트+노드 팩토리** / HTTP 서비스 / 미들웨어 / 전부 | **포트+노드 팩토리** (+ 검증용 얇은 API) | `chart_router`·`search_decision`이 확립한 관례의 4번째 인스턴스. HTTP 경계는 오버헤드만 늘림. 미들웨어는 `create_agent` 경로에만 적용 가능해 범용성 낮음 |
| D5 | 판정 권한 | 조언 / 고신뢰 강제 / 항상 강제 | **조언 전용** | 위키 계약 3 "결정적 라우팅=확실한 신호 전용, 불확실 판단=LLM"과 정합. 강제하면 오분류가 전면 오응답이 됨 |
| D6 | 실패 정책 | **unknown 반환** / 예외 / 휴리스틱 폴백 | **unknown(`degraded=True`)** | 기존 3개 모듈과 동일한 "보수적 폴백, 본 흐름 안 막기" 계약. 호출자는 "의도 모름 = 기존대로" 처리 |
| D7 | 입력 범위 | 현재 메시지만 / **메시지+이력** / +임의 컨텍스트 | **메시지 + optional 이력** | 위키 계약 3의 "재질문 재검색 우회" 선례상 다중턴 문맥 없이는 오판. 단 이력은 **인자**일 뿐 모듈은 상태를 보유하지 않음 |
| D8 | 1차 투입 지점 | 없음(모듈만) / supervisor / general_chat / multi_query | **없음 (모듈만)** | 회귀 위험 0으로 이음매를 먼저 확보. 배선은 소비자가 확정된 다음 사이클 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD — 기존 idt/ 구조 준수)

src/
├── domain/intent/                    ← 외부 의존 0. LangChain·DB·HTTP import 금지
│   ├── schemas.py                      Turn, IntentLabel, IntentSpec, IntentResult
│   ├── interfaces.py                   IntentAnalyzerInterface  (포트)
│   └── policies.py                     IntentResultPolicy.normalize()  (순수함수)
│
├── application/intent/               ← 흐름 제어만. 규칙은 policies에 위임
│   ├── use_case.py                     AnalyzeIntentUseCase
│   └── node.py                         create_intent_node(analyzer, spec, logger)
│                                       └ analyzer is None → return None (FR-09)
│
├── infrastructure/intent/            ← 유일하게 LangChain을 아는 곳
│   └── adapter.py                      LLMIntentAnalyzerAdapter
│                                       (search_decision/adapter.py 패턴 미러링)
│
├── interfaces/schemas/intent.py      ← FastAPI request/response
└── api/routes/intent_router.py       ← POST /api/v1/intent/analyze
     └ src/api/main.py 에 등록 + DI (기존 파일 중 유일한 수정 대상)

의존 방향:  interfaces → application → domain ← infrastructure
            (domain은 아무것도 향하지 않음)
```

**탈착 이음매 2개** — 이 기능의 존재 이유:

1. **주입 이음매** — `create_intent_node(analyzer=None)` → `None` 반환 → 호출측이 `add_node` 자체를 건너뜀. 노드가 그래프에 존재조차 하지 않는다.
2. **런타임 이음매** — LLM 실패 시 `degraded=True` → 호출측은 "의도 모름"으로 읽고 기존 로직 그대로 진행. 붙어 있어도 죽지 않는다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` — 레이어 책임·금지사항·함수 40줄 제한
- [x] `idt/docs/rules/logging.md` — StructuredLogger, `exception=e` 규약
- [x] `idt/docs/rules/testing.md` — TDD Red→Green→Refactor
- [x] `docs/wiki/backend/patterns/supervisor-graph-contracts.md` — 라우팅 계약 3종
- [x] `pyproject.toml` — pytest 설정
- [ ] `docs/01-plan/conventions.md` — 없음 (CLAUDE.md가 대체, 신규 작성 불필요)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 모듈 네이밍 | exists — `domain/{x}/{interfaces,schemas,policies}.py` 3회 선례 | 그대로 따름. 신규 규칙 없음 | High |
| 포트 폴백 계약 | exists — "실패 시 보수적 값, 본 흐름 안 막기" 3회 선례 | `degraded` 플래그는 **신규** — 기존 3개는 폴백을 침묵으로 처리. 호출자가 구분 가능하도록 명시 필드 도입 | High |
| 노드 팩토리 | exists — `create_chart_router_node()` 선례 | `analyzer=None → None 반환` 은 **신규 관례**. Design에 명문화 | High |
| 에러 처리 | exists | `logger.error(..., exception=e)` 준수 | Medium |
| 환경변수 | exists | `INTENT_ANALYZER_MODEL`, `INTENT_ANALYZER_TIMEOUT_SEC` 추가 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | Default | To Be Created |
|----------|---------|-------|---------|:-------------:|
| `INTENT_ANALYZER_MODEL` | 판정용 LLM 모델명 | Server (idt/.env) | 경량 모델 (Design에서 확정) | ☑ |
| `INTENT_ANALYZER_TIMEOUT_SEC` | 판정 타임아웃 | Server (idt/.env) | `10` | ☑ |
| `OPENAI_API_KEY` | 기존 | Server | — | ☐ (기존) |

> 두 변수 모두 기본값을 가지므로 **미설정 상태에서도 동작**한다 (기존 배포 환경 무영향).

### 8.4 Pipeline Integration

해당 없음 — 9-phase Development Pipeline이 아닌 단일 기능 PDCA 사이클.

---

## 9. Next Steps

1. [ ] `/pdca design intent-analyzer` — 설계 문서 작성 (3안 비교 → 선택)
   - Design에서 확정할 항목: 프롬프트 문안(R2 완화 문구 포함), 모델 등급, `IntentResult` 필드 최종 확정, 인증 방식, 다음 사이클 1차 배선 후보 1곳
2. [ ] TDD 구현 (`/pdca do intent-analyzer`) — Red → Green → Refactor
3. [ ] `/pdca analyze intent-analyzer` — Gap 분석
4. [ ] **후속 사이클**(별도 PDCA): 실제 배선 1곳 + 그 시점에 R2(과차단) 재평가

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 초안 — 사용자 인터뷰 10문항 기반 (D1~D8 확정) | 배상규 |
