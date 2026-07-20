# wiki-user-facing Gap Analysis Report

> **Design**: `docs/02-design/features/wiki-user-facing.design.md`
> **Analyzer**: gap-detector (2026-07-18) + 갭 즉시 보강 반영
> **Match Rate (1차)**: **97.1%** (35항목 = Match 33 · Partial 2 · Missing 0 · Extra 0)
> **Match Rate (보강 후)**: **100%** — Partial 2건 당일 해소, 테스트로 검증

---

## 1. 판정 요약

| 카테고리 | 항목 수 | 1차 판정 | 보강 후 |
|----------|:------:|:--------:|:-------:|
| §1.1 확정 결정 6건 | 6 | Match 5 · Partial 1(⑥) | 전부 Match |
| §1.2 실코드 제약 5건 | 5 | 전부 Match | — |
| §3 상세 설계 (DB/Domain/App/Interfaces/Front) | 5 | 전부 Match | — |
| §4 테스트 계획 · §6 리스크 매핑 | 8 | 전부 Match | — |
| Plan FR-01~FR-11 | 11 | Match 10 · Partial 1(FR-06) | 전부 Match |
| Extra (설계 외 구현) | 0 | 없음 | — |

E2E 수동 검증(Qdrant 실기동)은 Plan에 명시된 이월 항목 — 계산 제외, 공통 체크리스트 등재.

## 2. 발견 갭과 해소

### GAP-1 (Medium) — 프론트 트리 `/` split 계층 렌더 미구현 → ✅ 해소

- 현상: 서버 그룹핑은 정확하나 `AgentKnowledgePage`가 `"여신/한도"`를 단일 평면 라벨로 렌더 — 설계 결정 ⑥("계층 조립은 프론트가 `/` split") 미충족.
- 조치: `buildFolderTree()`(path split → `FolderNode` 트리) + 재귀 `Folder`/`ItemList` 컴포넌트로 교체. 미분류(null path)는 최하단 별도 그룹 유지.
- 검증: `index.test.tsx` — "📁 여신 > 📁 한도 중첩 렌더 + 평면 라벨 부재" 단언 추가, 통과.

### GAP-2 (Low) — 문서 뷰 출처·갱신일 미노출 (FR-06) → ✅ 해소

- 현상: 지식 브라우저 문서 패널에 source_refs·updated_at, 단독 뷰에 updated_at 누락 (데이터는 보유).
- 조치: 두 뷰에 `출처: {refs} · v{n} · 갱신 {date}` 라인 추가.
- 검증: 두 페이지 테스트에 출처/갱신일 렌더 단언 추가, 통과.

## 3. 최종 테스트 현황

| 스위트 | 결과 |
|--------|------|
| 백엔드 위키 전체 (domain·application·api·infra repo) | 143 passed, 기존 회귀 0 |
| 프론트 신규 4파일 (SourceCitation·두 페이지·useWiki 확장) | 18 passed |
| 프론트 회귀 (MessageBubble·WikiPage) | 8 passed |
| `tsc --noEmit` / eslint (변경 파일) | 클린 |

## 4. 이월 항목

- E2E 수동 검증: 실서버에서 문서 작성 → `use_wiki_first` 검색 반영 → 근거 배지 → 문서 뷰 (V051 적용 선행) — KB 시리즈 공통 이월 체크리스트에 합류
- 후속 feature 후보(Plan §8): `agent-workspace-view`, `fix-wiki-distill-dedup`, org 스코프 결정(비교 문서 §5-1)

## 5. 결론

Match Rate 90% 기준 충족(1차 97.1% → 보강 후 100%). `/pdca report wiki-user-facing` 진행 가능.

---

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | gap-detector 1차 분석(97.1%) + GAP-1·2 당일 보강으로 100% 도달 | 배상규 |
