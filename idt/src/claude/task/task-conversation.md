# CONV-001: Multi-Turn 대화 메모리 관리 UseCase

> 상태: 완료
> 의존성: LOG-001 (로깅), MYSQL-001 (DB 저장소)

---

## 개요

사용자 메시지를 받아 세션 기반 대화 히스토리를 관리하고, 6턴 초과 시 오래된 대화를 요약하여 LLM 토큰 폭증을 방지하는 Multi-Turn 대화 UseCase.

---

## 동작 흐름

```
1. 유저가 메시지 전송
2. session_id로 기존 메시지 조회 (ConversationMessageRepository)
3. 유저 메시지 DB 저장 (turn_index = len(existing) + 1)
4. 토큰 초과 여부 체크 (SummarizationPolicy: threshold=6)
   ├─ 괜찮으면 → 전체 히스토리 + 새 메시지로 컨텍스트 구성
   └─ 초과면   → 오래된 턴(1 ~ N-3) 요약 → ConversationSummary 저장
                → (system: 요약 + 최근 3턴 + 새 메시지)로 컨텍스트 구성
5. LLM 호출 (ConversationLLMInterface)
6. 어시스턴트 응답 DB 저장 (turn_index = len(existing) + 2)
7. ConversationChatResponse 반환 (was_summarized 포함)
```

---

## 아키텍처

### Domain Layer
- `src/domain/conversation/schemas.py`
  - `ConversationChatRequest`: user_id, session_id, message
  - `ConversationChatResponse`: user_id, session_id, answer, was_summarized, request_id
- `src/domain/conversation/entities.py` (기존)
  - `ConversationMessage`, `ConversationSummary`
- `src/domain/conversation/value_objects.py` (기존)
  - `UserId`, `SessionId`, `TurnIndex`, `MessageRole`
- `src/domain/conversation/policies.py` (기존)
  - `SummarizationPolicy(threshold=6, keep_recent=3)`
    - `needs_summarization(messages)`: len > threshold
    - `get_turns_to_summarize(messages)`: 첫 N-3 턴
    - `get_recent_turns(messages)`: 마지막 3턴
    - `get_summary_range(messages)`: (start_turn, end_turn) 인덱스

### Application Layer
- `src/application/conversation/interfaces.py`
  - `ConversationSummarizerInterface`: `summarize(messages, request_id) -> str`
  - `ConversationLLMInterface`: `generate(messages: list[dict], request_id) -> str`
- `src/application/conversation/use_case.py`
  - `ConversationUseCase`

### Infrastructure Layer
- `src/infrastructure/conversation/langchain_summarizer.py`
  - `LangChainSummarizer(ConversationSummarizerInterface)`
  - `ChatOpenAI` 활용, 사실 중심 요약 프롬프트
- `src/infrastructure/conversation/langchain_llm.py`
  - `LangChainConversationLLM(ConversationLLMInterface)`
  - `ChatOpenAI` 활용, system/user/assistant role 매핑

### API Layer
- `src/api/routes/conversation_router.py`
  - `POST /api/v1/conversation/chat`
  - Request: `{user_id, session_id, message}`
  - Response: `{user_id, session_id, answer, was_summarized, request_id}`

---

## 요약 정책 (SummarizationPolicy)

| 항목 | 값 |
|------|-----|
| 요약 트리거 임계값 | 6턴 초과 |
| 요약 대상 | turn 1 ~ N-3 |
| 컨텍스트 유지 | 최근 3턴 |
| 요약 스타일 | 사실 중심 (결정사항, 사용자 의도, 중요 제약) |
| 질문/답변 형식 | 금지 |

---

## 로깅 (LOG-001 준수)

모든 서비스에 `LoggerInterface` 주입. 처리 시작/완료 INFO, 에러 ERROR (exception= 포함).

---

## 테스트

| 파일 | 케이스 수 | 비고 |
|------|----------|------|
| `tests/domain/conversation/test_chat_schemas.py` | 4 | mock 금지 |
| `tests/application/conversation/test_use_case.py` | 12 | AsyncMock |
| `tests/infrastructure/conversation/test_langchain_services.py` | 6 | ChatOpenAI mock |
| `tests/api/test_conversation_router.py` | 8 | UseCase mock |
| **합계** | **30** | |

---

## DB 의존성

- `conversation_message` 테이블: `id, user_id, session_id, role, content, turn_index, created_at`
- `conversation_summary` 테이블: `user_id, session_id, summary_content, start_turn, end_turn, created_at`
- `AsyncSession` per-request (lifespan 초기화 불필요)
