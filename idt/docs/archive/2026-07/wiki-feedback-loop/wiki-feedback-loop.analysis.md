# wiki-feedback-loop Gap Analysis (Check)

> **Design 기준**: `docs/02-design/features/wiki-feedback-loop.design.md`
> **Plan 기준**: `docs/01-plan/features/wiki-feedback-loop.plan.md` (FR-01~07)
> **분석 도구**: bkit gap-detector (2026-07-21) · 브랜치 `feature/wiki-feedback-loop` (eval-feedback-loop 스택)
> **Match Rate**: **99% → 권고 1건 Check 내 해소 후 잔여 gap 0**

---

## 1. 결과 요약

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design 결정 ①~⑥ | 6/6 | ✅ |
| Design §3-1~3-6 상세 | 6/6 | ✅ |
| 테스트 T1~T4 | 4/4 | ✅ (T1은 설계 5케이스 대비 9케이스 초과 구현) |
| Plan FR-01~07 | 7/7 | ✅ |
| **Overall** | **99%** | 불일치 gap 0 |

- 회귀: wiki+eval+memory **230 pass** (`-p no:randomly`) + Check 보완 후 신규 스위트 39 pass
- 백엔드 전용·마이그레이션 0·프론트 diff 0 설계 목표 코드로 확인

## 2. 핵심 안전장치 5종 — 전부 코드·테스트 확인

| 검증 | 근거 |
|------|------|
| 자동 승인 불가 | `feedback_service.py` `status=WikiStatus.DRAFT` 리터럴, 상태 전이 코드 없음 |
| dedup이 **LLM 호출 전** | `_distill_and_save` step1 dedup→return 이후에만 step2 distill |
| 쓰기 세션 `begin()` | `async with session.begin():` 명시 트랜잭션 |
| off 경로 Q/A 복원 0회 | `if not (memory_on or wiki_on): return` — `_find_question` 이전 + 전용 테스트 |
| eval-feedback-loop 보존 | memory kickoff 인자·순서 불변, 기존 17건 무수정 통과 |

## 3. Gap 처분

| # | 심각도 | 내용 | 처분 |
|---|:------:|------|------|
| 1 | Minor(권고) | `float(raw_confidence)`가 json try/except 밖 — LLM이 `"confidence":"high"` 반환 시 ValueError(광역 격리로 무해하나 초안 유실) | **해소** — `_parse_confidence` 분리, 비수치는 기본 0.5로 강등(초안 유지) + 테스트 추가 (Check 내) |

설계 외 추가: `drain()` 헬퍼(테스트·종료 훅 전용) — MemoryExtractionService 동형 패턴 정합, 무해.

## 4. 의도적 스코프 외 (이월 유지)

- 반복 이유 빈도 집계 승격 · websearch 환류 · agent 경로 평가 연동 · E2E 수동 검증(양 플래그 on + MySQL/Qdrant 기동 시)

## 5. 결론

Match 99% ≥ 90%, 권고 1건 즉시 해소 — **iterate 불필요, report 진행 가능.**

⚠️ 브랜치 주의: 본 기능은 PR #42(eval-feedback-loop) 위 스택 — PR은 #42 머지 후 master 베이스, 또는 그 전엔 `feature/eval-feedback-loop` 베이스로 생성해야 한다.
