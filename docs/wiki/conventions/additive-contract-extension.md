---
title: API·WS 계약 확장은 additive + 응답 타입 분리 — 기존 소비자 무변경으로 회귀 0
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/expose-user-department/expose-user-department.report.md (결정 ③, Lessons 3)
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md (§2 결정 ④)
  - 커밋 fbafdaaf (idt_front/src/types/websocket.ts — assistant_message_id 가법 전파)
confidence: 0.85
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
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

## 다음에 적용하는 법

- 특정 엔드포인트에만 필요한 필드 → 그 엔드포인트 전용 **신규 응답 타입** 생성,
  공용 스키마는 건드리지 않는다.
- WS 이벤트 확장 → 기존 필드 변경 금지, 신규 optional 필드 추가.
  백엔드는 실패 시 None, 프론트는 부재 시 기능 미노출로 양쪽 하위호환.
- 설정/모드 확장 → 기존 enum 값 추가 대신 신규 bool 필드 + 분기 (기존 동작을
  교차검증 기준선으로 보존). 이는 사용자가 명시적으로 선호를 밝힌 방식이다.
- CLAUDE.md 4-1(API 계약 동기화)에 따라 백엔드 스키마 추가 시 `idt_front/src/types/` 동시 수정.
