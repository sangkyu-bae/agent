---
title: 사용자 평가(👍/👎) 저장 — 취소는 상태값이 아니라 행 삭제 토글로 표현
status: draft
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md (§2 결정 ②, §6)
  - 커밋 7a558832 (idt/src/infrastructure/eval/repository.py, idt/db/migration/V052__create_message_feedback.sql)
confidence: 0.85
version: 1
created: 2026-07-20
updated: 2026-07-20
verified_at: 6cc25656
---

# 평가 취소 = 행 삭제 토글 패턴

## 문제

👍/👎 같은 사용자 평가에 "취소" 상태를 어떻게 표현할 것인가.
`rating = null` 갱신으로 표현하면 집계 쿼리마다 null 제외 조건이 필요하고,
"평가 안 함"과 "평가했다가 취소함"이라는 무의미한 상태 구분이 생긴다.

## 검증된 사실 (agent-eval-gate, 백엔드 30 테스트 통과)

- `message_feedback` 테이블(V052): `UNIQUE(message_id, user_id)` + `INDEX(agent_id, rating)`.
- 쓰기 규칙:
  - 다른 rating 클릭 또는 코멘트 동반 → **upsert** (UNIQUE 키 기준)
  - **같은 rating + 코멘트 없음 재클릭 → 행 delete** (= 취소)
  - 단, 코멘트가 있는 재클릭은 갱신 유지 (`comment is None` 가드 — Report G5)
- 집계(`EvalPolicy.satisfaction`)는 **존재하는 행만** 대상으로 하고, 평가 0건이면
  0%가 아니라 `None`을 반환한다 (미평가 ≠ 만족도 0).
- FK/COLLATE는 명시하지 않음 (MySQL FK collation 규칙 문서 참조, errno 3780 회피).

## 다음에 적용하는 법

- 좋아요/북마크/투표류의 "있다·없다" 신호는 상태 컬럼 대신 **행 존재 여부**로 모델링:
  UNIQUE 자연키 + upsert/delete 토글. 집계는 필터 없이 단순해진다.
- "0건"과 "값 0"을 구분해야 하는 집계는 None 반환을 정책(domain policy)에 명시한다.
- 부착 대상 id는 신규 id 체계를 만들지 말고 기존 엔티티 id를 재사용
  (여기서는 `ConversationMessage.id` — 결정 ①).
