# fix-wiki-distill-dedup Design Document

> **Plan**: `docs/01-plan/features/fix-wiki-distill-dedup.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 실코드 (distill_use_case.py · wiki_repository.py `_to_model/_to_entity` · api_schemas.py · test_distill_use_case.py)

---

## 1. Plan 이월 결정 3건 — 확정

| # | 결정 대상 | 확정안 | 근거 |
|---|-----------|--------|------|
| ① | 스킵 대상 상태 범위 | **전 상태 (draft/approved/deprecated)** | deprecated(반려)를 재생성 허용하면 재실행마다 반려 의사가 무효화되는 루프 — 보수적 전 상태 스킵. 재정제가 필요하면 후속 force 옵션 |
| ② | refs 비교 위치 | **UseCase에서 `find_by_agent(agent_id, request_id)` 1회(전 상태) → 메모리 set 비교** — repo·스키마 무변경 | source_refs는 모델 JSON 컬럼에 list 왕복 저장(`wiki_repository.py:32,51,69` 실측) — DB 레벨 집합 질의 불가·불필요. **source_type=DISTILLED 문서만** 비교 대상(human 문서의 `human:{id}` refs와 교차 오염 방지) |
| ③ | 정체성 키 정규화 | **`frozenset(r.strip() for r in refs)`** — 순서·공백 무관, 부분 겹침은 신규 취급(정확 일치만 스킵) | 저장이 list 그대로라 순서 비의존 비교 필요 |

## 2. Detailed Design

### 2-1. Domain — `WikiPolicy` 확장 (순수 함수)

```python
@staticmethod
def refs_key(source_refs: list[str]) -> frozenset[str]:
    """중복 판정용 정체성 키 — strip 후 frozenset (순서·공백 무관)."""

@staticmethod
def is_duplicate_group(group_refs: list[str], existing_keys: set[frozenset[str]]) -> bool:
    """그룹 refs가 기존 키 집합과 정확 일치하면 True (FR-01)."""
```

### 2-2. Application — `DistillToWikiUseCase.execute` 수정

```python
groups = await self._source.fetch_source_groups(...)

# FR-01/02: 기존 distilled 문서의 refs 키 집합 1회 구축 — LLM 호출 전 스킵
existing = await self._repo.find_by_agent(agent_id, request_id)   # 전 상태 (결정 ①)
existing_keys = {
    WikiPolicy.refs_key(a.source_refs)
    for a in existing
    if a.source_type == WikiSourceType.DISTILLED                  # 결정 ②
}

created, skipped = [], 0
for group in groups:
    if WikiPolicy.is_duplicate_group(group.refs, existing_keys):
        skipped += 1
        continue                                                  # distiller 미호출 (FR-02)
    article = await self._distill_one(...)
    if article is not None:
        created.append(article)
        existing_keys.add(WikiPolicy.refs_key(article.source_refs))  # 동일 실행 내 중복 방어
# done 로그에 skipped_count 추가, return (created, skipped)
```

- **반환 계약 변경**: `execute` → `tuple[list[WikiArticle], int]` — 호출부는 wiki_router의 distill 엔드포인트 1곳뿐(grep 확인 전제, Do에서 재확인). 기존 테스트는 튜플 언패킹으로 수정.

### 2-3. Interfaces

- `DistillResponse.skipped_count: int = 0` — additive, 기본 0 (기존 프론트 무수정)
- `wiki_router.distill_wiki`: `created, skipped = await use_case.execute(...)` → 응답에 포함
- 프론트: `types/wiki.ts` `DistillResponse.skipped_count?: number` 동기화(표시는 WikiPage distill 결과 문구에 "· 스킵 N건" — 최소 반영)

### 2-4. 문서

- `docs/guides/llm-wiki.md` §10 한계 항목을 "해소(2026-07-20, refs 정확 일치 스킵)"로 갱신 + 남는 한계(내용 유사도 미판정·그룹핑 변화 시 신규 취급) 명시

## 3. Test Plan (TDD — Red 먼저)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/wiki/test_policies.py` 확장 | refs_key(순서 무관·공백 strip) · is_duplicate_group(일치/부분 겹침은 False/빈 집합) |
| `tests/application/wiki/test_distill_use_case.py` 확장 | **멱등성**: 동일 그룹 2회 실행 → 2회차 생성 0·skipped N·distiller 미호출(FR-02 — call_count 검증) · 신규+기존 혼합 → 신규만 생성 · human 문서 refs는 비교 제외 · 동일 실행 내 중복 그룹 1회만 · 기존 케이스 튜플 반환 수정 |
| `tests/api/test_wiki_router.py` 확장 | 응답 skipped_count 포함 |
| 프론트 (선택 최소) | 기존 wiki 테스트 회귀 — skipped_count optional이라 무수정 통과 예상 |

## 4. Implementation Order

1. WikiPolicy 확장 — 정책 테스트 먼저
2. execute 수정(스킵 루프 + 튜플 반환) — 멱등성 테스트 먼저, 기존 테스트 수정
3. DistillResponse + 라우터 + 프론트 타입/문구
4. llm-wiki.md §10 갱신 → `/pdca analyze`

## 5. Plan 리스크 해소 매핑

| Plan 리스크 | 해소 |
|-------------|------|
| 부분 겹침 오판 | 정확 일치만 스킵 (is_duplicate_group frozenset 동등) |
| deprecated 재생성 여부 | 결정 ① 전 상태 스킵 — 반려 의사 존중 |
| 조회 비용 | find_by_agent 1회 + 메모리 set (수백 건 수준) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | 이월 결정 3건 확정 (전 상태 스킵·UseCase set 비교·frozenset strip 키) | 배상규 |
