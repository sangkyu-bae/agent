# Multi-Turn Conversation Memory Rules

> 원본: CLAUDE.md §7

---

## 기본 원칙

- 모든 대화는 **user_id + session_id** 기준으로 관리한다
- 대화 기록은 **MySQL(RDB)** 에 저장한다
- Vector DB에 대화 원문 저장 ❌ (문서용과 분리)

---

## Conversation Table (개념 설계)

### conversation_message

| 컬럼 | 설명 |
|------|------|
| id (pk) | |
| user_id | |
| session_id | |
| role | user \| assistant |
| content | |
| created_at | |
| turn_index | |

### conversation_summary

| 컬럼 | 설명 |
|------|------|
| user_id | |
| session_id | |
| summary_content | |
| summarized_until_turn | |
| updated_at | |

---

## 요약 트리거 규칙 (강제)

- 한 세션에서 **대화 턴이 6개를 초과하면** → 반드시 **요약을 수행한다**

요약 방식:
1. turn_index 1 ~ N-3 까지 요약
2. 요약 결과를 `conversation_summary`에 저장
3. 기존 메시지는 유지하되, 다음 질의 시 **요약본 + 최근 3턴만 컨텍스트로 사용**

❌ 전체 대화를 그대로 LLM에 전달 금지  
❌ 요약 없이 무한 누적 금지

---

## 요약 정책

- 요약은 사실 중심
- 결정사항 / 사용자 의도 / 중요한 제약 포함
- 질문/답변 스타일 요약 금지

요약은 다음 질문의 **system/context**로만 사용한다.
