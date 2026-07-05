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

---

## 차트 메타 컨텍스트 규칙 (D7-rev1, chart-context-continuity 2026-06-10)

`conversation_message.charts`(표시 전용 차트 메타)의 LLM 컨텍스트 투입 규칙:

- ❌ **full config(JSON)는 LLM 컨텍스트에 투입 금지** (토큰 폭증 방지 — 기존 D7 유지)
- ✅ **캡션 1줄만 투입 허용**: charts 부속 assistant 메시지를 컨텍스트로 변환할 때
  `ChartCaptionPolicy`가 생성한 캡션(예: `[생성된 차트: bar "제목" (labels: ... | series: ...)]`,
  메시지당 ≤ 200자)을 content 뒤에 부착한다
- 캡션은 **컨텍스트 윈도우 내에서만** 유효 (전체 컨텍스트 시 전부, 요약 시 최근 3턴)
- ❌ **요약 본문에는 미포함** — summarizer 입력은 content만 사용 (기존과 동일)
- 차트 편집 후속 질문(`ChartFollowupPolicy` EDIT 판정) 시에만 저장된 charts를
  DB에서 로드해 `ChartTransformerInterface` 전용 경로로 처리한다 (일반 컨텍스트 미경유)

> 개정 이력: D7("LLM 컨텍스트 미투입") → D7-rev1("full config 미투입, 캡션은 투입").
> 근거: `docs/02-design/features/chart-context-continuity.design.md` §1/§3.
