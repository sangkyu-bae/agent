# fix-wiki-distill-dedup Plan Document

> **Feature**: fix-wiki-distill-dedup — 위키 distill 재실행 시 draft 중복 생성 수정
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **부채 출처**: `docs/guides/llm-wiki.md` §10 (2026-07-18 기록) · 비교 문서 §2-2 한계

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | distill을 같은 컬렉션에 재실행하면 동일 소스 그룹에서 draft가 매번 새로 생성된다(`_distill_one`이 무조건 uuid4 신규 저장) — 승인 큐가 중복으로 오염되고 LLM 비용도 중복 지출 |
| **Solution** | 소스 그룹의 `refs`를 정체성 키로 삼아, 동일 agent에 같은 refs로 만들어진 문서가 이미 있으면 **LLM 호출 전에 스킵**(멱등 재실행) — 스킵 사유·개수를 응답과 로그로 관측 |
| **Function UX Effect** | 관리자가 distill을 반복 실행해도 승인 큐가 오염되지 않고, 응답에 `skipped_count`가 표시되어 "이미 정제됨"을 즉시 알 수 있다 |
| **Core Value** | 위키 축의 자동 유입 경로가 멱등해져 "주기 실행(스케줄)" 전제가 성립 — Phase 3 대화 환류·백필의 선행 조건 해소 |

---

## 1. 배경 / 문제 (실코드 확인)

- `distill_use_case.py:64-92` — `_distill_one`이 그룹마다 `uuid.uuid4()` 신규 WikiArticle을 무조건 저장. 기존 문서 조회 없음.
- 결과: 같은 컬렉션 재실행 = 같은 `group.refs`에 대해 ① LLM 중복 호출(비용) ② draft 중복 적재(승인 큐 오염) ③ 승인된 문서와 내용 중복.
- 메모리 추출(Phase 2)은 이 실수를 반복하지 않도록 dedup을 처음부터 넣었음 — 위키만 부채로 남은 상태.

## 2. 목표 / 범위

### In Scope

1. **refs 기반 스킵**: distill 실행 시 해당 agent의 기존 문서 refs 집합을 1회 조회 → 그룹 refs가 이미 커버된 그룹은 **distiller 호출 전에 스킵** (LLM 비용도 절약)
2. **관측**: 스킵 그룹 수를 `DistillResponse`에 `skipped_count`로 노출(additive) + info 로그
3. **가이드 갱신**: `llm-wiki.md` §10의 한계 기록을 해소로 갱신

### Out of Scope

- 내용 유사도(임베딩) 기반 중복 판정 — refs 정확 일치만
- 기존 중복 draft의 소급 정리(수동/후속 배치)
- force 재생성 옵션(요청 시 후속)
- 원본 문서 변경 감지 후 재정제(refs 동일하나 내용 갱신) — Phase 3 환류에서 다룸

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | 동일 agent에 동일 refs 집합으로 생성된 문서(상태 무관 여부는 Design 결정)가 있으면 그룹 스킵 | 정체성 키 = frozenset(refs) |
| FR-02 | 스킵은 **LLM 호출 전** 판정 — 중복 비용 0 | |
| FR-03 | 응답 `skipped_count` additive — 기존 프론트 무수정 동작 | api_schemas + 프론트 타입 동기화 |
| FR-04 | 신규 그룹만 있는 실행·전부 스킵 실행 모두 정상 완료 (에러 아님) | |
| FR-05 | 기존 distill 테스트 회귀 0 | |

## 4. 성공 기준

- 동일 입력 2회 실행 시 2회차 생성 0건·스킵 N건 (멱등성 테스트)
- Match ≥ 90%, 회귀 0

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| refs 부분 겹침(그룹핑 변화) 시 스킵 누락/과잉 | 정확 일치(frozenset 동등)만 스킵 — 부분 겹침은 신규로 취급(보수적) |
| deprecated(반려) 문서와 일치 시 재생성 여부 | Design 결정 ① — 반려 의사 존중(스킵) vs 재정제 허용 |
| agent당 문서 수 증가 시 조회 비용 | find_by_agent 1회 → 메모리 set 비교 (문서 수 수백 수준 — 충분) |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 스킵 대상 상태 범위 | 전 상태(draft/approved/deprecated) vs deprecated 제외 |
| ② | refs 비교 위치 | UseCase에서 find_by_agent 후 set 비교(무스키마) vs repo 전용 조회 메서드 |
| ③ | 정체성 키 정규화 | refs 정렬·strip 여부 (저장 형식 실측 후 확정) |

## 7. 참조

- 대상 코드: `src/application/wiki/distill_use_case.py` (`_distill_one`), `api_schemas.py`(DistillResponse), `wiki_router.py`
- 동형 해결 선례: 메모리 Phase 2 `dedup_candidates` + "LLM 호출 전 스킵" (extraction_service)
- 테스트: `tests/application/wiki/test_distill_use_case.py` 확장
