# fix-agent-planner-hitl Gap Analysis (Check)

> **Match Rate: 100%** (94 / 94 가중 항목) — Act-1 반영 후. 최초 Check 95.2%
>
> **Design SoT**: `docs/02-design/features/fix-agent-planner-hitl.design.md`
> **Analyzer**: gap-detector agent + Act-1 수동 재검증
> **Date**: 2026-08-06 (Act-1: 동일)

---

## 1. 판정 요약

| 검사 영역 | 항목 수 | 점수 | 비고 |
|---|:---:|:---:|---|
| §2.1 도메인 VO | 4 | 4.0 | 전부 일치 |
| §2.2 PlannerPolicy | 4 | 4.0 | 전부 일치 |
| §2.3 AgentPlanner | 13 | 11.0 | G1·G3 |
| §2.4 인터페이스 | 2 | 2.0 | 전부 일치 |
| §2.5 DTO 계약 | 5 | 4.5 | G5 |
| §2.6 UseCase | 9 | 8.0 | G2·G4 |
| §2.7 Composer / §2.8 DI | 6 | 6.0 | 전부 일치 |
| §2.9 백엔드 테스트 | 4 | 4.0 | 전부 일치 |
| §3.1~3.4 프론트 | 21 | 21.0 | 전부 일치 |
| §3.5 프론트 테스트 | 3 | 2.5 | G6 |
| §5 결정 D1~D10 | 10 | 10.0 | 전부 반영 |
| Plan FR-01~FR-10 | 10 | 9.5 | FR-10 partial(G1) |
| 아키텍처 규칙 | 3 | 3.0 | 역참조 0·라우터 무변경 |
| **합계** | **94** | **89.5** | **95.2%** |

## 2. Gap 목록

| # | 심각도 | 위치 | 내용 | 조치 |
|---|:---:|---|---|---|
| G1 | Medium | `planner.py` trace metadata | 설계 §2.3 "metadata에 round" 누락 — FR-10의 라운드 관측이 needs_clarification 분기 로그에만 존재. 설계 자체도 §2.3/§2.4 시그니처에 round가 없는 내부 모순 | Act: `plan(..., round_)` 추가 + `metadata["round"]` 기록 |
| G2 | Low | `compose_agent_use_case.py` `_try_plan` | 폴백 경고가 `error=str(e)` — 스택 트레이스 유실(CLAUDE.md §6 위반 소지). planner.py의 `logger.error(exception=e)`가 완화 | Act: `exception=e`로 교체 |
| G3 | Low | `planner.py` ↔ UC | 질문 id 부여·clamp 책임이 설계(Planner)와 달리 UC에 위치 — Protocol 교체 지점 계약 약화 | Act: Planner에서도 clamp 적용(중복 무해) + 설계 문구 정정 |
| G4 | Low | UC 생성자 | `planner`가 optional 마지막 인자(설계는 필수 2번째) — 기존 테스트 무수정 통과를 위한 **의도적 개선** | 설계 문서 정정만 |
| G5 | Low | needs_clarification 응답 | `name_suggestion=request.name` 에코 — 설계 D7 "전부 빈 값"과 미세 불일치, 동작 영향 없음 | 설계 문서 정정만 |
| G6 | Low | MSW variant | 공용 handlers.ts 미확장, 테스트 파일 내 `server.use` 로컬 오버라이드로 대체(격리성 우수) | 설계 문서 정정만 |
| G7 | Low | 테스트 보강 | Composer `[빌드 계획]` 블록 부착 여부를 직접 검증하는 테스트 부재(UC 테스트는 인자 전달만 확인) | Act: 2케이스 추가 |

**의도적 개선(Gap 아님)**: `ClarifyQuestionCard`의 `isPending` prop(mutation-pending-guard 선례), `_maybe_clarification` 네이밍, FE 최초 요청 시 `clarification_round` 미전송(서버 기본 0).

## 3. 테스트 실행 결과 (세션 내 실측 — 분석 시점 확인 완료)

- 백엔드: `tests/domain/agent_composer/ + tests/application/agent_composer/` **78 passed** (신규 28건 포함), `tests/api/test_agent_composer_router.py` **4 passed**
- 프론트: fix 3파일 **28 passed** (신규 HITL 11건), 회귀 `useAgentComposer`·`AgentBuilderPage` **5 passed**, `tsc --noEmit` 클린
- 기존 compose 테스트 전부 **무수정 통과** — additive 계약 증명

## 4. 미검증 이월 (Report 시 명시)

- E2E 수동 시나리오: 모호 요청→질문 카드→답변→계획 반영 초안→적용 (create/edit 각 1회) — 서버 기동 필요
- LLM 2회 호출 지연 실측 (LangSmith run 시간)
- verify-architecture 스킬 공식 실행 (정적 검토로는 위반 없음 확인)

## 5. Act-1 반복 결과 (Gap 전량 해소 → 100%)

| Gap | 조치 | 검증 |
|-----|------|------|
| G1 (Medium) | `PlannerInterface.plan`/`AgentPlanner.plan`에 `round_: int = 0` 추가, UC가 clamp된 라운드 전달, trace `metadata["round"]`·start 로그 round 기록 | `test_round_recorded_in_trace_metadata` + UC `round_==1` 단언 |
| G2 (Low) | 폴백 경고 `error=str(e)` → `exception=e` — StructuredLogger `_log`의 명시 파라미터로 exc_info(스택 트레이스) 기록 확인 | 기존 폴백 테스트 통과 유지 |
| G3 (Low) | `AgentPlanner._to_result`에 `PlannerPolicy.clamp_questions` 적용 — 질문 상한을 Planner 계약으로 보장(UC 이중 방어 무해) | `test_questions_clamped_by_planner_contract` |
| G7 (Low) | `TestAgentComposerPlanInjection` 2케이스 — plan 주입 시 `[빌드 계획]`/`[계획 준수 규칙]` 블록 부착, plan=None 시 미부착 | 신규 테스트 통과 |
| G4·G5·G6 (Low) | 설계 문서를 구현 사실로 정정(§2.3 후처리 주체, §2.4 round_ 시그니처, §2.5 D7 name_suggestion 에코, §2.6 planner optional 인자, §3.5 MSW 로컬 오버라이드) | 문서 diff |

**Act-1 후 테스트**: 백엔드 composer 관련 **86 passed** (Act-1 신규 4건 포함: clamp 1·round 2·plan 블록 2 중 트레이싱 단언 1건은 기존 테스트 확장). 프론트 변경 없음(이전 실측 33건 유효).

**재계산**: 최초 차감 4.5점(G1 1.0 + G3 1.0 + G2 0.5 + G4 0.5 + G5 0.5 + G6 0.5 + FR-10 0.5) 전량 회복 → **94/94 = 100%**.

## 6. 다음 단계

`/pdca report fix-agent-planner-hitl` — E2E 수동 시나리오·지연 실측은 Report에 이월 항목으로 명시.
