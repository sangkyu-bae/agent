# eval-feedback-loop Completion Report

> **Feature**: eval-feedback-loop — 평가 신호 기반 자동 환류 (이유 있는 👎 → 부정 맥락 메모리 추출)
> **Author**: 배상규
> **기간**: 2026-07-21 (1일, Plan→Report 단일 세션)
> **Match Rate**: **100%** (gap-detector 25/25, Critical/Major 0)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | eval-feedback-loop |
| 기간 | 2026-07-21 (Plan→Design rev1→Do→Check→Report) |
| Match Rate | 100% (iterate 0회) |
| 변경 규모 | 12파일 +549/−29 (백엔드 6 + 프론트 3 + 테스트 3 확장) |
| 마이그레이션 | **0** (comment VARCHAR(500)·기존 memory 테이블 재사용) |
| 테스트 | 신규 20케이스 (T1 10·T2 5·T3 3·T5 6 중 신규분) / 회귀 백엔드 196 pass + 프론트 51 pass |

### 1.3 Value Delivered (4관점)

| 관점 | 실제 결과 |
|------|-----------|
| **Problem** | 👍/👎 신호가 대시보드 표시로 끝나고 소비처가 없었음. 초기 설계는 bare 👎로 LLM이 불만 원인을 추측하는 구조였으나, 사용자 리뷰("어떤 점에서 싫은지 알아야 등록 판단이 가능")로 신호 품질 문제를 Do 전에 교정 |
| **Solution** | 👎 클릭 시 이유 칩 4종+자유 코멘트 수집(기존 comment 필드 재사용) → **이유 있는 👎만** 해당 턴 Q/A+이유를 부정 맥락으로 추출 kickoff → PENDING 승인 합류. `eval_feedback_extraction_enabled` 기본 off 독립 opt-in |
| **Function UX Effect** | 👎 후 1클릭으로 이유 제출 — 관리자 승인 큐에 "사용자가 말한 이유 기반 교정 후보"(preference·domain_term 우선, 추측 금지 프롬프트) 출현, 승인 시 다음 대화 반영 |
| **Core Value** | 측정(eval)→학습(memory) **첫 자동 환류 고리** — 성장 방향을 사용자 판단이 직접 결정. 수집된 "이유" 신호는 wiki 환류(후속 축)가 그대로 재사용 |

---

## 2. 산출물

| 단계 | 문서/코드 |
|------|-----------|
| Plan (rev1) | `docs/01-plan/features/eval-feedback-loop.plan.md` — FR-01~08 |
| Design (rev1) | `docs/02-design/features/eval-feedback-loop.design.md` — 결정 ①~⑥ |
| Do | 백엔드 6 + 프론트 3 파일 (아래 §3) |
| Check | `docs/03-analysis/eval-feedback-loop.analysis.md` — Match 100% |

## 3. 구현 요약

**백엔드** (마이그레이션 0 · 신규 라우트 0 · API 계약 무변경):
- `config.py`: `eval_feedback_extraction_enabled: bool = False`
- `memory/interfaces.py` + `infrastructure/memory/extractor.py`: `extract()` additive `feedback_note` — 절단 후 `[사용자 평가 신호]` 블록(이유 원문 + "추측하지 마세요")
- `memory/extraction_service.py`: `feedback_enabled` kwarg + `kickoff_feedback()` — 기존 fire-and-forget·격리·cap·PENDING 흐름 계승, `trigger="feedback"` 로그
- `eval/use_cases.py`: `_should_trigger_extraction`(comment 있는 down + 전이/이유 변경) + `_find_question`(turn_index-1·role=USER 복원, 실패 시 warning+평가 저장 유지), optional 의존성 무회귀 패턴
- `api/main.py`: DI 2곳 배선 ("off여도 주입은 항상")

**프론트**:
- `MessageFeedback.tsx`: 👎 상태에서 이유 칩(부정확함·질문과 무관·근거 부족·형식/톤 불만) + 자유 코멘트 패널, 제출 후 "이유: X"+수정, 취소 토글 보존
- `useMessageFeedback.ts`: 전역 싱글톤 queryClient → `useQueryClient()` **결함 수정** (설계 외 개선, gap-detector "타당·권장")

## 4. FR 이행

| FR | 내용 | 상태 |
|----|------|:----:|
| FR-01 | comment 있는 down만 kickoff (bare/취소/동일 재제출 제외) | ✅ |
| FR-02 | Q/A 복원 + 실패 시 skip(평가 저장 유지) | ✅ |
| FR-03 | 부정 맥락 프롬프트 반영, 매 턴 프롬프트 무변경 | ✅ |
| FR-04 | PENDING 합류·active 직행 금지·dedup/cap 계승 | ✅ |
| FR-05 | 기본 off, off 경로 무회귀 | ✅ |
| FR-06 | 평가 API 지연 0 + 실패 격리 | ✅ |
| FR-07 | 회귀 0 (백엔드 196·프론트 51 pass) | ✅ |
| FR-08 | 이유 수집 UI + comment upsert + 취소 토글 보존 | ✅ |

## 5. 학습 포인트

1. **신호 품질 게이트**: "있다/없다" 신호(👎)만으로 LLM 추론을 태우면 할루시네이션 비용을 승인 큐에 전가하게 됨 — 이유(사용자 발화)를 전제조건으로 삼아 추측 자체를 차단하는 편이 승인 게이트보다 상류 방어. 사용자 리뷰가 Do 전에 이를 교정(rev1).
2. **"필드는 있고 수집 UI만 없던" 패턴**: comment 컬럼·API·훅 파라미터가 agent-eval-gate 때 이미 존재 — 이유 수집 추가가 컴포넌트 1개 수정으로 끝남. 계약 선행 설계의 이자 수취.
3. **전역 queryClient import 결함**: TanStack Query 훅에서 전역 싱글톤 참조는 Provider 불일치 시 캐시 갱신 유실 — `useQueryClient()`가 표준. 취소-토글 테스트가 처음 노출시킴 (다른 훅에도 동일 패턴 존재 가능성, 후속 점검 후보).

## 6. 이월 항목

- **E2E 수동 검증**: 👎+이유 → 추출 → PENDING → 승인 전 구간 (Qdrant/ES/MySQL 기동 시 기존 체크리스트 합류, `eval_feedback_extraction_enabled=true` 필요)
- agent(비 general-chat) 경로 평가 연동 (agent-eval-gate부터 이월)
- wiki 자동 초안 환류 축 — 이번 "이유" 신호 재사용 (다음 사이클 후보)
- 전역 queryClient import 패턴 전수 점검 (프론트 훅 일괄)
- 배포: 신규 마이그레이션 없음. V052(message_feedback)는 agent-eval-gate 건으로 이미 이월 관리 중
