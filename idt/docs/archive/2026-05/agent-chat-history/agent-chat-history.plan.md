# AGENT-CHAT-001: 에이전트별 채팅 기록 관리

> 상태: Plan
> 연관 Task: CHAT-HIST-001 (대화 히스토리 API), CONV-001 (Multi-Turn 대화), AGENT-004 (Custom Agent Builder)
> 작성일: 2026-04-30
> 우선순위: High

---

## 1. 배경 및 목적 (Background)

현재 `conversation_message` 테이블은 `user_id + session_id` 기준으로 채팅을 저장한다.
그러나 **어떤 에이전트와 대화했는지** 구분이 없어서:

- 사용자가 커스텀 에이전트 A와의 대화 기록만 따로 볼 수 없음
- 일반 채팅과 에이전트 채팅이 같은 세션 목록에 섞여 있음
- 에이전트별 대화 통계/분석이 불가능

각 사용자가 **특정 에이전트별로 채팅 기록을 분리하여 조회**할 수 있어야 한다.

---

## 2. 목표 (Goals)

1. `conversation_message` 테이블에 `agent_id` 컬럼 추가 (기존 테이블 확장)
2. `conversation_summary` 테이블에도 동일하게 `agent_id` 추가
3. 일반 채팅(general_chat)은 `agent_id = "super"`로 통일
4. 기존 데이터 마이그레이션: agent_id가 NULL인 기존 레코드 → `"super"` 일괄 업데이트
5. 에이전트별 세션 목록 조회 API 구현
6. 에이전트별 세션 메시지 조회 API 구현
7. 채팅 저장 시 agent_id 자동 기록
8. TDD 방식으로 구현

---

## 3. 범위 외 (Non-Goals)

- 에이전트별 대화 통계 대시보드 (별도 기능)
- 대화 내용 수정/삭제 (DOC-DELETE-001 패턴 참고하여 별도 기획)
- 세션 제목 자동 생성 (별도 기능)
- 에이전트 간 대화 이전/복사
- 프론트엔드 UI 구현 (이번 Plan은 백엔드 API만, 프론트는 후속 Plan)

---

## 4. 핵심 설계 결정 (Key Decisions)

### 4-1. agent_id 값 규칙

| 대화 유형 | agent_id 값 | 설명 |
|-----------|------------|------|
| 일반 채팅 (`/api/v1/chat`) | `"super"` | 내장 ReAct 에이전트 |
| 대화형 채팅 (`/api/v1/conversation/chat`) | `"super"` | 기본 대화 에이전트 |
| 커스텀 에이전트 채팅 | `agent_definition.id` (UUID) | 사용자 정의 에이전트 |

### 4-2. 기존 데이터 마이그레이션

- `agent_id` 컬럼을 `VARCHAR(36)`, `NOT NULL`, `DEFAULT "super"`로 추가
- 기존 NULL 레코드는 마이그레이션 스크립트에서 `"super"`로 일괄 UPDATE
- `conversation_summary` 테이블도 동일 처리

### 4-3. 인덱스 전략

- 기존 인덱스 `ix_message_user_session (user_id, session_id)` 유지
- 새 인덱스 `ix_message_user_agent (user_id, agent_id)` 추가 — 에이전트별 세션 조회용

---

## 5. API 설계 (Endpoint Design)

### 5-1. 에이전트별 세션 목록 조회

```
GET /api/v1/conversations/agents/{agent_id}/sessions
Header: Authorization: Bearer {token}
```

**Response** (200):
```json
{
  "user_id": "user123",
  "agent_id": "super",
  "sessions": [
    {
      "session_id": "sess-abc",
      "message_count": 8,
      "last_message": "부동산 취득세 면제 조건이 뭔가요?",
      "last_message_at": "2026-04-30T10:30:00"
    }
  ]
}
```

- `agent_id` 기준 필터링 후 session_id 그룹핑
- `last_message_at` 내림차순 (최신 세션 먼저)

### 5-2. 에이전트 세션 메시지 조회

```
GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages
Header: Authorization: Bearer {token}
```

**Response** (200):
```json
{
  "user_id": "user123",
  "agent_id": "super",
  "session_id": "sess-abc",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "안녕하세요",
      "turn_index": 1,
      "created_at": "2026-04-30T09:00:00"
    }
  ]
}
```

### 5-3. 사용자의 에이전트 목록 (대화 기록이 있는)

```
GET /api/v1/conversations/agents
Header: Authorization: Bearer {token}
```

**Response** (200):
```json
{
  "user_id": "user123",
  "agents": [
    {
      "agent_id": "super",
      "agent_name": "일반 채팅",
      "session_count": 5,
      "last_chat_at": "2026-04-30T10:30:00"
    },
    {
      "agent_id": "uuid-xxx",
      "agent_name": "금융 분석 에이전트",
      "session_count": 3,
      "last_chat_at": "2026-04-29T15:00:00"
    }
  ]
}
```

- 대화 기록이 존재하는 에이전트만 반환
- `agent_id = "super"`인 경우 agent_name은 `"일반 채팅"` 하드코딩
- 그 외 agent_id는 `agent_definition` 테이블에서 name 조회

---

## 6. 아키텍처 설계 (Architecture)

### 레이어별 역할

```
interfaces/ (router)
  └─ conversation_history_router.py (기존 확장)
       ├─ GET /api/v1/conversations/agents
       ├─ GET /api/v1/conversations/agents/{agent_id}/sessions
       └─ GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages

application/ (use case)
  └─ ConversationHistoryUseCase (기존 확장)
       ├─ get_agents_with_history(user_id) → AgentListResponse
       ├─ get_sessions_by_agent(user_id, agent_id) → SessionListResponse
       └─ get_messages(user_id, agent_id, session_id) → MessageListResponse

infrastructure/ (repository 확장 + 마이그레이션)
  └─ SQLAlchemyConversationMessageRepository (기존 확장)
       ├─ find_agents_by_user(user_id) → List[AgentChatSummary]  ← 신규
       ├─ find_sessions_by_user_and_agent(user_id, agent_id) → List[SessionSummary]  ← 신규
       └─ find_by_session() ← 기존 확장 (agent_id 필터 추가)

domain/ (schemas/entities 확장)
  └─ conversation/
       ├─ entities.py: ConversationMessage에 agent_id 필드 추가
       ├─ value_objects.py: AgentId VO 추가
       └─ history_schemas.py: AgentChatSummary, AgentListResponse 추가
```

---

## 7. DB 스키마 변경 (Migration)

### V016__add_agent_id_to_conversation.sql

```sql
-- conversation_message 테이블에 agent_id 추가
ALTER TABLE conversation_message
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

-- 기존 데이터 마이그레이션 (이미 DEFAULT로 처리됨)
UPDATE conversation_message SET agent_id = 'super' WHERE agent_id = 'super';

-- conversation_summary 테이블에 agent_id 추가
ALTER TABLE conversation_summary
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

UPDATE conversation_summary SET agent_id = 'super' WHERE agent_id = 'super';

-- 에이전트별 조회 인덱스
CREATE INDEX ix_message_user_agent ON conversation_message (user_id, agent_id);
CREATE INDEX ix_summary_user_agent ON conversation_summary (user_id, agent_id);
```

---

## 8. 파일 변경 목록 (File Changes)

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/domain/conversation/entities.py` | ConversationMessage에 `agent_id` 필드 추가 |
| `src/domain/conversation/value_objects.py` | `AgentId` VO 추가 |
| `src/domain/conversation/history_schemas.py` | `AgentChatSummary`, `AgentListResponse` 추가 |
| `src/infrastructure/persistence/models/conversation.py` | `agent_id` 컬럼 추가 |
| `src/infrastructure/persistence/mappers/conversation_mapper.py` | agent_id 매핑 추가 |
| `src/infrastructure/persistence/repositories/conversation_repository.py` | 에이전트별 조회 메서드 추가 |
| `src/application/repositories/conversation_repository.py` | 추상 메서드 추가 |
| `src/application/conversation/history_use_case.py` | 에이전트별 조회 UseCase 추가 |
| `src/application/conversation/use_case.py` | 메시지 저장 시 agent_id 전달 |
| `src/api/routes/conversation_history_router.py` | 에이전트별 엔드포인트 추가 |
| `src/api/routes/general_chat_router.py` | 채팅 시 `agent_id="super"` 전달 |
| `src/api/routes/conversation_router.py` | 채팅 시 `agent_id="super"` 전달 |

### 신규 파일

| 파일 | 설명 |
|------|------|
| `db/migration/V016__add_agent_id_to_conversation.sql` | 마이그레이션 스크립트 |
| `tests/domain/conversation/test_agent_chat_schemas.py` | AgentChatSummary 스키마 테스트 |
| `tests/application/conversation/test_agent_history_use_case.py` | 에이전트별 히스토리 UseCase 테스트 |
| `tests/api/test_agent_conversation_history_router.py` | 에이전트별 API 라우터 테스트 |

---

## 9. TDD 계획 (Test Plan)

| 파일 | 테스트 수 | 설명 |
|------|----------|------|
| `test_agent_chat_schemas.py` | 4 | AgentChatSummary 생성, AgentId VO 검증, 기본값 "super" 확인 |
| `test_agent_history_use_case.py` | 10 | 에이전트 목록 조회, 에이전트별 세션 조회, 세션 메시지 조회, 빈 결과, agent_id 필터링 |
| `test_agent_conversation_history_router.py` | 8 | 200/400/404 응답, agent_id 파라미터 검증, 인증 검증 |

---

## 10. 구현 순서 (Implementation Order)

```
Phase 1: DB 스키마 변경
  └─ V016 마이그레이션 → ORM 모델 수정 → 엔티티/VO 수정

Phase 2: Domain & Repository 확장
  └─ AgentId VO → AgentChatSummary 스키마 → Repository 추상/구현

Phase 3: UseCase 확장
  └─ ConversationHistoryUseCase에 에이전트별 메서드 추가

Phase 4: API 엔드포인트
  └─ conversation_history_router에 에이전트별 엔드포인트 추가

Phase 5: 기존 채팅 흐름에 agent_id 연동
  └─ general_chat, conversation 채팅 시 agent_id="super" 전달
  └─ 커스텀 에이전트 채팅 시 agent_definition.id 전달
```

---

## 11. 완료 기준 (Definition of Done)

- [ ] `conversation_message`, `conversation_summary`에 `agent_id` 컬럼 존재
- [ ] 기존 데이터 `"super"`로 마이그레이션 완료
- [ ] `GET /api/v1/conversations/agents` 정상 동작
- [ ] `GET /api/v1/conversations/agents/{agent_id}/sessions` 정상 동작
- [ ] `GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages` 정상 동작
- [ ] 일반 채팅 시 `agent_id="super"` 자동 기록
- [ ] 커스텀 에이전트 채팅 시 해당 `agent_id` 자동 기록
- [ ] 전체 테스트 22개 통과
- [ ] `/verify-logging` 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-tdd` 통과

---

## 12. 의존성 (Dependencies)

- **CONV-001**: conversation_message 테이블 구조 재사용
- **CHAT-HIST-001**: 기존 히스토리 API 확장
- **AGENT-004**: agent_definition 테이블 (agent_id FK 참조)
- **AUTH-001**: JWT 토큰에서 user_id 추출
- **LOG-001**: 로깅 규칙 준수
- **MYSQL-001**: SQLAlchemy AsyncSession 패턴

---

## 13. 리스크 & 고려사항

| 리스크 | 대응 |
|--------|------|
| 기존 대화 기능 호환성 깨짐 | agent_id DEFAULT 'super'로 하위 호환 보장 |
| agent_definition 삭제 시 고아 레코드 | agent_id는 FK가 아닌 문자열 — 에이전트 삭제 후에도 기록 유지 |
| 인덱스 추가로 INSERT 성능 영향 | 대화 메시지 INSERT 빈도 낮아 무시 가능 |
| 프론트엔드 동시 변경 필요 | 이번 Plan은 백엔드만, 프론트는 후속 Plan에서 처리 |
