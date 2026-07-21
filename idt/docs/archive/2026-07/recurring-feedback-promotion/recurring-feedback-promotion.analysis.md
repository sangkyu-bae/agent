# recurring-feedback-promotion Gap Analysis (Check)

> **Design 기준**: `docs/02-design/features/recurring-feedback-promotion.design.md`
> **Plan 기준**: `docs/01-plan/features/recurring-feedback-promotion.plan.md` (FR-01~07)
> **분석 도구**: bkit gap-detector (2026-07-21)
> **Match Rate**: **97.6% → gap 1건(경미) Check 내 해소 후 잔여 gap 0 (≈99%)**

---

## 1. 결과 요약

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design 결정 ①~⑤ | 5/5 | ✅ |
| Design §3-1~3-5 상세 | 5/5 (§3-4 로그 필드 부분 → 해소) | ✅ |
| 테스트 T1~T3 | 전부 일치 (+방어 테스트 1건 초과) | ✅ |
| Plan FR-01~07 | 7/7 | ✅ |
| **Overall** | **97.6% → 해소 후 잔여 0** | Critical/Major 0 |

- 회귀: wiki+eval+memory **301 pass** (`-p no:randomly`)
- 설계 목표 코드 확인: 마이그레이션 0 · 신규 파일 0 · 프론트 diff 0 · DI 1줄

## 2. 집중 검증 4종 — 전부 코드·테스트 확인

| 검증 | 근거 |
|------|------|
| off 경로 기준선 보존 | `_match_candidates`가 off면 즉시 None → distiller 프롬프트 블록 미추가 + match_id None — 기존 테스트 무수정 통과로 고정 |
| 환각 match_id 2중 방어 | 1차 distiller(후보 id 집합 검증) + 2차 service(실재·DRAFT 재검증 → warning+신규 폴백) |
| refs dedup이 강화보다 선행 | `_distill_and_save` step1 dedup → LLM·강화 이전 차단 (지지 수 인플레 방지, FR-06) |
| 제목·본문 불변 + begin() | `add_support` title/content 미변경 · `_reinforce`의 `session.begin()` + repo.update(flush만) — `_apply_fields`가 refs/confidence/version/updated_at 전부 반영 확인 |

## 3. Gap 처분

| # | 심각도 | 내용 | 처분 |
|---|:------:|------|------|
| 1 | 경미 | §3-4 강화 info 로그에 `reinforced=True` 필드 누락(메시지 문자열로만 구분) | **해소** — 필드 추가 (Check 내, 재실행 14 pass) |

설계 외 추가: `test_candidates_없이_match_id_응답은_None` 방어 테스트 1건 — `not candidates` 가드 커버리지 보강, 긍정 평가.

## 4. 의도적 스코프 외 (이월 유지)

- APPROVED 문서 강화(신규 draft로 처리 — 승인 문서 자동 변경 금지 유지) · memory 쪽 반복 집계 · admin 집계 위젯 · E2E(3플래그 on + 인프라 기동)

## 5. 결론

97.6% ≥ 90%, 유일 gap 즉시 해소 — **iterate 불필요, report 진행 가능.**
