# agent-create-pipeline Gap Analysis

> **Match Rate**: **97%** (Act-1 후 — §8 재검증. 최초 92%)
> **게이트(90%)**: ✅ 통과 · **Iteration**: 1/5
> **분석일**: 2026-08-19 · **분석자**: gap-detector agent + 런타임(pytest) 실행 증거
> **Design**: [agent-create-pipeline.design.md](../02-design/features/agent-create-pipeline.design.md) · **Plan**: [agent-create-pipeline.plan.md](../01-plan/features/agent-create-pipeline.plan.md)

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | intent·tool_selection·prompt_composer가 배선 없이 각자 떠 있어, 에이전트 자동 생성의 end-to-end 가치가 한 번도 증명된 적 없다 |
| **WHO** | P2(에이전트 소유자). 이번 사이클 1차 소비자는 API 호출자 — 프론트 배선은 후속 사이클 |
| **RISK** | 규칙 3벌 공존(R1) · SSE 끊김·중복 생성(R7) |
| **SUCCESS** | 회귀 0 · 되묻기 왕복 완주 · degraded=200/저장실패=5xx · steps 5개 고정 · SSE 순서 계약 |
| **SCOPE** | 백엔드 전용 (module-1~3 완료) |

---

## 1. 전략 정합성 (Strategic Alignment)

- **WHY 충족**: 재료 모듈 3종이 실제로 한 UseCase에서 완주 배선됨 — Plan의 핵심 문제가 해소됨. ✅
- **핵심 설계 결정 준수**: D1(병렬 신설·기존 무변경), D2(ToolSelectorPort 재사용), D3(stateless 되묻기), D4(실제 생성+바인딩), D8(단계 상태 1급 계약+SSE) 전부 구현 확인. ✅
- Critical 등급 전략 이탈: **없음**.

## 2. Plan Success Criteria 평가

| 기준 (Plan §4.1) | 판정 | 근거 |
|---|:---:|---|
| 되묻기 왕복: need_input → answers 재호출 → agent_id 완주 | ⚠️ Partial | 각 반쪽(질문 반환 / round 재clamp 재호출)은 검증됐으나 **이어붙인 왕복 통합 테스트 없음** (시나리오 #3) |
| 미충족 슬롯 없는 요청 1차 호출로 agent_id | ✅ | `test_happy_path_emits_five_stages_then_created_outcome` + 라우터 테스트 |
| 생성된 agent_id GET 조회 일치 | ❌ | 시나리오 #15 미구현 |
| prompt_session에 agent_id 바인딩 | ✅ | `test_happy_path...` bind_calls 단언 (UseCase 계층) |
| LLM 3단계 실패 각각 200+degraded (저장 실패 5xx) | ✅ | 시나리오 #4/#5/#6/#7 전부 테스트 통과 |
| steps/SSE: 실제 이력 일치·순서·failed 식별 | ✅ | 시나리오 #12/#13 + FR-15 동일성 테스트 |
| 기존 5경로 회귀 0 (FAILED 목록 diff) | ✅ | 전체 스위트 7,404건 실행 — FAILED 60건 중 58건 = 상시 baseline, 신규 2건은 tool_selection 경계 계약(선언 갱신으로 해소, 재실행 통과). 단 **전용 등록 테스트(#14)는 부재** — 실행 증거로 갈음 |

## 3. 런타임 검증 (이 프로젝트 관례: pytest/TestClient)

- 기능 테스트 4계층 58케이스 + 경계 계약 35케이스 = **93/93 통과**
- 전체 스위트: 신규 회귀 0건 (baseline 58건 외 추가 실패 없음)
- 시나리오 커버리지: **76.7%** (Design §8.2 15개 중 10 full / 3 partial / 2 missing — §5 매핑 표)

## 4. 축별 일치율 및 Gap (gap-detector 리포트)

| 축 | 일치율 |
|---|:---:|
| Structural Match | 96% |
| Functional Depth | 93% (placeholder 0건) |
| API Contract | 90% |
| **Overall (static)** | **92%** |

### 4.1 Gap 목록 — Critical 0 · Important 4 · Minor 6

| # | 심각도 | 항목 | 근거 절 | 위치 | 확신도 |
|---|:---:|---|---|---|:---:|
| G-01 | **Important** | SSE heartbeat 미구현 — LLM 3회 대기 중 프록시 idle 끊김 → R7(중복 생성) 실현 경로. `format_heartbeat()` 기성품 미사용 | §4.4 | `agent_pipeline_router.py:113-146` | 95% |
| G-02 | **Important** | dead config 2종 — `AGENT_PIPELINE_MAX_QUESTIONS`/`_MAX_OPTIONS_PER_SLOT`가 조립되나 UseCase는 `max_rounds`만 소비. 실제 상한은 intent 어댑터의 `INTENT_*` config가 결정 → 오버라이드 무효 | §3.2/§9.3 | `main.py` 조립 vs `use_case.py:114` | 92% |
| G-03 | **Important** | round clamp 기준 이원화 — 파이프라인(`AGENT_PIPELINE_MAX_ROUNDS`) vs intent 어댑터 프롬프트(`INTENT_*` max_rounds) 불일치 가능 | §3.2/FR-02 | `use_case.py:114` vs `infrastructure/intent/adapter.py:161` | 80% |
| G-04 | **Important** | 미지 tool_id 에코백 누락 — Plan FR-03 요구가 Design §4.3에서 유실. `unknown_tool_ids`가 계산되지만 응답에서 버려짐 | Plan FR-03 | `events.py`/`agent_pipeline.py` | 75% |
| G-05 | Minor | SSE `stage_started` payload가 `{"stage":...}`가 아니라 StageRecord 전문 (status:"ok" 오독 여지) | §4.4 | `agent_pipeline_router.py:129` | 90% |
| G-06 | Minor | 무인증 응답 403 (HTTPBearer 기본) — Design은 401만 명시, 테스트 단언 느슨 | §4.5 | 라우터/테스트 | 85% |
| G-07 | Minor | 파일명 이탈 (`catalog_candidate_reader.py` → `adapters.py`) + `NullToolSelector` 미설계 추가(사유는 D-04) | §11.1 | `adapters.py` | 100% |
| G-08 | Minor | 요청 `history` 상한 미강제 (다운스트림 절단은 존재 — 절단 계약 자체는 충족) | §4.2 | `agent_pipeline.py:29` | 80% |
| G-09 | Minor | 셀렉터 timeout 기본 3.0→5.0 수치 근거 미문서화 | §9.3 | config | 85% |
| G-10 | Minor | created 경로 `finalize_steps(..., "need_input")` skip_reason 오용 (현재 도달 불가) | §4.3 | `use_case.py:289` | 90% |

### 4.2 Documented Deviations (10건 — gap 아님, 전부 코드 주석/테스트에 사유 명시)

D-01 `resolve_tool_ids` 1인자화 · D-02 `halted_at`→`skip_reason` · D-03 `empty_candidate_selection` 추가(규칙 위치 이동) · D-04 `NullToolSelector`(degraded 진행, 미등록 낙하 아님) · D-05 SSE 포매터 관례 재사용(코드 공유 아님, wire 동일) · D-06 셀렉터 파라미터 독립(Plan O6/R3 정합) · D-07 `assembled_prompt`=실저장값 · D-08 `IntentSummaryOut.label` additive · D-09 tool_selection 선언 소비자 등록(경계 테스트로 계약화) · D-10 스펙 상수→팩토리(오염 방지)

## 5. 시나리오 → 테스트 매핑 (Design §8.2)

#1 ✅ #2 ✅ #3 ⚠️(왕복 완주 미증명) #4 ✅ #5 ✅ #6 ✅ #7 ✅ #8 ⚠️(create DB예외→500 전용 없음, ValueError→422만) #9 ⚠️(RuntimeError 주입 — 계약 예외 `AgentAlreadyBoundError` 미사용, API층 bind_ok=false 단언 없음) #10 ✅ #11 ✅ #12 ✅ #13 ✅ #14 ❌(전용 테스트 없음 — 전체 스위트 diff로 갈음) #15 ❌(GET 재확인 없음)

## 6. 권고 조치

**Important (코드)**: G-01 heartbeat 주기 송출 · G-02 dead config 제거 또는 배선 · G-03 round 상한 단일 출처화 · G-04 `unknown_tool_ids` 응답 필드 추가(또는 이월 명시)
**테스트 보강 (DoD)**: #3 왕복 완주 통합 · #9 계약 예외로 정밀화 · #8 500/422 분리 · #15 생성 후 GET 확인
**문서 갱신 (코드가 진실 — 사용자 보고 후)**: §11.1 파일명 · §4.4 started payload 형상 · §4.5 403 병기 · §9.3 timeout 5.0

## 7. 판정

**92% ≥ 90% — iterate 없이 report 진행 가능**하나, Important 4건 중 G-01(스트리밍 안정성=R7 직결)과 DoD 미증명 2건(#3 왕복 완주, #15)은 이 기능의 존재 이유와 직결되므로 처리 후 마감 권장.

## 8. Act-1 결과 (사용자 결정: "지금 모두 수정")

### 8.1 해소 내역

| Gap | 조치 | 검증 |
|---|---|---|
| G-01 heartbeat | SSE 스트림에 15초 주기 heartbeat 주석 라인. **`wait_for` 미사용** — `__anext__` 취소가 파이프라인을 중단시키므로 task 유지 + `asyncio.wait(timeout)` 패턴 (run/stream의 `wait_for` 패턴은 큐 기반 스트림에만 안전) | `test_sse_emits_heartbeat_while_stage_is_slow` (이벤트 무손실 동시 단언) |
| G-02/G-03 config | `AGENT_PIPELINE_MAX_*` 3종 삭제 — 되묻기 상한 단일 출처를 `IntentConfig.slot_limits()`로 통일, main.py가 파이프라인에 주입 | 기존 `test_round_is_reclamped_before_intent_call` + config docstring |
| G-04 unknown_tool_ids | `PipelineOutcome`/응답 스키마에 추가, compose 산출물에서 전달 (Plan FR-03 복원) | `test_unknown_tool_ids_are_echoed` |
| G-05 started payload | `{"stage": ...}` 만 송출 (§4.4 계약대로 축소) | `test_sse_stage_started_payload_is_stage_only` |
| G-06 무인증 상태코드 | **gap-detector 판정 반증** — 실측 401 (이 FastAPI 버전의 HTTPBearer). Design §4.5가 처음부터 정확했음. 테스트를 `== 401`로 고정 | `test_unauthenticated_is_rejected_with_401` |
| G-07/G-09 | Design v0.2 갱신 (adapters.py·NullToolSelector §2.3·timeout 5.0 근거) — 코드가 진실 | 문서 |
| G-08 history 상한 | 스키마 `max_length=20` (prompt_composer와 동일) | `test_history_over_20_turns_is_422` |
| G-10 skip_reason | created 경로 `_NOT_REACHED` 사용 | 코드 |

### 8.2 DoD 시나리오 보강

- **#3 왕복 완주**: `test_clarification_round_trip_completes_creation` — need_input → answers/round 에코백 재호출 → created, round 재사용·answers 전달·create 1회 단언 ✅
- **#8 분리**: `test_create_storage_failure_propagates_as_is` (DB 예외→전파) vs 기존 ValueError→422 ✅
- **#9 정밀화**: `test_bind_conflict_contract_exception_is_absorbed` (계약 예외 `AgentAlreadyBoundError`) + API층 `test_bind_failure_is_surfaced_in_created_response` ✅
- **#14**: 전용 테스트 대신 **전체 스위트 FAILED 목록 diff**(baseline 58건 외 0)로 갈음함을 본 문서에 명시 — 거짓 초록 게이트 관례 준수
- **#15 GET 재확인**: 실 DB 필요 — **명시 이월** (`explicit-gap-carryover` 관례). 실서버 기동 시 E2E 체크리스트에서 소화: "파이프라인 생성 → `GET /api/v1/agents/{id}` 프롬프트·도구 일치 확인"

### 8.3 재검증 Match Rate

Act-1 후 기능 테스트 **101/101 통과**, ruff 통과, main import 스모크 통과.

| 축 | 최초 | Act-1 후 | 변화 근거 |
|---|:---:|:---:|---|
| Structural | 96% | 98% | 파일 구조 문서 정합화 (잔여: 없음) |
| Functional | 93% | 98% | dead config 제거·skip_reason·단일 출처화 |
| Contract | 90% | 97% | unknown_tool_ids·started 형상·history 상한·401 고정 (잔여: #15 이월) |
| **Overall** | 92% | **97%** | 시나리오 커버리지 76.7% → 90% (13.5/15, #15 이월·#14 갈음) |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-08-19 | 최초 분석 — 92%, Critical 0 / Important 4 / Minor 6 / Deviation 10 |
| 0.2 | 2026-08-19 | Act-1 — Important 4건 전부 해소, Minor 5건 해소·G-06 반증(401), DoD #3/#8/#9 보강, #15 명시 이월 → **97%** |
