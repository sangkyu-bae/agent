# kb-retrieval-test Completion Report

> **Feature**: KB 상세 페이지 상태 요약 카드 + 리트리버 테스트 (KB 단위 검색/히스토리 API)
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Period**: 2026-07-18 (Plan → Report 동일일 완료)
> **Match Rate**: **100% (44/44)** — Gap 0건, iterate 불필요

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | kb-retrieval-test |
| 기간 | 2026-07-18 (1일, iterate 0회) |
| Match Rate | 100% (44/44 검증 항목) |
| 산출물 | 백엔드 신규 5 + 변경 6, 프론트 신규 5(테스트 포함) + 변경 8, 마이그레이션 V049 |
| 테스트 | 백엔드 신규 28 + 회귀 195 통과, 프론트 신규/갱신 17 통과, type-check 통과 |

### 1.3 Value Delivered (4-Perspective)

| Perspective | Delivered |
|-------------|-----------|
| **Problem** | KB 상세 페이지에 문서 처리 상태 가시화·리트리버 테스트 수단이 없었고, 컬렉션 검색을 대신 쓰면 같은 물리 컬렉션을 공유하는 타 KB 문서가 결과에 혼입되었다. |
| **Solution** | `POST /knowledge-bases/{kb_id}/search`(kb_id payload 필터 + document_id 스코프) · `GET .../search-history` 신설. 기존 하이브리드 검색 스택은 공용 임베딩 해석 헬퍼로 추출해 재사용(D2), 컬렉션 검색 경로는 바이트 무변경 — 회귀 44건 통과로 검증. |
| **Function/UX Effect** | KB 화면에서 ① 상태 카드 4종(전체/준비완료/처리중/오류), ② 가중치·topK 조절 하이브리드 검색(KB 격리), ③ "이 문서에서 검색" 스코프 전환(드릴다운과 독립 state), ④ 히스토리 원클릭 재적용. |
| **Core Value** | KB 운영자가 업로드→저장→검색 품질을 KB 화면 안에서 폐루프로 검증 — 리트리버 튜닝이 타 KB 문서가 섞인 추측에서 KB 단위 정확한 실측으로 전환. |

---

## 1. PDCA 사이클 요약

| 단계 | 산출물 | 핵심 결과 |
|------|--------|----------|
| Plan | `01-plan/features/kb-retrieval-test.plan.md` | 사용자 Q&A 4건으로 방향 확정(KB 전용 API·KB 히스토리·4카드·문서단위검색), 리스크 2건 식별 |
| Design | `02-design/features/kb-retrieval-test.design.md` | 리스크 2건 실코드 해소(KB=기존 컬렉션 배정 구조, ES `kb_id: keyword` 매핑 기존재), D1–D10 확정 |
| Do | 코드 + 테스트 (TDD Red→Green) | 백엔드 28 + 프론트 17 테스트 선행 작성 후 구현, 회귀 0 |
| Check | `03-analysis/kb-retrieval-test.analysis.md` | Match 100% (44/44), 차단 Gap 0, cosmetic 2건(설계 표기 정정 권장), 양성 편차 6건 |

## 2. 구현 내역

### 2.1 백엔드 신규 (idt/)

| 파일 | 역할 |
|------|------|
| `db/migration/V049__alter_search_history_add_kb_id.sql` | kb_id nullable 컬럼 + `(user_id, kb_id)` 인덱스 (additive) |
| `src/domain/knowledge_base/search_schemas.py` | `KbSearchRequest`(도메인 검증 포함)/`KbSearchResult` |
| `src/application/collection_search/embedding_resolver.py` | 임베딩 모델 해석 공용 헬퍼 (D2 — 컬렉션/KB 양쪽 사용) |
| `src/application/knowledge_base/search_use_case.py` | `KbSearchUseCase` — KB 권한→가드→kb_id 필터 하이브리드 검색→히스토리 저장 |
| `src/application/knowledge_base/search_history_use_case.py` | `KbSearchHistoryUseCase` — kb_id 단위 본인 히스토리 |

### 2.2 백엔드 변경

`search_history` 인터페이스/스키마/모델/레포(kb_id additive + `find_by_user_and_kb`),
`CollectionSearchUseCase`(헬퍼 위임 — 동작 불변), `knowledge_base_router.py`(엔드포인트 2개 + 스키마 4종 + DI 스텁),
`main.py`(`create_kb_search_factories` — 단일 세션 규칙 준수 배선).

### 2.3 프론트엔드 (idt_front/)

- 신규: `KbStatusCards`(+test), `KbSearchSection`(+test), `KbSearchHistoryPanel`
- 변경: `constants/api.ts`, `lib/queryKeys.ts`, `types/knowledgeBase.ts`(컬렉션 결과 타입 재사용), `knowledgeBaseService`, `useKnowledgeBases`(`useKbSearch`/`useKbSearchHistory`), `KbDocumentTable`(onSearchInDocument), `KnowledgeBaseDetailPage`(조립+테스트 3건), MSW 핸들러
- 재사용: `HybridSearchPanel`, `SearchResultList` (컬렉션 컴포넌트 무변경)

### 2.4 테스트 (전부 선행 작성 — TDD)

| 스위트 | 건수 | 비고 |
|--------|------|------|
| KbSearchUseCase / KbSearchHistoryUseCase 단위 | 10 + 3 | 필터·가드·권한·히스토리 안전 저장 |
| SearchHistoryRepository SQLite 통합 | 5 | kb_id 저장 검증(조용한 미저장 방지) + 컬렉션 회귀 |
| KB 검색 라우터 통합 | 9 | 200/403/404/422 + document_id + 페이징 |
| 프론트 (Vitest+MSW, `--pool=threads`) | 17 | 카드 판정·검색·스코프 전환·히스토리 재적용·에러 |
| 회귀 | 195 | 컬렉션 검색 44 + KB application 108 + KB 라우터 32 + 브라우저 11 |

## 3. 배운 점 / 재사용 가능한 패턴

- **공용 헬퍼 추출 위임 패턴**: 기존 유스케이스의 private 메서드를 모듈 함수로 추출하고 원본은 위임만 — 시그니처·기존 테스트 무변경으로 이중화 제거 (`embedding_resolver.py`)
- **KB 격리 검색**: `metadata_filter`에 kb_id를 얹으면 Qdrant(SearchFilter)·ES(term filter, `kb_id: keyword` 매핑) 양쪽에 동일 적용 — 신규 필드 격리 검색은 매핑 확인이 선행 조건
- **SQLite variant PK**: `BigInteger().with_variant(Integer, "sqlite")`로 MySQL BIGINT 유지하면서 repo 통합테스트를 실제 세션으로 실행 가능
- **스코프 state 분리(D10)**: 드릴다운 선택과 검색 스코프를 독립 state로 — 행 클릭마다 검색 범위가 바뀌는 결합 버그 예방
- Plan 단계 리스크(임베딩 해석·ES 필터)를 Design에서 실코드로 해소해 Do 단계 재작업 0회

## 4. 이월 항목

| 항목 | 내용 | 조건 |
|------|------|------|
| V049 적용 | 배포 전 DB 마이그레이션 필수 — 미적용 시 히스토리 저장만 조용히 실패(검색은 동작) | 배포 시 |
| 수동 E2E | 같은 컬렉션 공유 KB 2개로 kb_id 격리 실측 + V047 이전 문서 미출현 + 문서 스코프 검색 | Qdrant/ES 기동 시 (기존 KB 시리즈 공통 체크리스트) |
| Design 표기 정정 | `KbSearchAPIRequest`→`KbSearchBody`, 테스트 파일명 — cosmetic 2건 | 아카이브 전 선택 |
| 후속 후보 | 문서별 저장 상태 실측 오류 카운트, 히스토리 패널 컬렉션/KB 공용화, KB 문서 목록 페이지네이션 UI | 별도 기능 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-18 | 완료 보고서 — Match 100%, iterate 0회 | 배상규 |
