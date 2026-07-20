# fix-wiki-distill-dedup Gap Analysis (Check)

> **Design**: `docs/02-design/features/fix-wiki-distill-dedup.design.md`
> **Analyzer**: gap-detector (bkit)
> **Date**: 2026-07-20
> **Match Rate**: **100%** (Gap 0건 · Act 0회)

---

## 1. 결과 요약

| Category | Score |
|----------|:-----:|
| Design Match (결정 3건 + FR 5건) | 100% |
| Test Plan Coverage | 100% (+초과 1건: refs 순서 멱등 케이스) |
| execute 호출부 단일성 | grep 실증 — `wiki_router.py:74` 1곳뿐 (튜플 전환 안전) |

## 2. 매칭 확인 (전건 일치)

- 결정 ① 전 상태 스킵: `find_by_agent(agent_id, request_id)` status 생략 조회
- 결정 ② DISTILLED만 비교 (human 제외): `distill_use_case.py:58-62`
- 결정 ③ `frozenset(strip)` 키 — 순서·공백 무관, 부분 겹침 신규: `policies.py`
- FR-02 LLM 호출 전 스킵: continue가 `_distill_one` 앞 — call_count 테스트로 고정
- 실행 내 중복 방어: 생성분 키 추가
- FR-03 `skipped_count: int = 0` additive — 기존 프론트 무수정 동작
- 가이드 §10: 중복 검사 해소 + 남는 한계 명시, human 작성 API 낡은 항목도 정정

## 3. Gap 목록

**없음** — 누락·초과·계약 불일치 0건.

## 4. 정당한 편차

| 항목 | 판정 |
|------|------|
| 프론트 문구 "N건은 이미 정제되어 건너뜀" (설계는 "최소 반영"으로 자유 부여) | UX 개선 — 정당 |
| `WikiDetailPanel.test.tsx` path: null 드라이브바이 수정 | 범위 외 기존 tsc 에러 편승 정리 — 정당 |

## 5. 테스트 결과

- 백엔드: 위키 정책 40(신규 5) + distill 14(신규 dedup 7) + 라우터 26 — 전부 통과
- 프론트: wiki 12 + WikiDetailPanel 3 통과, tsc wiki 에러 0
- 기존 테스트 2건이 신규 dedup에 걸려 실패 → 고유 refs로 수정 (동작 방증)

## 6. 이월

- E2E 실측(같은 컬렉션 distill 2회 → 2회차 skipped 확인) — KB 공통 체크리스트

## 7. 총평

설계 결정 3건·FR·Test Plan 전건 일치, 호출부 단일성 실증 — 100%로 `/pdca report` 진행 가능. 소형 수정의 표준 사이클(당일 Plan→Check).
