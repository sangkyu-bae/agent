# wiki-feedback-loop Plan Document

> **Feature**: wiki-feedback-loop — 이유 있는 👎를 팀 지식(제품 위키) draft로 승격하는 환류 2단계
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft
> **비전 근거**: eval-feedback-loop(PR #42)가 개인 학습(memory)으로 연결한 "이유" 신호를 **팀 지식(wiki)**으로 확장 — `WikiSourceType.CONVERSATION`("대화 환류 Phase 3", LLM-WIKI-001)의 **예약석을 최초로 채우는** 사이클

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 사용자가 👎와 함께 남긴 이유(용어 교정·사실 오류·정책 위반 지적)는 한 사용자의 memory로만 환류되고 끝난다 — 같은 오류를 다른 사용자가 또 겪어도 팀 차원 지식으로 축적되지 않는다. 한편 위키에는 `CONVERSATION` 출처 유형이 설계 때부터 예약돼 있으나(entity.py:16) 사용처가 0곳이다 |
| **Solution** | comment 있는 👎 저장 시(eval-feedback-loop와 동일 트리거) 백그라운드에서 LLM이 "팀 일반화 가치"를 판정 — 가치 있으면 `WikiArticle(draft, source_type=conversation, source_refs=[feedback:{message_id}])` 생성, 없으면 0건. 기존 draft→승인 흐름·출처 불변식·refs_key dedup 전부 재사용. `wiki_feedback_draft_enabled` 기본 off 독립 opt-in |
| **Function UX Effect** | 사용자 UI 변화 없음 — 관리자 위키 승인 큐(기존 wiki-user-facing 화면)에 "대화 환류" 출처의 초안이 나타나고, 승인하면 approved로 전환되어 wiki-first 검색에 노출 → 다음부터 모든 사용자의 답변 품질에 반영 |
| **Core Value** | 환류의 스코프 확장: 개인(memory) → **팀(wiki)**. 한 사용자의 교정이 조직 전체의 지식이 되는 Self-Improving RAG 고리 완성 — LLM-WIKI-001 Phase 3(대화 환류)의 첫 구현 |

---

## 1. 배경 / 문제 (실코드 확인)

- **신호 존재**: eval-feedback-loop가 comment 있는 👎에서 Q/A+이유를 이미 복원(`SubmitFeedbackUseCase._find_question`) — memory 추출로만 소비 중.
- **예약석 존재**: `WikiSourceType.CONVERSATION`(entity.py:16) 정의만 있고 사용 0곳(grep 확인 — DISTILLED·HUMAN만 사용). 라이프사이클(draft→approved→deprecated), 출처 불변식(`source_refs` 최소 1), `refs_key` dedup(distill 멱등 선례), 승인 UI(wiki-user-facing)까지 **전부 기성품**.
- **정제 인프라 존재**: `DistillToWikiUseCase` + `WikiDistillerInterface`(LLM 주입, from_openai 팩토리) — 입력 계약만 다름(청크 그룹 vs Q/A+이유).
- **주의**: 현재 평가는 general-chat 경로만 동작(agent 경로 이월) → 트리거되는 메시지의 `agent_id`는 super sentinel — 위키 귀속 결정 필요(Design).

## 2. 목표 / 범위

### In Scope (환류 2단계 — 백엔드 전용)

1. **트리거**: comment 있는 👎 저장 성공 시(eval-feedback-loop 트리거 조건 동일) 위키 초안 생성 kickoff — `wiki_feedback_draft_enabled: bool = False` **독립 opt-in**(memory 환류 플래그와 별개, 각각 켜고 끌 수 있음)
2. **승격 판정 + 초안 생성**: LLM이 Q/A+이유에서 "팀 일반화 가치 있는 지식"(용어 정의·사실 교정·정책/규정 지식)만 추출 — 개인 선호·일회성 불만은 0건 반환(빈 결과 허용, 강제 생성 금지)
3. **draft 저장**: `source_type=CONVERSATION`(최초 사용), `source_refs=["feedback:{message_id}"]`, `status=DRAFT`(자동 승인 절대 금지), WikiPolicy 불변식 통과분만
4. **멱등 dedup**: 동일 message_id refs가 이미 존재하면 **LLM 호출 전 스킵** (distill `refs_key` 선례)
5. **격리**: 평가 API 지연 0(fire-and-forget), 실패 warning 격리

### Out of Scope

- 자동 승인·confidence 기반 자동 노출 (승인은 사람만 — 위키 불변식 유지)
- 반복 이유 빈도 집계 기반 승격(여러 👎 묶어 판단) — 후속 후보
- 프론트 신규 화면 (기존 위키 승인 UI 재사용 — conversation 출처 배지 표기는 Design에서 기존 렌더 확인, 라벨 누락 시에만 소폭)
- memory 환류(eval-feedback-loop) 경로 수정, agent(비 general-chat) 경로 평가 연동
- websearch 환류(WikiSourceType.WEBSEARCH — 별도 예약석)

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | comment 있는 👎 저장 성공 시 위키 초안 생성 kickoff | eval-feedback-loop 트리거 조건 재사용, 독립 플래그 |
| FR-02 | LLM 승격 판정 — 팀 일반화 가치 없으면 저장 0건 | 개인 선호·일회성 불만 배제, 빈 결과 허용 |
| FR-03 | draft 저장: conversation 출처·`feedback:{message_id}` refs·DRAFT 고정 | WikiPolicy.validate_for_creation 통과분만 |
| FR-04 | 동일 message refs 기존 존재 시 LLM 호출 전 스킵 (멱등) | refs_key dedup 선례 |
| FR-05 | `wiki_feedback_draft_enabled` 기본 False — off면 기존 경로 동일 | memory 환류와 독립 opt-in |
| FR-06 | 평가 API 지연 0 + 실패 격리 (평가 저장·memory 환류에 무영향) | fire-and-forget |
| FR-07 | 기존 wiki(distill·승인·검색)·eval·memory 테스트 회귀 0 | |

## 4. 성공 기준

- Match ≥ 90%, 마이그레이션 0(wiki 테이블 source_type 문자열 — enum 값 기존 정의)
- 👎+이유 → 판정 → draft 저장 → (수동)승인 → 검색 노출 대상화 전 구간 단위 테스트
- off 상태 무회귀: wiki·eval·memory 스위트 전부 통과

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| 초안 남발(위키 오염) | LLM 판정 게이트(가치 없으면 0건) + 메시지당 1회 dedup + draft는 검색 비노출 + 사람 승인 필수 |
| general-chat 답변의 위키 귀속 모호(super sentinel) | Design 결정 ① — sentinel 저장 vs 스킵 vs 전용 스코프, 위키 조회 화면 실측 후 확정 |
| 잘못된 "교정" 승격(사용자 이유가 틀린 경우) | draft 승인 게이트가 최종 방어 + 출처 배지로 근거(feedback) 추적 가능 |
| 트리거 지점 비대화(UseCase가 memory+wiki 2종 kickoff) | Design 결정 ③ — 의존성 추가 vs 팬아웃 단일화, 40줄/중첩 규칙 준수 |
| LLM 비용 | 이유 있는 👎는 저빈도 + dedup + 판정 1회 호출 상한 |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 위키 귀속 agent_id | super sentinel 그대로 저장(공통 지식 취급) vs general-chat은 스킵 vs 전용 값 — 위키 트리/에이전트 지식 화면의 sentinel 처리 실측 후 |
| ② | 정제 계약 | 신규 `FeedbackWikiDistillerInterface` vs 기존 `WikiDistillerInterface` 재사용(입력 계약 상이) — WikiSourceGroup 어댑팅 가능성 |
| ③ | 트리거 배선 | SubmitFeedbackUseCase에 두 번째 optional 의존성 vs memory+wiki 팬아웃 서비스 단일화 |
| ④ | path 분류 | None(미분류) vs 고정 세그먼트("피드백") — 승인 큐 가시성 |
| ⑤ | confidence 초기값 | 고정(0.5) vs LLM 판정 점수 매핑(clamp_confidence) |
| ⑥ | 프론트 배지 | conversation 출처 라벨이 기존 렌더에 있는지 실측 — 없으면 라벨 1건 추가 |

## 7. 참조

- 트리거·Q/A 복원: `src/application/eval/use_cases.py` (eval-feedback-loop §3-4) · [[project-eval-feedback-loop-completion]]
- 위키 기성품: `src/domain/wiki/entity.py`(CONVERSATION 예약석) · `policies.py`(불변식·refs_key·전이) · `application/wiki/distill_use_case.py`(dedup 멱등 선례) · `review_use_case.py`(승인)
- 승인 UI: wiki-user-facing (근거 배지·path 트리 V051) · [[project_wiki-user-facing_completion]]
- 독립 opt-in: [[prefer-independent-optin-over-field-extension]]
