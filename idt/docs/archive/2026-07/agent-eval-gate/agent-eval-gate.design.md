# agent-eval-gate Design Document

> **Plan**: `docs/01-plan/features/agent-eval-gate.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 실코드 (general_chat/use_case.py:389·745 _persist_messages · ConversationMessage(id·agent_id) · agent_run_router messages/{id}/retrievals · admin_dashboard_router · MessageId VO)

---

## 1. Plan 이월 결정 4건 — 확정

| # | 결정 | 확정안 | 근거 (실측) |
|---|------|--------|------|
| ① | 평가 부착 키 | **conversation message_id** (assistant 메시지) | 메시지가 사용자 대면 답변 단위. `ConversationMessage.id`(MessageId) 존재, retrieval-observability가 이미 message_id로 조회 |
| ② | 취소 표현 | **행 삭제** (up→down→취소 토글) — upsert로 up/down 갱신, 같은 값 재클릭 시 삭제 | 단순·상태 없음. 집계는 존재 행만 세면 됨 |
| ③ | 집계 API 위치 | **신규 eval 라우터** (`/api/v1/admin/eval/*`, admin) — admin 대시보드 위젯이 소비 | 피드백 도메인이 자기 집계 소유(dashboard 라우터 비대화 방지) |
| ④ | 스트리밍 답변 id | **ANSWER_COMPLETED에 `assistant_message_id` additive 노출** — `_persist_messages`가 이미 `_msg_repo.save(ai_msg)`로 저장(반환 엔티티 id 보유, 현재 버림)하므로 캡처만 | 방금 답변 즉시 평가 + 히스토리(Message.id)에서도 평가 가능. 저장 실패 시 None(FR-07) |

## 2. Architecture

```
[저장] message_feedback (V052)
  message_id BIGINT · user_id VARCHAR · agent_id VARCHAR · rating VARCHAR(4) 'up'|'down'
  · comment VARCHAR(500) NULL · created_at · updated_at
  UNIQUE(message_id, user_id)  ← 1인 1메시지 1평가(upsert)
  INDEX(agent_id, rating)      ← 집계

[API]
  POST   /conversations/messages/{message_id}/feedback  {rating, comment?}  → upsert (본인)
         같은 rating 재요청이면 삭제(취소, 결정 ②)
  DELETE /conversations/messages/{message_id}/feedback                       → 취소
  GET    /conversations/messages/{message_id}/feedback                       → 본인 값(없으면 null)
  GET    /api/v1/admin/eval/agents            → 에이전트별 만족도(up/(up+down))·평가수 (admin)
  GET    /api/v1/admin/eval/recent-negative   → 최근 부정 피드백 N건 (admin)

[general_chat] _persist_messages: saved_ai = await _msg_repo.save(ai_msg)
  → assistant_message_id 반환(추가), ANSWER_COMPLETED payload에 포함(결정 ④)

[프론트]
  채팅 assistant 메시지: 👍/👎 토글(낙관적, useMessageFeedback) — assistant_message_id 사용
  admin 대시보드: 만족도 위젯(에이전트별 %) + 최근 부정 피드백
```

## 3. Detailed Design

### 3-1. DB — V052

```sql
-- V052__create_message_feedback.sql
-- agent-eval-gate: 답변 사용자 평가. FK/COLLATE 명시 없음(V037 선례), ENGINE=InnoDB.
CREATE TABLE message_feedback (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    message_id  BIGINT       NOT NULL COMMENT 'conversation_message.id (assistant)',
    user_id     VARCHAR(255) NOT NULL,
    agent_id    VARCHAR(64)  NOT NULL COMMENT '메시지 agent_id 파생(general-chat 포함)',
    rating      VARCHAR(4)   NOT NULL COMMENT 'up|down',
    comment     VARCHAR(500) NULL,
    created_at  DATETIME     NOT NULL,
    updated_at  DATETIME     NOT NULL,
    UNIQUE KEY uq_feedback_msg_user (message_id, user_id),
    INDEX idx_feedback_agent_rating (agent_id, rating)
) ENGINE=InnoDB;
```

### 3-2. Domain (`domain/eval/`)

```python
class Rating(str, Enum): UP = "up"; DOWN = "down"

@dataclass
class MessageFeedback:
    id: int | None; message_id: int; user_id: str; agent_id: str
    rating: Rating; comment: str | None = None
    created_at: datetime | None = None; updated_at: datetime | None = None

class EvalPolicy:
    COMMENT_MAX = 500
    @staticmethod
    def validate_comment(comment: str | None) -> None: ...   # 500자 초과 ValueError
    @staticmethod
    def satisfaction(up: int, down: int) -> float | None:
        """up/(up+down). 평가 0건이면 None (0 나눗셈 방지)."""

class MessageFeedbackRepositoryInterface(ABC):
    find_by_message_and_user / upsert / delete
    aggregate_by_agent → [(agent_id, up, down)]
    recent_negative(limit) → [MessageFeedback]
```

### 3-3. Application

- **`SubmitFeedbackUseCase`**: message 소유·존재 검증(메시지 조회 — 타 세션 메시지 평가 차단) → agent_id 파생 → 같은 rating 존재 시 삭제(취소) else upsert. comment 검증
- **`GetFeedbackUseCase`**: 본인 값(없으면 None)
- **`AgentEvalStatsUseCase`**: aggregate_by_agent → satisfaction 계산 + recent_negative

### 3-4. Interfaces

- `agent_run_router` 또는 신규 `eval_router`에 feedback 3종(POST/GET/DELETE) — 본인(str(user.id)), 401 / 타·미존재 404 은닉(메모리 계약)
- 신규 `/api/v1/admin/eval/*` 2종 — require_role("admin")
- **general_chat 통합**: `_persist_messages` 반환을 `(user_message_id, assistant_message_id)` 튜플로 확장 — 호출부(stream)가 ANSWER_COMPLETED payload에 `assistant_message_id` 추가. 저장 실패 시 None
- config: `eval_recent_negative_limit: int = 20`

### 3-5. Frontend

- 계약: `MESSAGE_FEEDBACK(id)`·`ADMIN_EVAL_AGENTS`·`ADMIN_EVAL_RECENT_NEG`, types(`Rating`·`MessageFeedback`·`AgentEvalStat`), service, 훅(`useMessageFeedback`·`useSubmitFeedback`·`useAgentEvalStats`)
- ChatEvent/Message 타입에 `assistant_message_id?` 추가 (스트리밍·히스토리)
- MessageBubble(assistant): 👍/👎 토글 — 낙관적 업데이트, 실패 롤백(FR-06), message id 없으면 미표시
- AdminDashboardPage: 만족도 위젯(에이전트별 %) + 최근 부정 피드백 리스트

## 4. Test Plan (TDD)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/eval/test_policies.py` | validate_comment · satisfaction(정상·0건 None) |
| `tests/infrastructure/eval/test_repository.py` | upsert(신규·갱신)·delete·aggregate_by_agent·recent_negative (SQLite) |
| `tests/application/eval/test_submit_feedback.py` | 신규/갱신/같은값 취소·타 메시지 404·comment 초과 422 |
| `tests/application/eval/test_agent_eval_stats.py` | 만족도·부정 목록 |
| `tests/api/test_eval_router.py` | POST/GET/DELETE 401·404 / admin 집계 401·403 |
| `tests/application/general_chat/` | _persist_messages 튜플 반환 · ANSWER_COMPLETED에 assistant_message_id · 회귀 0 |
| 프론트 | useMessageFeedback 토글·롤백 · MessageBubble 👍/👎 · 대시보드 만족도 위젯 |

## 5. Implementation Order

1. V052 + domain(entity·policy·interface) — 정책 테스트 먼저
2. Repository(upsert/delete/aggregate) — SQLite 테스트
3. SubmitFeedback/GetFeedback/AgentEvalStats UC
4. eval_router(feedback 3 + admin 2) + config + main DI
5. general_chat _persist_messages 튜플 + ANSWER_COMPLETED — 회귀 0 확인
6. 프론트 계약 + MessageBubble 토글 + 대시보드 위젯
7. verify → analyze

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 해소 |
|-------------|------|
| 스트리밍 message_id 노출 | 결정 ④ — save 반환 id 캡처 → ANSWER_COMPLETED additive (히스토리도 Message.id) |
| agent_id 파생 | 메시지 조회 시 agent_id 사용(저장 시 이미 보유) |
| 남용 | UNIQUE(message_id,user_id) + 인증 |
| 집계 비용 | INDEX(agent_id, rating) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | 이월 4건 확정(message_id 키·취소=삭제·신규 eval 라우터·ANSWER_COMPLETED assistant_message_id 노출), V052 스키마 | 배상규 |
