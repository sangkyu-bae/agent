# recurring-feedback-promotion Plan Document

> **Feature**: recurring-feedback-promotion — 반복되는 👎 이유의 빈도 집계로 위키 초안 승격 우선순위화
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft
> **비전 근거**: 환류 3부작(#41 측정 → #42 개인 학습 → #44 팀 지식) 위에서 **신호의 세기**를 반영하는 축 — "한 명이 한 번 말한 것"과 "여러 턴에서 반복 확인된 것"을 승인 큐에서 구분

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | wiki-feedback-loop는 메시지당 1 draft를 만들지만 **같은 주제의 불만이 다른 메시지에서 반복되면 별개 draft가 남발**된다 — 신호가 분산되어 반복성(강한 신호)이 승인 큐에서 보이지 않고, 관리자는 같은 내용을 여러 번 검토한다 |
| **Solution** | 피드백 위키 환류 시 기존 CONVERSATION draft 제목 목록을 LLM 판정에 함께 전달 — **같은 주제면 신규 draft 대신 기존 draft 강화**: `source_refs`에 `feedback:{message_id}` 추가(지지 수 = refs 개수), 지지 수 기반 confidence 가중(정책 함수·클램프), version +1. 판정 실패 시 기존 동작(신규 draft) 폴백 |
| **Function UX Effect** | 관리자 승인 큐(WikiPage)에서 반복 확인된 초안이 **높은 신뢰도(confidence)·버전·다수 출처(refs)**로 표시되어 우선 검토 대상이 됨 — 신규 화면 없음, 기존 노출 필드(신뢰도·버전·출처)가 그대로 우선순위 신호가 됨 |
| **Core Value** | 환류에 **빈도 차원** 추가 — 반복 지지된 지식이 스스로 승인 큐 상위로 떠오르는 구조. draft 남발 억제 + 관리자 검토 비용 절감 |

---

## 1. 배경 / 문제 (실코드 확인)

- `FeedbackWikiService._distill_and_save`: dedup이 **정확 refs 일치**(`feedback:{message_id}`)만 차단 — 같은 주제라도 다른 메시지면 매번 신규 draft (feedback_service.py).
- dedup을 위해 `find_by_agent(agent_id)` 전체 조회를 **이미 수행 중** — 기존 draft 제목 목록을 추가 조회 없이 확보 가능.
- `WikiArticle.apply_edit`는 version +1 선례, `WikiPolicy.clamp_confidence` 존재, repo `update()` 존재 (load-then-mutate).
- 승인 큐 노출: `WikiArticleTable`(confidence 컬럼)·`WikiDetailPanel`(신뢰도·버전·출처유형) — **우선순위 신호가 이미 화면에 있음** → 프론트 diff 0 가능.
- `source_refs`는 list[str] — 지지 수를 별도 컬럼 없이 `len(refs)`로 표현 가능 → **마이그레이션 0**.

## 2. 목표 / 범위

### In Scope (백엔드 전용 — wiki 환류 경로 개선)

1. **주제 매칭**: `distill_feedback` LLM 호출에 기존 CONVERSATION **draft** 제목 목록(id+title) 전달 — worthy 판정 시 "기존 초안과 같은 주제면 match_id 반환" (기존 [기존 메모리 — 중복 금지] 프롬프트 패턴 동형)
2. **강화(reinforce)**: match 시 신규 draft 생성 대신 대상 draft 갱신 — `source_refs += feedback:{message_id}`, confidence = 지지 수 기반 정책 함수(단조 증가·상한 클램프), version +1, updated_at 갱신
3. **안전 폴백**: match_id가 실재하지 않거나 DRAFT 상태가 아니면 기존 동작(신규 draft) — 판정 오류가 데이터를 오염시키지 않음
4. **관측**: 강화 시 info 로그(article_id·지지 수) — 기존 `trigger="feedback"` 로그 확장

### Out of Scope

- APPROVED/DEPRECATED 문서 강화 — 같은 주제라도 **신규 draft**(승인자가 비교 판단, 승인 문서 자동 변경 금지)
- draft 본문(content) LLM 병합·재작성 (이유만 축적 — 본문 품질은 승인자 편집 몫)
- memory 환류 쪽 반복 집계 (개인 스코프라 반복 개념 약함)
- admin 집계 API/위젯 신규 (기존 confidence·version·refs 노출 재사용)
- 신규 config 플래그 (기존 `wiki_feedback_draft_enabled` 내 동작 — §5 리스크 참조)

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | distill 판정에 같은 agent의 CONVERSATION+DRAFT 제목 후보 전달, 같은 주제면 match 식별 | 기존 find_by_agent 결과 재사용 — 추가 조회 0 |
| FR-02 | match 시 강화: refs 추가·confidence 지지 수 정책 재계산·version+1·updated_at | 신규 draft 생성 안 함 |
| FR-03 | confidence 정책: 지지 수 단조 증가, 상한 클램프(승인 전 1.0 도달 금지) | 도메인 정책 함수(WikiPolicy) |
| FR-04 | match 대상이 미실재·비DRAFT면 신규 draft 폴백 (오염 방지) | warning 관측 |
| FR-05 | 후보 없음·match 없음이면 기존 동작 바이트 동일 (신규 draft) | 회귀 기준선 |
| FR-06 | 동일 메시지 재트리거는 기존 refs dedup이 선차단 (지지 수 인플레 방지) | 기존 FR-04 계승 — 지지 수 = 고유 메시지 수 |
| FR-07 | 기존 wiki·eval·memory 테스트 회귀 0 | |

## 4. 성공 기준

- Match ≥ 90%, 마이그레이션 0(지지 수 = len(source_refs)), 프론트 diff 0
- 같은 주제 2번째 피드백 → 기존 draft 강화(refs 2개·confidence 상승·v2) 전 구간 단위 테스트
- 다른 주제 → 신규 draft(기존 동작) 회귀 테스트

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| **기존 동작 변경**(같은 주제 신규 draft → 강화) — "갈아끼우기" 우려 | draft 남발은 결함성 동작(신호 분산)으로 판단. 단 신규 플래그 없이 가는 근거를 Design에서 재검토 — 필요 시 독립 opt-in으로 전환 (Design 결정 ①) |
| LLM 오매칭(다른 주제를 같다고 판정) → 잘못된 강화 | 강화는 refs·confidence·version만(본문 불변) + DRAFT 한정 + 승인 게이트 최종 방어. 프롬프트에 "확실할 때만 match" 지시 |
| 후보 목록이 커지면 프롬프트 비대 | 후보 상한(최근 N개) — Design 결정 |
| confidence 인플레 | 정책 함수 상한 클램프(예: ≤0.95) + 같은 메시지 중복 차단(FR-06) |
| update 경쟁(동시 강화) | fire-and-forget 저빈도 + load-then-mutate 짧은 트랜잭션 — 충돌 시 한쪽 손실 허용(best-effort, 기존 환류 원칙) |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 플래그 전략 | 기존 `wiki_feedback_draft_enabled` 내 동작 개선 vs 신규 독립 opt-in — 독립 opt-in 선호 선례 vs 결함성 동작 교정 |
| ② | match 반환 계약 | `FeedbackWikiDraft`에 optional `match_id` 추가 vs 별도 반환 타입 — additive 원칙 |
| ③ | confidence 정책 공식 | base + per-지지 증분(클램프) vs 로그 스케일 — WikiPolicy 함수로 어느 쪽이든 교체 용이하게 |
| ④ | 후보 상한·정렬 | 최근 N개(updated_at desc) vs 전체 — 프롬프트 예산 |
| ⑤ | 강화 시 title 갱신 여부 | 유지(안정 키) vs LLM 제안 반영 — 유지 유력(매칭 키 안정성) |

## 7. 참조

- 강화 지점: `src/application/wiki/feedback_service.py` (`_distill_and_save` — find_by_agent 기수행) · [[project-wiki-feedback-loop-completion]]
- 판정 계약: `src/infrastructure/wiki/feedback_distiller.py` (worthy JSON) · `src/application/wiki/schemas.py` (FeedbackWikiDraft)
- 정책·엔티티: `WikiPolicy.clamp_confidence` · `WikiArticle.apply_edit`(version+1 선례) · repo `update()`(load-then-mutate)
- 승인 큐 노출: `WikiArticleTable.tsx:128`(confidence) · `WikiDetailPanel.tsx:98-99`(신뢰도·버전)
- 독립 opt-in 선호: [[prefer-independent-optin-over-field-extension]]
