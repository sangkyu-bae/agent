# General Chat API

> 자동 생성 일시: 2026-04-12  
> 관련 파일: `src/api/routes/general_chat_router.py`

---

## 인증

모든 요청에 `Authorization: Bearer <access_token>` 헤더가 필요합니다.

토큰은 `POST /api/v1/auth/login` 으로 발급받습니다.

---

## chat

### `POST /api/v1/chat`

**설명**: LangGraph ReAct 에이전트가 질문을 분석하고 아래 도구를 자율적으로 선택·조합하여 응답합니다.

**인증 필요**: ✅

**사용 가능한 도구**
| 도구 | 설명 |
|------|------|
| `tavily_search` | 실시간 웹 검색 |
| `hybrid_document_search` | 내부 문서 BM25 + Vector 하이브리드 검색 |
| MCP 등록 도구 | DB에 등록된 MCP 서버 도구 동적 로드 |

**대화 메모리 정책**
- `user_id` + `session_id` 단위로 멀티턴 대화 유지
- 대화 턴이 **6개를 초과**하면 이전 턴을 자동 요약
- 요약 이후에는 **요약본 + 최근 3턴**만 컨텍스트로 사용

---

#### Request Body

```json
{
  "user_id": "user-abc123",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "2024년 금융 정책 변경사항을 알려줘",
  "top_k": 5
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `user_id` | string | ✅ | — | 요청 사용자 ID |
| `session_id` | string \| null | ❌ | null | 대화 세션 ID. 생략 시 서버에서 UUID 신규 발급 |
| `message` | string | ✅ | — | 사용자 질문 메시지 |
| `top_k` | integer | ❌ | `5` | 내부 문서 검색 결과 수 |

---

#### Response `200`

```json
{
  "user_id": "user-abc123",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "answer": "2024년 금융 정책 주요 변경사항은 다음과 같습니다...",
  "tools_used": ["tavily_search", "hybrid_document_search"],
  "sources": [
    {
      "content": "2024년 1월부터 금융위원회는...",
      "source": "financial_policy_2024.pdf",
      "chunk_id": "chunk-001-page-3",
      "score": 0.87
    }
  ],
  "was_summarized": false,
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `user_id` | string | 요청 사용자 ID |
| `session_id` | string | 대화 세션 ID (신규 발급 또는 요청 값 그대로 반환) |
| `answer` | string | 에이전트 생성 답변 |
| `tools_used` | string[] | 이번 응답에서 에이전트가 사용한 도구 목록 |
| `sources` | DocumentSource[] | 내부 문서 검색 출처 목록. 웹 검색만 사용한 경우 빈 배열 |
| `was_summarized` | boolean | 이번 응답에서 대화 히스토리 요약이 수행되었는지 여부 |
| `request_id` | string | 요청 추적용 UUID (서버 로그 조회 시 사용) |

**DocumentSource 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `content` | string | 검색된 문서 청크 내용 |
| `source` | string | 출처 파일명 또는 URL |
| `chunk_id` | string | 문서 청크 고유 ID |
| `score` | float | 검색 관련도 점수 (0.0 ~ 1.0) |

---

#### 에러 응답

| 코드 | 설명 |
|------|------|
| `401` | 인증 실패 — 토큰 없음 또는 만료 |
| `422` | 요청 유효성 검사 실패 (`user_id` 또는 `message` 누락 등) |

```json
// 401
{ "detail": "Not authenticated" }

// 422
{ "detail": "field required" }
```

---

#### curl 예시

**새 세션 시작**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-abc123",
    "message": "2024년 금융 정책 변경사항을 알려줘",
    "top_k": 5
  }'
```

**기존 세션 이어서 대화**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-abc123",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "message": "방금 말한 내용 중 가계대출 부분을 더 자세히 설명해줘"
  }'
```
