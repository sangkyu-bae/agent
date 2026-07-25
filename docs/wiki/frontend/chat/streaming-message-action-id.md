---
title: 채팅 메시지 단위 액션 부착 — 히스토리 id와 스트리밍 id의 양방향 해석
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md (§6 학습 포인트)
  - 커밋 fbafdaaf (idt_front/src/components/chat/MessageBubble.tsx, idt_front/src/hooks/useChatStream.ts)
confidence: 0.85
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
---

# 스트리밍 채팅에서 메시지 단위 액션(평가 등) 부착

## 문제

메시지 단위 서버 액션(평가, 신고 등)은 서버 메시지 id가 필요한데, 채팅 UI의 메시지는
출처가 둘이다:
1. **히스토리 로드 메시지** — 서버 numeric id 보유
2. **방금 스트리밍된 메시지** — 프론트가 만든 placeholder UUID뿐, 서버 id 없음

placeholder UUID로 API를 호출하면 실패하고, 스트리밍 직후 액션이 불가능해진다.

## 검증된 사실 (agent-eval-gate 프론트, 테스트 그린)

- 백엔드가 ANSWER_COMPLETED 이벤트에 `assistant_message_id`를 additive로 실어주고
  (저장 실패 시 None), 프론트는 이를 `Message.feedbackMessageId`로 전파:
  `types/websocket.ts` → `useChatStream` → NormalizedView → Message.
- `MessageBubble`의 **`feedbackId()` 단일 해석 함수**가 두 출처를 통합:
  - 히스토리 메시지 → numeric id 사용
  - 스트리밍 메시지 → `feedbackMessageId` 사용
  - 둘 다 없음(placeholder UUID만) → 액션 UI **자연히 미노출** (별도 분기 불필요)
- 토글 UI는 낙관적 업데이트 대신 **서버 왕복 후 캐시 갱신 + `isPending` disabled**로
  중복 클릭을 방지 (Report G1 — 의도적 대체, 낙관적 업데이트는 후속 개선 여지).
- 미연동 경계: agent(비 general-chat) 경로는 `ChatPage`에서 `assistantMessageId: null`로
  전달되어 평가 버튼 미노출 — 후속 작업 이월 상태.

## 다음에 적용하는 법

- 메시지 단위 액션을 새로 붙일 때 이 배선을 재사용한다: 서버 id를 완료 이벤트에
  additive 필드로 노출 → `feedbackMessageId`류 optional 필드 전파 → 단일 해석 함수.
- "id 없으면 미노출"을 기본 폴백으로 삼으면 placeholder·저장 실패·미연동 경로가
  전부 한 규칙으로 안전하게 처리된다.
- agent 경로에 액션을 확장할 때는 `ChatPage`의 `assistantMessageId: null` 지점부터 배선한다.
