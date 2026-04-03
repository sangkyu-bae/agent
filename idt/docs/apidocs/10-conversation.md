# 대화 메모리 API (Multi-Turn Conversation)

> **태그**: `conversation`
> **Base Path**: `/api/v1/conversation`

---

## 개요

대화 히스토리를 MySQL에 저장하고, 멀티턴 컨텍스트로 LLM 답변을 생성합니다.

### 핵심 기능: 자동 요약

대화가 길어지면 LLM 비용이 증가하고 컨텍스트 한도를 초과할 수 있습니다. 이를 해결하기 위해 **6턴 초과 시 자동으로 오래된 대화를 요약**합니다.

```
대화 1턴: "안녕하세요"
대화 2턴: "금리가 뭐에요?"
대화 3턴: "왜 금리를 올려요?"
대화 4턴: "올리면 어떤 영향이 있어요?"
대화 5턴: "집값은요?"
대화 6턴: "주식은요?"
────────── 6턴 초과! 자동 요약 트리거 ──────────
대화 7턴: 요약본 + 최근 3턴(4~6) 컨텍스트로 질의
```

### 요약 규칙

- 대화가 **6턴을 초과**하면 요약 실행
- 1번 ~ (전체-3)번 대화를 요약
- 이후 질의는 **요약본 + 최근 3턴**만 사용
- 요약은 MySQL `conversation_summary` 테이블에 저장

---

## 엔드포인트

### 대화 질의

**`POST /api/v1/conversation/chat`**

#### 요청 (JSON)

```json
{
  "user_id": "user_001",
  "session_id": "session_abc123",
  "message": "기준금리 인상이 대출 금리에 어떤 영향을 미치나요?"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | string | ✅ | 사용자 ID |
| `session_id` | string | ✅ | 대화 세션 ID (같은 세션 = 같은 대화) |
| `message` | string | ✅ | 사용자 메시지 |

#### session_id 사용 방법

- **같은 대화를 이어가려면**: 동일한 `session_id` 사용
- **새 대화를 시작하려면**: 새 `session_id` 사용 (예: UUID 생성)
- 여러 사용자가 독립된 대화를 가지려면: `user_id + session_id` 조합으로 구분

#### 응답 (200 OK)

```json
{
  "user_id": "user_001",
  "session_id": "session_abc123",
  "answer": "기준금리가 인상되면 은행의 자금 조달 비용이 높아져 주택담보대출, 신용대출 등 대출 금리가 함께 상승합니다. 일반적으로 기준금리 1% 인상 시 대출 금리는 0.5~1% 수준 상승하는 경향이 있습니다.",
  "was_summarized": false,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 필드 | 설명 |
|------|------|
| `answer` | LLM이 생성한 답변 |
| `was_summarized` | 이번 요청에서 요약이 실행되었는지 여부 |
| `request_id` | 요청 추적 ID |

#### 예제 — 새 대화 시작

```bash
# 첫 번째 메시지
curl -X POST "http://localhost:8000/api/v1/conversation/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "session_id": "session_001",
    "message": "금리가 뭔가요?"
  }'

# 대화 이어가기 (같은 session_id)
curl -X POST "http://localhost:8000/api/v1/conversation/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "session_id": "session_001",
    "message": "방금 설명한 금리가 높아지면 어떤 일이 생기나요?"
  }'
```

---

## 데이터 저장 구조

대화 데이터는 MySQL에 저장됩니다:

| 테이블 | 내용 |
|--------|------|
| `conversation_message` | 개별 메시지 (user/assistant 역할 구분) |
| `conversation_summary` | 요약된 대화 내용 |

> Vector DB(Qdrant/ES)에는 대화 내용을 저장하지 않습니다. 문서와 대화 데이터를 명확히 분리합니다.

---

## 주의사항

- 동일 `session_id`로 계속 대화하면 이전 맥락이 유지됩니다
- 요약은 자동으로 실행되며 별도 API 호출 없이도 처리됩니다
- 이 API는 RAG 검색을 포함하지 않습니다. 내부 문서 기반 대화는 [RAG 에이전트 API](./09-rag-agent.md)를 사용하세요
