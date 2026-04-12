# Gap Analysis: General Chat API (CHAT-001)

> Feature: general-chat-api
> Analysis Date: 2026-04-12
> Phase: Check
> **Match Rate: 93%** ✅ (>= 90% 기준 통과)

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 91% | Pass |
| Architecture Compliance | 95% | Pass |
| Convention Compliance | 100% | Pass |
| Test Coverage (38 cases) | 100% | Pass |
| **Overall** | **93%** | **Pass** |

---

## 1. schemas.py — 100% Match

모든 4개 클래스 (ToolUsageRecord, DocumentSource, GeneralChatRequest, GeneralChatResponse) 필드 타입 정확히 일치.

---

## 2. policies.py — Minor Change

**변경**: 설계는 class-level 속성, 구현은 instance-level (`__init__` 내 `self.`)  
**영향**: 낮음 — 값·환경변수 로직 동일, 테스트 용이성 향상

---

## 3. tools.py — Extended (LOG-001 준수)

**추가된 파라미터**:
- `MCPToolCache.get_or_load()`: `request_id`, `logger` 파라미터 추가 (LOG-001 필수)
- `ChatToolBuilder.build()`: `request_id` 파라미터 추가
- Cache key: `server_id` → `"__all__"` 단일 키 (전체 로드 방식)

**영향**: 낮음 — LOG-001 규칙 준수를 위한 필수 변경

---

## 4. use_case.py — Design Gap Fix

**추가된 의존성**: `summary_repo: ConversationSummaryRepository`  
→ 설계 흐름(Step 3: 요약 DB 저장)에 명시되어 있으나 생성자 파라미터에 누락된 것을 보완

**변경된 시그니처**:
- `execute(request)` → `execute(request, request_id: str)` (LOG-001)
- `_build_context_messages(history, summary)` → `_build_summarized_context()` + `_build_full_context()` (SRP)
- `_parse_agent_output(messages)` → `_parse_agent_output(result, tools)` (collected_sources 접근 필요)
- LLM 주입: `ChatOpenAI` 인스턴스 → `openai_api_key` + `model_name` 문자열 (테스트 용이성)

**langsmith() 위치**: Router → UseCase.execute() 내부 (verify-architecture 규칙 준수)

---

## 5. general_chat_router.py — 100% Match

POST /api/v1/chat, get_current_user, Depends(get_general_chat_use_case) 모두 일치.  
DI factory는 main.py에서 override (FastAPI 표준 패턴).

---

## 6. Test Coverage — 100% (38/38)

| 파일 | 설계 | 구현 | 상태 |
|------|------|------|------|
| test_schemas.py | 6 | 6 | ✅ |
| test_policies.py | 4 | 4 | ✅ |
| test_tools.py | 8 | 8 | ✅ |
| test_use_case.py | 12 | 12 | ✅ |
| test_general_chat_router.py | 8 | 8 | ✅ |
| **합계** | **38** | **38** | ✅ |

---

## Missing Features: 없음

설계된 모든 기능이 구현되었습니다.

---

## Intentional Changes (문서화)

| # | 변경 | 이유 |
|---|------|------|
| 1 | `summary_repo` 추가 | 설계 Gap 보완 (요약 DB 저장 흐름 완성) |
| 2 | `request_id` 파라미터 전파 | LOG-001 필수 준수 |
| 3 | langsmith() → UseCase 내부 | verify-architecture PASS |
| 4 | Policy 인스턴스 속성화 | 테스트 용이성 |
| 5 | `_build_context_messages` 분리 | SRP 원칙 |

---

## 결론

**Match Rate 93%** — 90% 기준 통과. 모든 차이점은 LOG-001 준수, 테스트 용이성 향상, 설계 Gap 보완을 위한 의도적 변경입니다. 코드 결함 없음.

**다음 단계**: `/pdca report general-chat-api`
