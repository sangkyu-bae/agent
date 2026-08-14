# intent-analyzer Gap Analysis

> **Phase**: Check
> **Date**: 2026-08-13
> **Analyst**: 배상규
> **Plan**: [intent-analyzer.plan.md](../01-plan/features/intent-analyzer.plan.md)
> **Design**: [intent-analyzer.design.md](../02-design/features/intent-analyzer.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 의도 판정이 3곳에 중복 산재 — 재사용 가능한 단일 모듈 부재 |
| **WHO** | P2 (에이전트 소유자) — 부서별 라벨로 자기 그래프에 꽂는 사람 |
| **RISK** | LLM 전용 비용·지연 / 라벨 목록 프레이밍 과차단 (위키 계약 2) |
| **SUCCESS** | 기존 경로 회귀 0 · 마이그레이션 0 · domain→infra import 0 · 실패 3종 degraded |
| **SCOPE** | 모듈 + 독립 API만. 배선은 다음 사이클 |

---

## 0. 분석 방법 및 한계 (선언)

| 항목 | 상태 |
|------|------|
| `gap-detector` 서브에이전트 | **미호출** — 세션 운영 제약("요청 없이 Agent 도구 금지"). 대신 파일 존재 검사·AST 검사·grep·커버리지로 직접 대조 |
| 라이브 서버 L1 (curl) | **미실행** — `localhost:8000` 응답 없음 (`NO_SERVER`) |
| L2 / L3 (Playwright) | **N/A** — UI 없음 (Design §8.1에서 사전 선언) |
| Match Rate 공식 | 라이브 런타임 부재 → **static-only 공식** 적용 |
| `/verify-architecture`·`/verify-logging`·`/verify-tdd` | **스킬 미실행** — 동등한 수동 대조로 대체 (§4 G5) |

---

## 1. Strategic Alignment Check

| 질문 | 판정 | 근거 |
|------|:----:|------|
| Plan 의 핵심 문제(WHY)를 다뤘는가 — 재사용 가능한 단일 의도 모듈 | ✅ | `src/domain/intent/` 포트 + 어댑터 + 노드 팩토리 + API 존재. 라벨 하드코딩 0건 |
| 주인공 P2 관점 — 부서별 라벨을 꽂을 수 있는가 | ✅ | `IntentSpec` 이 100% 호출 인자. 프로덕션 코드에 도메인 라벨 문자열 0건(grep 검증) |
| USER-SCENARIOS "일반화가 이긴다" 준수 | ✅ | 여신 특화 상수 없음. `search`/`analysis` 같은 라벨은 **테스트 픽스처에만** 존재 |
| 스코프 이탈 없는가 (배선 금지) | ✅ | supervisor/general_chat/multi_query 변경 0건 |
| **전략적 오정렬** | **없음** | Critical 승격 사유 없음 |

---

## 2. Plan Success Criteria 평가

### 2.1 Definition of Done (Plan §4.1)

| # | 기준 | 판정 | 증거 |
|---|------|:----:|------|
| 1 | FR-01 ~ FR-13 전부 구현 | ✅ | §3.2 FR 대조표 13/13 |
| 2 | `pytest` 전체 통과 (기존 실패 0건) | ❌ | `7040 passed, 58 failed`. **58건 전부 baseline 동일**(파일별 개수까지 일치), intent 무관 → §4 G4 |
| 3 | supervisor/general_chat/multi_query 변경 0건 | ✅ | `git status` — 내 변경은 `src/api/main.py` 1개뿐 |
| 4 | `db/migration/` 신규 0건 | ✅ | `git status -- db/migration` → 0 |
| 5 | 3개 verify 스킬 통과 | ⚠️ | 스킬 미실행. 수동 대조로 동등 확인 → §4 G5 |
| 6 | 실호출 1회 성공 (수동) | ❌ | 서버 미기동 → §4 G1 |

**DoD: 4/6 충족, 1 부분, 1 미충족**

### 2.2 Quality Criteria (Plan §4.2)

| # | 기준 | 판정 | 증거 |
|---|------|:----:|------|
| 1 | `IntentResultPolicy` 분기 100% | ✅ | `policies.py 26 stmts, 0 miss, 100%` |
| 2 | LLM 실패 3종 각각 degraded 테스트 | ✅ | 예외/타임아웃/스키마위반 3개 테스트 존재·통과 |
| 3 | spec 밖 라벨 → 강등 테스트 | ✅ | `test_label_outside_spec_is_demoted_not_degraded` + 어댑터 레벨 1건 |
| 4 | API 200/401/422 테스트 | ✅ | 13개 라우터 테스트 전부 통과 |
| 5 | 40줄 이내 / if 중첩 2단계 이내 | ✅ | AST 검사 — 위반 0건 |

**Quality: 5/5 충족**

---

## 3. 정적 분석 3축

### 3.1 Structural Match — 100%

Design §11.1 이 명세한 17개 경로 전부 존재.

| 계층 | 파일 | 상태 |
|------|------|:----:|
| domain | `__init__` / `schemas` / `interfaces` / `policies` | 4/4 ✅ |
| application | `__init__` / `use_case` / `node` | 3/3 ✅ |
| infrastructure | `intent/__init__` / `intent/adapter` / `config/intent_config` | 3/3 ✅ |
| interfaces | `schemas/intent.py` | 1/1 ✅ |
| api | `routes/intent_router.py` | 1/1 ✅ |
| tests | policies / use_case / node / adapter / router | 5/5 ✅ |
| 수정 | `src/api/main.py` (import 3 + DI 1 + include 1) | ✅ |

라우트 실등록 확인: 실앱 `POST /api/v1/intent/analyze` → **401**(404 아님) = 등록됨.

**Structural = 100%**

### 3.2 Functional Depth — 92%

| FR | 요구 | 판정 | 증거 |
|----|------|:----:|------|
| FR-01 | 도메인 포트, domain 외부 의존 0 | ✅ | `interfaces.py`; import = `abc`/자기 스키마뿐 |
| FR-02 | 라벨 호출자 주입, 도메인 상수 0 | ✅ | grep 0건 (프로덕션 코드) |
| FR-03 | 구조화 객체 7필드 | ✅ | `IntentResult` 7필드 일치 |
| FR-04 | history optional, 상태 미보유 | ⚠️ | 포트·어댑터 레벨 ✅(테스트 2건). **노드 레벨 history 경로 미테스트** → G2 |
| FR-05 | LLM 전용 `with_structured_output` | ✅ | `adapter.py:72` |
| FR-06 | 실패 3종 → degraded, 예외 미전파 | ✅ | 테스트 3건 통과 |
| FR-07 | normalize 4규칙 | ✅ | 분기 100% 커버 |
| FR-08 | 노드가 state_key 1개만 갱신 | ✅ | `test_node_returns_only_the_state_key` |
| FR-09 | analyzer=None → None 반환 | ✅ | `test_factory_returns_none_when_analyzer_missing` |
| FR-10 | POST + 인증 | ✅ | `Depends(get_current_user)`, 401 테스트 |
| FR-11 | labels<2 → 422 | ✅ | 라우터 422 테스트 2건 |
| FR-12 | config 주입, 하드코딩 0 | ✅ | grep 0건 (config 파일 외) |
| FR-13 | 판정 1회당 구조화 로그 1건 | ✅ | `adapter.analyze` info 1건 + 실패 시 error/warning |

**구현 기준 13/13.** 최초 측정 시 커버리지가 미검증 분기 2곳을 드러냈고(G2·G3), §9 에서 해소했다.

| 모듈 | 최초 | 해소 후 |
|------|-----:|-------:|
| `application/intent/node.py` | 67% (13 miss) | **100%** |
| `infrastructure/intent/adapter.py` | 92% (5 miss) | **94%** (잔여 = `_build_chain`, 실 LLM 필요) |
| `domain/intent/policies.py` | 100% | 100% |
| **TOTAL** | **88%** | **97%** |

**Functional = 100%** (FR 13/13 구현 + 명세된 분기 전량 테스트 고정. 잔여 미커버는
`_build_chain`(실 `ChatOpenAI`)과 추상 메서드 `raise` 뿐 — 둘 다 의도된 미검증)

### 3.3 API Contract — 100%

Design §4.2 ↔ `interfaces/schemas/intent.py` ↔ `api/routes/intent_router.py` 3-way 대조:

| 항목 | Design §4.2 | 코드 | 일치 |
|------|-------------|------|:----:|
| Request 필드 | `message`, `spec`, `history?` | `['history','message','spec']` | ✅ |
| `spec` 필드 | `labels`, `slots?`, `allow_unknown?` | `['allow_unknown','labels','slots']` | ✅ |
| Response 필드 | 7개 | `IntentResult` 와 완전 일치 (런타임 비교 True) | ✅ |
| 200 정상 | ✅ | 테스트 통과 | ✅ |
| **200 + degraded** (5xx 아님) | ✅ | `test_degraded_result_returns_200` | ✅ |
| 401 미인증 | ✅ | 테스트 통과 | ✅ |
| 422 검증 실패 | ✅ | 4건 테스트 | ✅ |
| prefix 충돌 없음 | ✅ | 실앱 401 응답으로 확인 | ✅ |

**Contract = 100%**

### 3.4 Runtime Verification

| 레벨 | 계획 | 실행 | 결과 |
|------|------|:----:|------|
| L0 단위 | 22+ 시나리오 | ✅ | 45 passed |
| L1 API (자동, TestClient) | 7 시나리오 | ✅ | 13 passed |
| L1 API (라이브 서버 curl) | Design §8.1 | ❌ | 서버 미기동 |
| 실 LLM 1회 호출 | Design §8.1 수동 | ❌ | 미실행 |
| L2 / L3 | — | N/A | UI 없음 (사전 선언) |

**intent 모듈 자동 테스트: 58 passed / 0 failed**

---

## 4. Gap 목록

| ID | 심각도 | 내용 | 근거 | 조치 |
|----|:------:|------|------|------|
| **G1** | **Important** | **실 LLM 호출 검증 0회.** Design §4.3 프롬프트(위키 계약 2 완화 문안 포함)가 실제로 의도대로 동작하는지 **한 번도 확인되지 않음**. fake chain 테스트는 프롬프트 조립만 검증하며 LLM 응답 품질은 검증하지 못한다 | Plan §4.1 #6 미충족 | 서버 기동 후 수동 1회. **본 기능 최대 리스크(R2)의 유일한 실증 수단** |
| **G2** | ~~Important~~ **해소** | `node.py` **history 경로 전량 미테스트** (13 stmts, 77-92행). `_extract_history`·`_to_turn` 을 호출하는 테스트가 없었다 — `history_key` 를 넘기는 테스트를 안 만듦 | 커버리지 67% | ✅ **테스트 6건 추가 → 100%** (§9) |
| **G3** | ~~Minor~~ **해소** | `_unknown_block` 의 `allow_unknown=False` 분기 미테스트 (adapter:164). Design §4.3 이 "힌트이지 제약이 아니다"라고 명시한 동작인데 고정되지 않음 | 커버리지 92% | ✅ **테스트 2건 추가** (§9) |
| **G4** | Minor(외부) | 전체 스위트 58건 실패 → Plan DoD #2 미충족 | parser 21 / agent_builder_stream 9 / retriever 7 / general_chat 7 등 | **본 기능 무관** — baseline과 파일별 개수까지 동일, 원인은 라이브러리 버전 드리프트. 별도 사이클 |
| **G5** | Minor | `/verify-architecture`·`/verify-logging`·`/verify-tdd` 스킬 미실행 | Plan DoD #5 | 수동 대조로 동등 확인됨(§5). 스킬 실행은 선택 |
| **G6** | Info | `_build_chain` 미테스트 (adapter:65-73) | 실 `ChatOpenAI` 필요 | 의도된 미검증. G1 수동 검증이 대신함 |

### Critical: **0건** · 잔여 Important: **1건 (G1)**

---

## 5. 아키텍처 회귀 검증 (A1~A7)

| # | 검증 | 결과 | 방법 |
|---|------|:----:|------|
| A1 | `domain/intent` → infra·langchain import | ✅ 0건 | grep `^(from\|import)` |
| A2 | `application/intent` → langchain·openai import | ✅ 0건 | grep |
| A3 | 기존 파일 변경 = `main.py` 1개 | ✅ | `git status` |
| A4 | 마이그레이션 신규 | ✅ 0건 | `git status -- db/migration` |
| A5 | `print()` | ✅ 0건 | grep |
| A6 | 프로덕션 모듈 대비 테스트 | ✅ 6/6 | 파일 존재 |
| A7 | **탈착성** — 모듈 참조처 | ✅ `main.py` **단 1개** | grep 전수 |

A7이 이 기능의 존재 이유이며, grep으로 확정됨.

---

## 6. Decision Record 준수 검증

| ID | 결정 | 준수 | 증거 |
|----|------|:----:|------|
| D1 | 구조화 의도 객체 | ✅ | `IntentResult` 7필드 |
| D2 | LLM 전용 (휴리스틱 없음) | ✅ | Policy는 정규화만 수행, 판정 로직 없음 |
| D3 | 라벨 호출자 주입 | ✅ | 도메인 라벨 상수 0건 |
| D4 | 포트 + 노드 팩토리 | ✅ | `create_intent_node` 존재 |
| D5 | 조언 전용 | ✅ | 노드가 state 1키만 기록, 분기 강제 없음 |
| D6 | 실패 시 unknown(`degraded`) | ✅ | 3종 테스트 |
| D7 | 메시지 + optional 이력, 무상태 | ✅ | 상태 필드 0건 |
| D8 | 배선 없음 | ✅ | 참조처 `main.py` 뿐 |
| Option C | search_decision 패턴 복제 | ✅ | 구조 동일 |

**결정 이탈: 0건**

### 6.1 Design 대비 구현 이탈 (전부 의도적, 문서화됨)

| # | 이탈 | 방향 | 사유 |
|---|------|------|------|
| 1 | `AnalyzeIntentUseCase` 에서 `logger` 제거 | 축소 | 어댑터가 이미 로깅 — 죽은 의존 방지. 파일 docstring에 명시 |
| 2 | `create_intent_node` 에 `message_key`·`history_key` 추가 | 확장 | state 키 이름이 그래프마다 다름. **G2의 원인 — 추가했으나 테스트 누락** |
| 3 | `IntentChain` Protocol 도입 | 확장 | `Any` 금지(§10.4) + fake 주입 양립 |
| 4 | 메시지 없으면 LLM 미호출 후 degraded | 확장 | 빈 state에서 비용 발생 방지 (Plan R1) |
| 5 | Design §8.2 시나리오 20~21 → 라우터 422 테스트로 이동 | 이동 | pydantic이 생성 시점에 거부 → UseCase 레벨 검증이 공허 |
| 6 | `AnalyzeIntentResponse` 가 `IntentResult` 상속 | 단순화 | 계약 중복 제거 |

---

## 7. Match Rate

라이브 런타임 미실행 → **static-only 공식** 적용:

```
Overall = (Structural × 0.2) + (Functional × 0.4) + (Contract × 0.4)
```

| 축 | 최초 | G2·G3 해소 후 |
|----|-----:|------------:|
| Structural | 100% | 100% |
| Functional | 92% | **100%** |
| Contract | 100% | 100% |
| **Overall** | **96.8%** | **100%** |

| 참고 지표 | 값 |
|-----------|----|
| intent 모듈 자동 테스트 | **66 passed / 0 failed** |
| intent 모듈 커버리지 | **97%** |
| 전체 스위트 | 7040+ passed / 58 failed (전부 baseline 동일, 무관) |

> ⚠️ **100% 를 "검증 끝"으로 읽으면 안 된다.** Match Rate 는 *설계 문서 대비 구현
> 일치도*만 재는 지표다. **G1(실 LLM 호출 0회)은 이 수치에 원리적으로 잡히지 않는다**
> — 코드는 설계와 완전히 일치하지만, Design §4.3 프롬프트가 실제 LLM에서 의도대로
> 동작하는지는 여전히 아무도 모른다. 본 기능 최대 리스크(Plan R2, 위키 계약 2)의
> 유일한 실증 수단이 미실행 상태라는 뜻이다.

---

## 8. 결론

- **Critical 0건.** 아키텍처 계약(A1~A7)과 설계 결정(D1~D8) 전량 준수.
- G2·G3 는 **테스트 추가만으로 해소** (프로덕션 코드 무수정, §9).
- **잔여 Important 1건: G1(실 LLM 검증 0회)** — 서버 기동 + API 키가 필요해 환경 의존. 자동화 불가.
- G4(전체 스위트 58 실패)·G5(verify 스킬 미실행)는 본 기능과 무관하거나 동등 대체됨.

**다음 사이클(배선) 진입 조건**: Design §11.4 의 1단계(shadow) 진입 전에 **G1 을 반드시 해소**할 것.
프롬프트가 실증되지 않은 상태로 배선하면 Plan R2 를 검증 없이 떠안는 것이 된다.

---

## 9. Act 로그 — G2·G3 해소

Checkpoint 5 에서 "G2·G3 테스트만 추가"를 선택. **프로덕션 코드는 한 줄도 수정하지 않았다.**

| 갭 | 추가한 테스트 | 검증 내용 |
|----|--------------|----------|
| G2 | `test_history_key_none_forwards_no_history` | `history_key` 미지정 시 state 의 이력을 무시 |
| G2 | `test_history_key_converts_dicts_to_turns` | dict 리스트 → `Turn` 변환, 순서 보존 |
| G2 | `test_history_key_accepts_turn_objects_as_is` | 이미 `Turn` 이면 그대로 통과 |
| G2 | `test_history_key_drops_malformed_items` | 잘못된 role·문자열·필드 누락 항목을 조용히 버리고 나머지만 전달 |
| G2 | `test_history_key_with_all_items_invalid_yields_none` | 전부 무효면 `None` |
| G2 | `test_history_key_with_non_list_value_yields_none` | 리스트가 아니면 `None` |
| G3 | `test_unknown_block_is_empty_when_unknown_allowed` | 기본값(`allow_unknown=True`)이면 힌트 문구 없음 |
| G3 | `test_unknown_block_nudges_but_does_not_forbid_empty_label` | `allow_unknown=False` 가 **빈 label 을 금지하지 않음**을 문구 수준에서 고정 — 위키 계약 2 재현 방지 |

**결과**: 58 passed → **66 passed**, 커버리지 88% → **97%**, `node.py` 67% → **100%**. ruff clean.

G3 의 두 번째 테스트는 단순 커버리지 채우기가 아니다. `allow_unknown=False` 를
"빈 label 금지"로 해석하도록 프롬프트를 바꾸는 순간 위키 계약 2 의 과차단 실장애가
재현되므로, **그 해석을 코드가 아니라 테스트로 못 박았다**.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 초안 — static 3축 + A1~A7 + D1~D8 대조. Match Rate 96.8% | 배상규 |
| 0.2 | 2026-08-13 | G2·G3 테스트 추가로 해소 (66 passed, 커버리지 97%). Match Rate 100%. 잔여 Important = G1 | 배상규 |
