# fix-wiki-distill-dedup Completion Report

> **Feature**: fix-wiki-distill-dedup — 위키 distill 재실행 중복 생성 수정
> **Author**: 배상규
> **Cycle**: Plan → Design → Do → Check → Report (2026-07-20 당일 완결)
> **Match Rate**: **100%** (Gap 0건 · Act 0회)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | fix-wiki-distill-dedup (llm-wiki.md §10 기록 부채 해소) |
| 기간 | 2026-07-20 당일 사이클 |
| 산출물 | 백엔드 4파일 수정 + 프론트 4파일 수정 · 마이그레이션 0 · 신규 API 0 |
| Match Rate | 100% — Gap 0건, 정당한 편차 2건뿐 |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 테스트 | 백엔드 80건(정책 40 + distill 14 + 라우터 26) + 프론트 15건 — 전부 통과 |
| 신규 테스트 | 정책 5 + dedup 7 + 라우터 단언 1 |
| 기존 회귀 | 0 (기존 실패 2건은 신규 dedup이 정확히 작동한 방증 — 고유 refs로 정정) |
| Act 반복 | 0회 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | distill 재실행 시 동일 소스 그룹에서 draft가 매번 재생성 — 승인 큐 오염 + LLM 비용 중복 (2026-07-18 §10 기록 부채) |
| **Solution** | `source_refs` frozenset(strip) 정체성 키로 **LLM 호출 전 스킵** — 재실행 멱등, 실행 내 중복까지 방어, `skipped_count`로 관측 |
| **Function UX Effect** | 관리자가 distill을 안심하고 반복 실행 — 응답 문구 "N건은 이미 정제되어 건너뜀"으로 상태 즉시 파악 |
| **Core Value** | 위키 자동 유입 경로가 멱등해져 **주기 실행(스케줄) 전제 성립** — Phase 3 환류·백필의 선행 조건 해소. 메모리 축과 위키 축의 dedup 패턴 정렬 완성 |

---

## 2. 구현 결과

- **도메인**: `WikiPolicy.refs_key`(순서·공백 무관) + `is_duplicate_group`(정확 일치만 — 부분 겹침은 보수적으로 신규)
- **유스케이스**: 기존 DISTILLED 문서 키 집합 1회 구축(전 상태 — deprecated 재생성 루프 차단, human 제외 — 교차 오염 방지) → 스킵 → `(created, skipped)` 튜플 (호출부 단일성 grep 실증)
- **계약**: `DistillResponse.skipped_count = 0` additive — 프론트 무수정 동작 + 타입·문구·MSW 동기화
- **문서**: llm-wiki.md §10 한계 2건 갱신(중복 검사 해소 + human 작성 API 낡은 항목 정정)

## 3. Lessons Learned

1. **기존 테스트 실패가 신규 동작의 방증이 되는 경우** — `_group()` 기본 refs가 동일해 실행 내 dedup에 걸림. "왜 실패했나"를 신규 동작 관점에서 읽으면 테스트 의도(복수 그룹)와 기본값 설계의 결합이 드러난다.
2. **부채는 기록 당시보다 해소 시점이 싸다** — §10에 원인 파일까지 기록해 둔 덕에 Plan에서 원인 특정 0분, 당일 사이클 완결.
3. **양 축 패턴 정렬** — 메모리(추출 전 dedup)와 위키(정제 전 dedup)가 같은 "LLM 호출 전 스킵" 원칙으로 수렴 — 이후 자동 유입 경로 추가 시의 기본형.

## 4. 이월 항목

| 항목 | 비고 |
|------|------|
| E2E 실측 | 같은 컬렉션 distill 2회 → 2회차 skipped_count 확인 — KB 공통 체크리스트 |
| 기존 중복 draft 소급 정리 | 수동/후속 (범위 외 명시) |
| force 재생성 옵션 | 요청 시 후속 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 당일 사이클 완결 — Match 100%, Gap 0 | 배상규 |
