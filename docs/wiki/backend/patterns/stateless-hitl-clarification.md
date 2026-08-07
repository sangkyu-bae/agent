---
title: Stateless HITL 질문 왕복 — 에코백 계약 + 서버 clamp + Planner 2단계
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/application/agent_composer/compose_agent_use_case.py (_try_plan/_maybe_clarification)
  - idt/src/domain/agent_composer/policies.py (PlannerPolicy)
  - idt/src/application/agent_composer/interfaces.py (PlannerInterface — application 레이어 배치 이유 주석)
  - idt/src/application/agent_composer/planner.py (AgentPlanner)
  - idt_front/src/components/agent-builder/fix/FixAgentPanel.tsx (sendCompose/pendingClarify)
  - docs/archive/2026-08/fix-agent-planner-hitl/fix-agent-planner-hitl.report.md (D5/D7/D8/D9, Match 100%)
  - 커밋 5bee1d71·923b05e3 (PR #49, 머지 18fd521e)
confidence: 0.9
version: 1
created: 2026-08-06
updated: 2026-08-07
verified_at: 18fd521e
---

# Stateless HITL 질문 왕복 — 에코백 계약 + 서버 clamp

## 문제

LLM이 사용자 요청을 1회 추측으로 처리하면 모호한 요청에서 시행착오가 반복된다.
"부족하면 되묻기"(HITL)를 넣고 싶지만, 세션/DB 상태를 추가하면 마이그레이션·만료 정책·
동시성 관리가 따라온다. `/api/v1/agents/compose`(Fix 탭)는 **세션 없이** 다회 질문↔응답
왕복을 성립시켰다 (fix-agent-planner-hitl, Match 100%, 마이그레이션 0).

## 검증된 사실

1. **에코백 계약 (D8)**: 서버는 자신이 낸 질문을 기억하지 않는다. 답변 DTO
   (`ClarificationAnswerDto`)에 **질문 텍스트를 그대로 실어 되돌려**, 서버가 요청
   페이로드만으로 Q/A 맥락을 재구성한다. 프론트는 `pendingClarify` 상태에 질문+원요청을
   보관했다가 `sendCompose` 재호출 시 동봉한다 (FixAgentPanel.tsx).
2. **클라이언트 신고값은 재clamp**: 라운드 번호는 클라이언트가 `clarification_round`로
   신고하지만 서버가 `PlannerPolicy.clamp_round`로 0..MAX(2) 범위에 강제 clamp한다
   (음수·과대값 조작 방어). 질문 수도 `clamp_questions`로 상한(3) 강제. 임계값
   (`CONFIDENCE_THRESHOLD=0.8`)·상한은 전부 도메인 정책 상수로 계약화.
3. **Planner→Composer 2단계 + Protocol 교체 지점 (D2/D9)**: AgentPlanner(계획·질문)와
   AgentComposer(초안 조합)를 분리하고 UseCase는 `PlannerInterface`(Protocol)에만 의존.
   **Protocol 파라미터가 application DTO(`ComposeCurrentConfig`)를 포함하므로 domain이
   아닌 application 레이어에 둔다** — domain→application 역참조 방지. 추후 LangGraph
   interrupt 기반 구현체로 DI 교체만으로 전환 가능.
4. **도구 선택은 방향 힌트만 (D5)**: Planner는 도구 "방향 힌트"만 제시하고, 최종
   결정·검증(후보 밖 tool_id drop, 개수 clamp, MCP 매핑)은 Composer+서버 보정이 그대로
   유지된다 — Planner 오판의 복구 경로 보존.
5. **Planner 장애 = 기존 동작 폴백 (FR-08)**: `_try_plan`이 예외를 삼키고 None 반환 →
   기존 단발 compose로 진행. 신규 협력자 장애가 기능 가용성을 깎지 않는다.
6. **함정 — `auto_agent_builder`(v3)와 혼동 금지**: v3 자동 빌더에 세션 기반
   clarification 루프가 이미 있지만 Fix 탭(compose)과 **무관한 별개 경로**다.
   플랜 단계에서 프론트 훅(`useComposeAgent`)부터 역추적해 실제 소비 경로를 확정해야
   스코프 오판(기존 루프 재활용 착각)을 막는다.

## 다음에 적용하는 법

- 무상태 API에 다회 왕복 대화가 필요하면: 세션 테이블부터 만들지 말고 **① 서버 산출물
  (질문)을 클라이언트가 에코백, ② 클라이언트 신고 카운터는 서버 정책으로 재clamp**의
  2요소로 성립하는지 먼저 검토한다.
- 신규 판단 모듈은 Protocol 뒤에 두되, **시그니처가 application DTO를 물면 Protocol도
  application에** 둔다 (domain에 두면 역참조 발생).
- 신규 모듈 실패는 예외 전파 대신 "미주입/실패 = 기존 경로 폴백"으로 설계해 additive를
  유지한다 (하위호환 주입 방식은 [[additive-contract-extension]] 참조).
- E2E(질문 카드→답변→초안)와 지연 실측(LLM 2회 경로 +5s 목표)은 이월 상태 —
  [[e2e-carryover-checklist]] 확인.
