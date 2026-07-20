# kb-retrieval-test — Gap Analysis Report

> **Feature**: KB 단위 검색/히스토리 API + 상태 카드·리트리버 테스트 UI
> **Design**: `docs/02-design/features/kb-retrieval-test.design.md`
> **Plan**: `docs/01-plan/features/kb-retrieval-test.plan.md`
> **Analyzer**: gap-detector agent
> **Date**: 2026-07-18
> **Match Rate**: **100% (44/44)** — cosmetic 편차 감점 산식 시 97.7%, 양쪽 모두 DoD ≥90% 충족

---

## 1. 항목별 판정

### 1.1 Design Decisions D1–D10

| # | 결정 | 판정 | 근거 (file:line) |
|---|------|:----:|------|
| D1 | `KbSearchUseCase` 신설, `CollectionSearchUseCase` 미호출·내부 스택만 재사용 | Match | `application/knowledge_base/search_use_case.py:31,78,102` — HybridSearch 직접 조립, 컬렉션 UC import 없음 |
| D2 | `resolve_collection_embedding_model` 모듈 함수 추출, 양쪽 호출 | Match | `collection_search/embedding_resolver.py:12`; 위임 `collection_search/use_case.py:137`, `kb/search_use_case.py:105` |
| D3 | `KnowledgeBaseUseCase.get` 위임 (404/403) | Match | `kb/search_use_case.py:71`; `kb/search_history_use_case.py:33` |
| D4 | `document_id` body 옵션 + `KbDocumentGuard.ensure` 소속검증 | Match | `kb/search_use_case.py:72-76`; `knowledge_base_router.py:778` |
| D5 | filter = {collection_name, kb_id}(+document_id) | Match | `kb/search_use_case.py:121-126` |
| D6 | V049 `kb_id VARCHAR(64) NULL` + `ix_sh_user_kb` | Match | `db/migration/V049__...sql:3-5`; `infrastructure/collection_search/models.py:21` |
| D7 | `save(kb_id=None)` additive + `find_by_user_and_kb` 신설 | Match | `search_history_interfaces.py:21,35`; `search_history_repository.py:30,77` |
| D8 | `KbSearchHistoryUseCase` 경량 신설 | Match | `kb/search_history_use_case.py:13`; `search_history_schemas.py:31` |
| D9 | `KbSearchHistoryPanel` 신설, 기존 패널 무변경 | Match | `components/knowledge-base/KbSearchHistoryPanel.tsx:28` |
| D10 | `searchScopeDoc` 로컬 state, 드릴다운과 독립 | Match | `pages/KnowledgeBaseDetailPage/index.tsx:21,23,112-133` |

### 1.2 API 계약(§3.2) / 에러(§4) / 레이어(§6) / UX(§3.4)

| 항목 | 판정 | 근거 |
|------|:----:|------|
| search 요청 필드 전체 | Match | `knowledge_base_router.py:769-778` (`KbSearchBody`) |
| search 응답 필드 전체 | Match | `knowledge_base_router.py:793-803` (`KbSearchAPIResponse`) |
| search-history 요청/응답 | Match | `knowledge_base_router.py:817-822,886-932` |
| 에러 매핑 404/403/422 + 히스토리 저장실패 무영향 | Match | `_raise_http`; `search_use_case.py:149-175` |
| §3.3 파일 인벤토리 (백엔드 10 + 프론트 8) | Match | 전 파일 존재·역할 일치 |
| §3.4 스코프 UX (기본 배지 / 문서 스코프 / ✕ 복귀) | Match | `KbSearchSection.tsx:84-100`; `KbDocumentTable.tsx:98-108` |
| §6 레이어 배치 + 단일 세션 | Match | domain 순수 유지, `main.py:2881-2903` |

### 1.3 프론트 계약 동기화 — 10/10 Match

constants(2종 엔드포인트) · queryKeys · types(3종) · service(2 메서드) · hooks(2종) ·
KbStatusCards · KbSearchSection · KbDocumentTable(onSearchInDocument) · 페이지 조립 · MSW 목 — 전부 일치.

### 1.4 Test Plan §5 — 6/6 Match (§5.4 수동 E2E는 Deferred, 분모 제외)

- 유스케이스 단위 10+3 케이스, repo SQLite 통합 5 케이스(저장 검증 명시), 라우터 통합 9 케이스, 프론트 17 케이스
- 컬렉션 검색 회귀(D2 추출 후) 통과

### 1.5 Plan FR-01~FR-11 — 11/11 Match

전 기능 요구사항 구현 + 테스트 근거 확인 (상세는 gap-detector 원본 판정 참조).

---

## 2. Gap 목록

**기능/계약을 훼손하는 Gap 0건.** 비차단 cosmetic 편차 2건 — Design 문서 정정 권장(코드 변경 불필요):

| # | 심각도 | 내용 | 처리 |
|---|:------:|------|------|
| G1 | Trivial | 요청 스키마명 설계 `KbSearchAPIRequest` → 실제 `KbSearchBody` | 설계 표기를 실제명으로 정정 |
| G2 | Trivial | 테스트 파일명 설계 `test_search_use_case.py` → 실제 `test_kb_search_use_case.py` | 실제명이 기존 `test_use_case.py`와 충돌 회피로 우수 — 설계 정정 |

---

## 3. 양성 편차 (Design 초과 구현)

| 편차 | 위치 | 가치 |
|------|------|------|
| SQLite variant PK (`with_variant(Integer,"sqlite")`) | `models.py:12-16` | repo 통합테스트를 실제 SQLite 세션으로 수행 |
| `find_by_user_and_kb` 보조정렬 `id.desc()` | `search_history_repository.py:101-104` | 동일 timestamp flakiness 방지 |
| `KbSearchRequest.__post_init__` 도메인 검증 | `search_schemas.py:17-23` | 라우터 422와 별개 도메인 불변식 |
| 명시적 응답 아이템 스키마 2종 | `knowledge_base_router.py:781,806` | "동일 형태" 지시를 구체 타입으로 고정 |
| 추가 테스트(가중치 전달·요청 검증·컬렉션 회귀) | 테스트 4파일 | 설계 최소 스펙 초과 커버리지 |
| 히스토리 상대시간 포매터 + total 배지 | `KbSearchHistoryPanel.tsx:14-23,49-53` | UX 디테일 |

참고: V047 이전 `kb_id NULL` 문서의 검색 제외는 D5의 **의도된 알려진 한계**로 Gap 아님.

---

## 4. 결론

- Match Rate **100% (44/44)** — 설계-구현 완전 동기화
- 이월: Qdrant/ES 실기동 수동 E2E(같은 컬렉션 공유 KB 2개 격리 검증, V049 적용 선행) → 기존 KB 시리즈 공통 체크리스트에 등재
- 다음 단계: `/pdca report kb-retrieval-test`
