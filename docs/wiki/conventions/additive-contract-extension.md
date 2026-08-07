---
title: API·WS 계약 확장은 additive + 응답 타입 분리 — 기존 소비자 무변경으로 회귀 0
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/expose-user-department/expose-user-department.report.md (결정 ③, Lessons 3)
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md (§2 결정 ④)
  - 커밋 fbafdaaf (idt_front/src/types/websocket.ts — assistant_message_id 가법 전파)
  - idt/src/application/agent_composer/compose_agent_use_case.py (planner optional 마지막 인자)
  - docs/archive/2026-08/fix-agent-planner-hitl/fix-agent-planner-hitl.report.md (Lessons 2, D7)
confidence: 0.85
version: 2
created: 2026-07-20
updated: 2026-08-06
verified_at: 18fd521e
---

# 계약 확장은 additive + 응답 타입 분리

## 문제

기존 REST 응답 스키마나 WebSocket 이벤트 payload에 필드가 필요해질 때,
공용 스키마를 직접 수정하면 그 스키마의 다른 소비자 전부가 영향권에 들어간다.
사용자(프로젝트 오너)도 기존 설정을 갈아끼우는 방식을 일관되게 거부한다
(기존 enum 값 추가조차 거부된 선례 있음 — 독립 opt-in 선호).

## 검증된 사실

1. **응답 타입 분리** (expose-user-department, Match 100% · 회귀 0):
   `/auth/me`에 부서를 넣을 때 `UserResponse`를 확장하지 않고 **신규 `MeResponse`**를
   만들어 `/me`만 전환했다. `UserResponse` 소비자 4곳(로그인 등)은 무변경.
2. **WS 이벤트 additive 필드** (agent-eval-gate, 회귀 0):
   ANSWER_COMPLETED payload에 `assistant_message_id`를 **가법 추가**하고,
   저장 실패 시 `None` 폴백으로 채팅 흐름을 차단하지 않았다(FR-07).
   프론트는 부재 시 해당 UI(평가 버튼)를 미노출하는 하위호환 처리.
3. 프론트 전파 체인도 각 단계에서 optional로 유지:
   `types/websocket.ts` → `useChatStream` → NormalizedView → `Message.feedbackMessageId`.
4. **생성자에도 같은 원리 — optional 마지막 인자 주입** (fix-agent-planner-hitl, Match 100%):
   기존 UseCase에 신규 협력자를 넣을 때 `planner: PlannerInterface | None = None`을
   **마지막 인자**로 추가하면 기존 테스트 13건이 **무수정 통과** — 통과 자체가 additive
   계약의 구조적 증명이 된다. 미주입 시 기존 동작과 완전 동일(폴백)해야 한다.
5. **신규 상태값은 구형 소비자용 안전 강하를 함께 설계** (fix-agent-planner-hitl D7):
   응답에 `status="needs_clarification"`을 추가하면서, status 필드를 모르는 구형
   소비자를 위해 같은 응답을 `coverage="none"`+빈 초안으로도 표현했다. 프론트 타입도
   신규 필드(`status?`/`questions?`/`plan_summary?`)를 전부 optional로 선언해
   구형 mock/응답과 호환 (`idt_front/src/types/agentComposer.ts`).

## 다음에 적용하는 법

- 특정 엔드포인트에만 필요한 필드 → 그 엔드포인트 전용 **신규 응답 타입** 생성,
  공용 스키마는 건드리지 않는다.
- WS 이벤트 확장 → 기존 필드 변경 금지, 신규 optional 필드 추가.
  백엔드는 실패 시 None, 프론트는 부재 시 기능 미노출로 양쪽 하위호환.
- 설정/모드 확장 → 기존 enum 값 추가 대신 신규 bool 필드 + 분기 (기존 동작을
  교차검증 기준선으로 보존). 이는 사용자가 명시적으로 선호를 밝힌 방식이다.
- 기존 UseCase/서비스에 협력자 추가 → **optional 마지막 인자 + 미주입 시 기존 경로
  폴백**. 기존 테스트가 무수정 통과하는지를 하위호환 검증 기준으로 삼는다.
- 응답에 신규 상태/모드 값 추가 → 구형 소비자가 그 값을 몰라도 깨지지 않는
  안전 강하 표현(기존 필드 의미론 재사용)을 같이 설계한다.
- CLAUDE.md 4-1(API 계약 동기화)에 따라 백엔드 스키마 추가 시 `idt_front/src/types/` 동시 수정.
