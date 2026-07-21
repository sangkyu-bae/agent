# eval-feedback-loop Gap Analysis (Check)

> **Design 기준**: `docs/02-design/features/eval-feedback-loop.design.md` (rev1)
> **Plan 기준**: `docs/01-plan/features/eval-feedback-loop.plan.md` (rev1, FR-01~08)
> **분석 도구**: bkit gap-detector (2026-07-21)
> **Match Rate**: **100%** (25/25 일치 — §3-3 `run()` 스레딩 표현을 부분 일치로 엄격 계산 시 98%)

---

## 1. 결과 요약

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design 결정 ①~⑥ | 6/6 | ✅ |
| Design §3-1~3-6 상세 | 6/6 | ✅ |
| 테스트 설계 T1~T5 | 5/5 | ✅ |
| Plan FR-01~08 | 8/8 | ✅ |
| **Overall** | **100%** | Critical/Major gap 0 |

- 회귀: 백엔드 196 pass (eval·memory·general_chat, `-p no:randomly`) · 프론트 51 pass (AdminDashboard+chat 10파일)
- rev1 핵심 결정(bare 👎 추측 추출 금지 · comment 있는 down만 트리거 · 절단 후 이유 블록 부착 · PENDING 합류 · 독립 opt-in) 전부 코드·테스트 반영 확인

## 2. 검증 근거 (대표)

| 항목 | 근거 |
|------|------|
| 트리거 가드 (결정 ⑤, FR-01) | `use_cases.py` `_should_trigger_extraction` — bare down·동일 재제출·up 배제 |
| Q/A 복원 (결정 ①, FR-02) | `_find_question` turn_index-1 + role=USER, 실패 시 warning + 평가 저장 유지 |
| 계약 확장 (결정 ②, FR-03) | `interfaces.py` additive `feedback_note` · `extractor.py` 절단 후 블록 부착 + "추측 금지" |
| cap 동일 (결정 ③) | `kickoff_feedback` → 기존 `_extract_and_store` cap 검사 경유, T2 skip 테스트 |
| provenance (결정 ④) | `source_run_id=None` + info 로그(message_id·trigger="feedback") |
| 이유 UI (결정 ⑥, FR-08) | `MessageFeedback.tsx` 칩 4종+코멘트 패널, 취소 토글 보존, a11y group |
| DI (§3-5) | `main.py` feedback_enabled 배선 + `_eval_submit_f` extraction 주입 |

## 3. Gap 처분

| # | 심각도 | 내용 | 처분 |
|---|:------:|------|------|
| 1 | Minor | §3-3 "run() 스레딩" 문구 — 피드백 경로는 `_spawn`→`_run_guarded` 직행이라 `run()` 확장은 dead-path (기능 영향 0) | **해소** — Design 문구 정정 완료 (Check 중) |
| 2 | Minor | §3-6 "훅 무변경" 서술 vs 실제 `useMessageFeedback.ts` 결함 수정 | **해소** — Design에 "훅 1건 결함 수정 포함" 명시 완료 |

## 4. 설계 외 개선 (위반 아님)

- `useSubmitFeedback` 전역 싱글톤 queryClient → `useQueryClient()` 전환: Provider 클라이언트 불일치 시 캐시 갱신 유실 결함(agent-eval-gate 유래) 수정. gap-detector 평가 "타당·권장", 공개 API 무변경, T5로 커버.

## 5. 의도적 스코프 외 (이월 유지)

- 긍정(👍) 환류 · 코멘트 자연어 분류 · wiki 자동 초안 환류(다음 축, 이번 이유 신호 재사용 예정)
- agent(비 general-chat) 경로 평가 연동 (agent-eval-gate부터 이월)
- E2E 수동 검증 (Qdrant/ES/MySQL 기동 시 일괄 — 기존 이월 체크리스트 합류)

## 6. 결론

Match 100% ≥ 90% — **iterate 불필요, report 진행 가능.**
