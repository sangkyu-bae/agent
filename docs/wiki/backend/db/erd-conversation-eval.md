---
title: 미니 ERD — 대화·평가 도메인 (conversation_message/summary, message_feedback)
status: draft
source_type: conversation
source_refs:
  - idt/src/infrastructure/persistence/models/conversation.py
  - idt/src/infrastructure/eval/models.py
  - idt/db/migration/V052__create_message_feedback.sql
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md
confidence: 0.9
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

구조는 SQLAlchemy 모델에서 도출(2026-07-21 기준). 이 도메인은 **FK가 하나도 없다** — 전부 소프트 참조.

```mermaid
erDiagram
    conversation_message |o..o{ message_feedback : "message_id (soft)"
    conversation_message }o..|| conversation_summary : "user_id+session_id 묶음 (soft)"

    conversation_message {
        int id PK
        string user_id
        string session_id
        string agent_id "default 'super'"
        string role "user|assistant|..."
        text content
        int turn_index
        json charts "V031, NULL=차트 없음"
        json analysis_data "V039, 분석 원천 스냅샷"
    }
    conversation_summary {
        int id PK
        string user_id
        string session_id
        string agent_id
        text summary_content
        int start_turn
        int end_turn
    }
    message_feedback {
        bigint id PK
        bigint message_id "assistant 메시지 id, UQ(message_id,user_id)"
        string user_id
        string agent_id "집계 인덱스용 비정규화"
        string rating "up|down"
        string comment "👎 이유, 500자"
    }
```

## 각주 (코드에 안 보이는 규칙)

- **평가 취소 = 행 삭제.** `message_feedback`에는 상태 컬럼이 없고 행 존재 자체가 평가 상태다. 같은 (message_id, user_id) upsert, 취소는 DELETE. 집계 0건은 0%가 아니라 None ([[feedback-toggle-row-delete]]).
- **세션은 테이블이 아니다.** `session_id`는 클라이언트가 발급하는 문자열이며 세션 마스터 테이블이 없다. 세션 목록은 `conversation_message` DISTINCT로 파생된다.
- `message_feedback.message_id`는 FK 없는 소프트 참조 (V052 주석: V037 선례 — [[mysql-fk-collation]]). 평가 UI가 메시지 id를 얻는 경로는 [[streaming-message-action-id]] (스트리밍 완료 이벤트의 additive `assistant_message_id` — [[additive-contract-extension]]).
- `message_feedback.agent_id`는 조인 회피용 비정규화 컬럼이다 (`idx_feedback_agent_rating`으로 에이전트별 만족도 집계).
- 👎 환류 파이프라인은 이 테이블을 기점으로 한다: 이유(comment) 있는 👎만 memory 후보(eval-feedback-loop)·wiki 초안(wiki-feedback-loop)으로 팬아웃, 반복 👎는 빈도 집계로 초안 강화(recurring-feedback-promotion). **이유 없는 👎는 상류에서 차단**된다.
- 대화 기록은 vector DB에 저장 금지 (idt/CLAUDE.md 금지 조항) — 요약은 `conversation_summary`가 담당.
