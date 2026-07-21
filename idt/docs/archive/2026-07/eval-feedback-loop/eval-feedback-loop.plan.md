# eval-feedback-loop Plan Document

> **Feature**: eval-feedback-loop — 평가 신호 기반 자동 환류 (부정 평가 → 메모리 추출 우선순위)
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft (rev1 — 2026-07-21 이유 수집 추가: bare 👎 추측 추출 제거, comment 있는 👎만 트리거. 사용자 결정)
> **비전 근거**: growing-agent 7원칙의 측정 게이트(agent-eval-gate, PR #41)가 수집한 신호를 **성장의 입력**으로 처음 연결하는 축 — "사용자가 평가했을 때 자동으로 문맥을 이해하고 성장하는 에이전트"의 환류 1단계

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | agent-eval-gate로 👍/👎 신호는 쌓이지만 **소비처가 없다** — 부정 평가는 관리자 대시보드에 표시될 뿐, 에이전트가 그 실패에서 아무것도 배우지 않는다. 한편 메모리 추출(agent-memory-extraction)은 모든 턴을 동일 취급하여 "사용자가 명시적으로 불만족한 턴"이라는 최고 가치 신호를 활용하지 못한다 |
| **Solution** | 👎 클릭 시 **이유 수집**(선택형 칩 + 자유 코멘트, 기존 comment 필드 재사용) → **이유 있는 👎만** 해당 턴 Q/A + 이유를 부정 맥락으로 메모리 추출 자동 kickoff. 기존 MemoryExtractionService 재사용, fire-and-forget으로 평가 API 지연 0, 후보는 pending 승인 흐름 합류. 신규 bool 설정 기본 off(독립 opt-in) |
| **Function UX Effect** | 👎 클릭 시 "무엇이 아쉬웠나요?" 칩(부정확함·질문과 무관 등)+코멘트 입력이 노출 — 이유를 남기면 관리자 메모리 승인 큐에 "사용자가 말한 이유 기반 교정 후보"가 나타나 승인만 하면 다음 대화부터 반영됨. 이유 없는 👎는 지금처럼 만족도 통계만 |
| **Core Value** | 측정(eval) → 학습(memory) 파이프라인의 **첫 자동 환류 고리 완성**. "모델 고정·데이터 성장" 비전에서 성장 방향을 사용자 판단이 직접 결정하게 됨 — 이후 위키 초안·프롬프트 튜닝 환류의 선례 구조 |

---

## 1. 배경 / 문제 (실코드 확인)

- **신호 수집 완료**: `message_feedback`(V052) — `SubmitFeedbackUseCase`가 rating=down 저장 시점에 message_id·user_id·agent_id를 모두 보유 (`src/application/eval/use_cases.py:41`). 그러나 저장 후 아무 후속 동작 없음.
- **추출 인프라 존재**: `MemoryExtractionService.kickoff()`(fire-and-forget, 실패 격리, pending cap, 기본 off) — general_chat `use_case.py:402`에서만 호출. 평가 시점에는 미연결.
- **Q/A 복원 가능**: 👎 대상 메시지에서 `find_by_id` → session_id·turn_index 확보 → `find_by_session`으로 직전 user 메시지(질문) 복원 가능 (`conversation_repository.py:29,41`).
- **후보 검수 흐름 존재**: 추출 후보는 `MemoryStatus.PENDING`으로 저장되어 관리자/사용자 승인 후 active (FR-02 선례 — active 직행 금지).

## 2. 목표 / 범위

### In Scope (환류 1단계 — 이유 있는 부정 평가 트리거 추출)

1. **이유 수집 UI**: 👎 클릭 시 선택형 이유 칩 + 자유 코멘트(선택) 입력 노출 — 칩·코멘트 모두 기존 `comment` 필드(VARCHAR 500)로 전송, **마이그레이션 0**
2. **트리거**: `SubmitFeedbackUseCase` 성공 경로에서 **comment 있는 down 저장** 시에만 메모리 추출 kickoff — bare 👎는 만족도 통계만(추측 추출 금지)
3. **부정 맥락 추출**: extractor에 "사용자가 이 답변에 불만족했다" + **사용자가 말한 이유**를 전달 — 선호·교정 지향 후보 추출
4. **독립 opt-in**: 신규 `eval_feedback_extraction_enabled: bool = False` — 기존 `memory_extraction_enabled`(매 턴 추출)와 **독립** 분기, off면 기존 동작 완전 동일
5. **격리**: 평가 API 응답 지연 0(kickoff sync 반환), 추출 실패는 warning 격리 — 평가 저장에 전파 금지

### Out of Scope

- 긍정(👍) 평가 환류, 코멘트 자연어 분류(칩은 분류가 아니라 수집 UI)
- 프롬프트/에이전트 정의 자동 수정, 답변 자동 재생성
- agent(비 general-chat) 경로 평가 연동 — agent-eval-gate 이월 그대로 유지
- 위키 자동 초안 생성 환류(후속 축 후보 — 이번에 수집한 "이유" 신호를 그대로 재사용 예정)
- admin 대시보드 UI 변경

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | **comment 있는 👎** 저장 성공 시(신규 down·rating 전이·comment 변경) 해당 턴 Q/A로 메모리 추출 kickoff | bare 👎·up·취소·동일 재제출은 no-op |
| FR-02 | Q/A 복원: 대상 assistant 메시지 + 같은 세션 직전 user 메시지 | 복원 실패 시 조용히 skip(warning) |
| FR-03 | 부정 맥락(불만족 신호 + 사용자가 말한 이유)을 추출 프롬프트에 반영 | 기존 매 턴 추출 프롬프트는 무변경 |
| FR-04 | 추출 후보는 기존 PENDING 승인 흐름 합류 — active 직행 금지 유지 | dedup·validate·cap 정책 계승 |
| FR-05 | `eval_feedback_extraction_enabled` 기본 False, off면 기존 경로 바이트 단위 동일 | 독립 opt-in 선례 |
| FR-06 | 평가 API 응답 지연 0 + 추출 실패 격리(평가 저장 성공 유지) | kickoff 패턴 재사용 |
| FR-07 | 기존 eval·memory·general_chat 테스트 회귀 0 | |
| FR-08 | 👎 클릭 시 이유 칩 + 자유 코멘트 입력 노출, 제출 시 기존 comment 필드로 upsert | 기존 취소 토글(👎 재클릭) 동작 보존 |

## 4. 성공 기준

- Match ≥ 90%, 마이그레이션 0(comment 필드 재사용 — 신규 컬럼 없음)
- 👎+이유 제출 → kickoff 호출 → 부정 맥락 추출 → PENDING 저장 전 구간 단위 테스트 + 이유 수집 UI 테스트
- off 상태 무회귀: 기존 eval 30건·memory·general_chat·프론트 MessageFeedback 테스트 전부 통과

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| 평가 라우터 DI에 추출 서비스 추가로 결합 증가 | 싱글톤 `get_memory_extraction_service()` 재사용 — 신규 생성 없음 |
| Q/A 복원 시 turn 페어링 오판(멀티턴·요약) | 직전 user 메시지 1건만 사용, 모호하면 skip (FR-02) |
| 👎 반복 클릭(토글 on/off/on)으로 중복 추출 | 기존 dedup_candidates + pending cap이 방어, Design에서 추가 가드 판단 |
| pending cap에 걸려 고가치 신호 유실 | Design 결정 ③ — cap 동일 적용 vs 트리거 전용 여유 |
| 부정 답변에서 잘못된 "교훈" 추출(할루시네이션) | **comment 게이트(rev1)** — 이유 없는 👎는 추출 자체를 안 함(추측 제거) + PENDING 승인 게이트 최종 방어 |
| 이유 입력이 귀찮아 수집률 저조 | 선택형 칩(1클릭)으로 마찰 최소화, 미입력도 통계 신호로는 유효 |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | Q/A 복원 경로 | `find_by_session` 후 turn_index 페어링 vs 신규 repo 메서드(직전 user 메시지 1건 조회) |
| ② | 부정 맥락 전달 방식 | `MemoryExtractorInterface.extract`에 additive optional 파라미터 vs 별도 메서드 vs question 문자열에 맥락 접두 |
| ③ | pending cap 상호작용 | 동일 cap 적용(단순) vs 평가 트리거는 cap 검사 후에도 1건 허용 |
| ④ | 후보 provenance 표시 | 기존 `source_run_id` 재사용 vs 표시 없음 vs additive 컬럼(V053, 최후 수단) |
| ⑤ | 트리거 위치 | SubmitFeedbackUseCase 내부 vs 라우터 레이어 — 레이어 규칙(비즈니스 로직은 application) 고려 시 UseCase 유력 |

## 7. 참조

- 신호 수집: `src/application/eval/use_cases.py` (SubmitFeedbackUseCase) · [[project-agent-eval-gate-completion]]
- 추출 인프라: `src/application/memory/extraction_service.py` (kickoff·격리·cap) · [[project_agent-memory-extraction_completion]]
- 독립 opt-in 선호: [[prefer-independent-optin-over-field-extension]]
- Q/A 복원: `src/application/repositories/conversation_repository.py` (find_by_id · find_by_session)
- 비전: `docs/architecture/growing-agent-vision.md` — 환류(feedback loop) 축
