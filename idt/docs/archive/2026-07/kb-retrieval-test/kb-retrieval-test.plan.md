# kb-retrieval-test Planning Document

> **Summary**: `knowledge-bases/{kbId}` 상세 페이지에 컬렉션 문서 관리 페이지 수준의 **업로드/처리 상태 요약 카드**와 **리트리버 테스트(하이브리드 검색 + KB 전용 히스토리)** 를 추가 — 백엔드에 KB 단위(kb_id 필터) 검색/히스토리 API 신설
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | KB 상세 페이지는 문서 목록·업로드·드릴다운만 있고, 컬렉션 문서 관리 페이지(`collections/{name}/documents`)에 있는 **상태 요약 카드(전체/준비완료/처리중/오류)** 와 **하이브리드 검색(리트리버 테스트) 섹션**이 없다. 업로드한 문서가 검색 가능한 상태인지, 실제 RAG에서 어떻게 검색되는지 KB 화면에서 확인할 방법이 없다. 백엔드에도 KB 단위 검색 API가 없어 컬렉션 검색을 쓰면 같은 물리 컬렉션을 공유하는 **다른 KB 문서가 결과에 섞인다**. |
| **Solution** | 백엔드에 `POST /knowledge-bases/{kb_id}/search`(kb_id metadata 필터, document_id 옵션)와 `GET /knowledge-bases/{kb_id}/search-history`를 신설 — 기존 `CollectionSearchUseCase`/하이브리드 검색 스택을 재사용하되 KB 권한 검사 + kb_id 필터를 얹는 additive 확장. `search_history` 테이블에 kb_id 컬럼 추가(V049). 프론트는 컬렉션 페이지의 검증된 컴포넌트(HybridSearchPanel, SearchResultList)를 재사용해 KB 상세 페이지에 상태 카드·검색 섹션·히스토리 패널을 조립한다. |
| **Function/UX Effect** | KB 상세 페이지에서 ① 문서가 몇 개 있고 준비완료/처리중인지 카드로 한눈에 확인, ② 검색 쿼리 + BM25/벡터 가중치·top_k를 조절해 해당 KB 문서만 대상으로 리트리버 테스트, ③ 문서 행 선택 시 그 문서로 범위를 좁혀 검색, ④ 과거 검색 조건을 히스토리에서 원클릭 재적용. |
| **Core Value** | KB 운영자가 업로드→저장→검색 품질까지 **KB 화면 안에서 폐루프로 검증** — 컬렉션 화면을 오가며 다른 KB 문서와 섞인 결과로 추측하던 리트리버 튜닝을 KB 단위 정확한 결과로 대체한다. |

---

## 1. Overview

### 1.1 Purpose

`knowledge-bases/{kbId}` 페이지를 컬렉션 문서 관리 페이지와 동등한 운영 화면으로 끌어올린다:
문서 업로드 상태 가시화 + KB 범위로 정확히 스코핑된 리트리버 테스트.

### 1.2 Background (현재 구조 분석 — 2026-07-18 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| KB 상세 페이지 | KB 정보 + 청킹 설정 카드 + 문서 테이블(헤더에 총 개수 숫자만) + 업로드 모달 + 콘텐츠 드릴다운. 상태 카드·검색 섹션 없음 | `idt_front/src/pages/KnowledgeBaseDetailPage/index.tsx` |
| 컬렉션 문서 페이지(참조 대상) | 상태 카드 4종(chunk_count>0 → 준비완료, 0 → 처리중, 오류 하드코딩 0) + 하이브리드 검색 섹션 + 문서 단위 검색 + 검색 히스토리 | `idt_front/src/pages/CollectionDocumentsPage/index.tsx` |
| 재사용 가능 프론트 컴포넌트 | `HybridSearchPanel`(가중치/topK), `SearchResultList`(결과), `SearchHistoryPanel`(히스토리 — 컬렉션 전용 훅 내장 여부는 Design에서 확인) | `idt_front/src/components/collection/` |
| 컬렉션 검색 API | `POST /collections/{name}/search`, `POST /collections/{name}/documents/{id}/search`, `GET /collections/{name}/search-history`. metadata_filter로 collection_name(+document_id) 필터 | `src/api/routes/collection_search_router.py`, `src/application/collection_search/use_case.py:89-91` |
| KB 검색 API | **없음**. KB 라우터는 CRUD/문서목록/업로드/콘텐츠 브라우즈만 | `src/api/routes/knowledge_base_router.py` |
| kb_id 메타데이터 | KB 업로드 시 `extra_metadata={"kb_id", "kb_name"}`로 Qdrant/ES 양쪽 저장. 문서 목록도 kb_id payload 기준 필터 (V047) | `src/application/knowledge_base/upload_use_case.py:86`, `db/migration/V047__*.sql` |
| KB↔컬렉션 관계 | KB는 물리 컬렉션(`collection_name`)을 공유 가능 — 컬렉션 검색은 타 KB 문서가 섞임 | `knowledge_base_router.py:422-430` 주석 |
| search_history 테이블 | user_id/collection_name/document_id/query/가중치/top_k/result_count. **kb_id 없음** | `db/migration/V015__create_search_history.sql` |
| 임베딩 모델 해석 | 컬렉션 검색은 activity_log의 CREATE 기록에서 embedding_model을 읽음 — KB 플로우로 만든 컬렉션에 이 기록이 있는지 확인 필요 | `use_case.py:131-154` (`_resolve_embedding_model`) |
| 문서-KB 소속 검증 | 콘텐츠 브라우저용 가드 존재: document_metadata.kb_id 일치 검증, 불일치 시 404 | `src/application/knowledge_base/content_browse_guard.py` |

### 1.3 Related Documents

- 선행 기능: `kb-management-ui`(문서 목록 API·D4 kb_id NULL 한계), `kb-content-browser`(드릴다운·가드), `kb-rag-filter` — `docs/archive/2026-07/`
- 컬렉션 검색 원형: `collection-document-browser` 등 — `docs/01-plan/features/`
- 규칙: `idt/CLAUDE.md`, `docs/rules/db-session.md`, `docs/rules/testing.md`, 루트 `CLAUDE.md` §4-1(API 계약 동기화)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**
- [ ] `POST /api/v1/knowledge-bases/{kb_id}/search` 신설 — KB 조회(kb_id→collection_name) + **KB 권한 검사**(컬렉션 권한이 아닌 KB scope 기준) + metadata_filter에 `kb_id` 주입 후 기존 하이브리드 검색 스택 재사용. 요청/응답 스키마는 컬렉션 검색과 동일 형태(top_k, bm25/vector weight, rrf_k 등)
- [ ] 문서 단위 검색: 같은 엔드포인트에 `document_id` 옵션 파라미터 — 해당 문서가 이 KB 소속인지 검증(`content_browse_guard` 재사용 검토) 후 metadata_filter에 추가
- [ ] `GET /api/v1/knowledge-bases/{kb_id}/search-history` 신설 — kb_id 기준 히스토리 조회
- [ ] `search_history` 테이블에 `kb_id VARCHAR NULL` 컬럼 + 인덱스 추가 — **V049 마이그레이션** (기존 행/컬렉션 검색 경로는 kb_id NULL로 무변경, additive)
- [ ] `SearchHistoryRepositoryInterface.save`에 kb_id 옵션 파라미터 추가(기본 None — 기존 호출부 무영향) + kb_id 조회 메서드
- [ ] KB 검색 유스케이스(가칭 `KbSearchUseCase`) — application/knowledge_base에 신설, `CollectionSearchUseCase` 내부 스택(임베딩 해석·HybridSearchUseCase) 재사용 방식은 Design에서 확정
- [ ] pytest 선행 작성 (TDD: 유스케이스 단위 — kb_id 필터/권한/문서 소속 검증, 라우터 403/404/422, 히스토리 저장·조회)

**프론트엔드 (idt_front/)**
- [ ] KB 상세 페이지 상태 요약 카드 4종(전체/준비완료/처리중/오류) — `KbDocumentInfo.chunk_count` 기반 간이 판정(컬렉션 페이지와 동일 기준), 백엔드 무변경
- [ ] 하이브리드 검색 섹션 — 검색 입력 + `HybridSearchPanel`/`SearchResultList` 재사용, KB 검색 API 연동
- [ ] 문서 단위 검색 — 문서 행 선택 시 "이 문서에서 검색" 스코프 전환 UI
- [ ] KB 검색 히스토리 패널 — 조건 재적용(query/가중치/topK). `SearchHistoryPanel` 재사용 가능 여부 Design에서 판단(컬렉션 결합 시 KB용 신규)
- [ ] API 계약 동기화: `constants/api.ts` 엔드포인트 상수, `types/knowledgeBase.ts` 타입, `services/` + `hooks/useKnowledgeBases`(또는 신규 훅) — Vitest+MSW 테스트 선행

### 2.2 Out of Scope

- 문서별 실제 저장 상태(Qdrant/ES 실측) 기반 오류 카운트 — 이번엔 컬렉션 페이지와 동일한 chunk_count 간이 판정(오류 카드는 0 고정), 실측은 후속 후보
- KB 문서 목록 페이지네이션 UI (API는 이미 offset/limit 지원 — 화면 반영은 후속)
- 컬렉션 검색/히스토리 화면·API의 개편 (무변경 — 교차검증 기준선 유지)
- 검색 결과에서 콘텐츠 브라우저로의 청크 점프 연동
- rerank/multi-query 등 검색 파이프라인 자체의 변경 (기존 하이브리드 검색 그대로 사용)
- V047 이전 업로드 문서(kb_id NULL)의 검색 편입 — 문서 목록과 동일한 알려진 한계로 수용

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `POST /knowledge-bases/{kb_id}/search`가 해당 KB 문서(kb_id payload 일치)만 대상으로 하이브리드 검색 결과를 반환한다 — 같은 컬렉션의 타 KB 문서는 결과에 포함되지 않는다 | High | Pending |
| FR-02 | 검색 요청은 컬렉션 검색과 동일한 튜닝 파라미터(top_k, bm25/vector weight, rrf_k 등)를 지원한다 | High | Pending |
| FR-03 | `document_id` 지정 시 해당 문서로 범위를 좁혀 검색하며, 문서가 이 KB 소속이 아니면 404를 반환한다 | High | Pending |
| FR-04 | KB 접근 권한이 없는 사용자는 403, 존재하지 않는 kb_id는 404를 받는다 (KB scope 권한 기준 — 컬렉션 권한 아님) | High | Pending |
| FR-05 | KB 검색 실행 시 히스토리가 kb_id와 함께 저장되고, `GET /knowledge-bases/{kb_id}/search-history`로 본인 기록을 조회할 수 있다. 히스토리 저장 실패는 검색 응답에 영향을 주지 않는다(기존 정책 유지) | High | Pending |
| FR-06 | `search_history` V049 마이그레이션: kb_id NULL 허용 컬럼 + 인덱스. 기존 컬렉션 검색 히스토리 저장/조회는 회귀 없다 | High | Pending |
| FR-07 | KB 상세 페이지 상단에 상태 카드 4종(전체/준비완료/처리중/오류)이 표시된다 — chunk_count>0=준비완료, 0=처리중 (컬렉션 페이지와 동일 판정) | High | Pending |
| FR-08 | KB 상세 페이지 검색 섹션에서 쿼리+가중치+topK로 검색을 실행하고 결과(점수·BM25/벡터 순위·출처·내용)를 확인할 수 있다 | High | Pending |
| FR-09 | 문서 행 선택 상태에서 "이 문서에서 검색"으로 범위를 전환할 수 있고, 현재 검색 스코프(KB 전체/특정 문서)가 UI에 표시된다 | Medium | Pending |
| FR-10 | 히스토리 패널에서 과거 검색 조건을 클릭하면 입력폼에 재적용된다 | Medium | Pending |
| FR-11 | 프론트 타입/서비스/훅/엔드포인트 상수가 백엔드 계약과 동기화된다 (루트 CLAUDE.md §4-1) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 신규 유스케이스는 application/knowledge_base, 라우터는 위임만. domain→infrastructure 참조 금지, Repository 내 commit 금지 | `/verify-architecture` |
| 호환성 | 컬렉션 검색/히스토리 경로 회귀 0 (repo save 시그니처는 기본값 additive). 기존 KB API 무변경 | pytest (Windows 격리 실행 기준) |
| TDD | 신규 모듈 테스트 선행 작성 (Red→Green) | `/verify-tdd` |
| 로깅 | 검색 시작/완료·필터 내용·히스토리 저장 실패를 request_id 포함 구조화 로그로 기록 | `/verify-logging` |
| DB | 마이그레이션은 Flyway 형식 V049, FK/COLLATE 명시 금지 관례 준수 | `db/migration/` 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현: KB 상세 페이지에서 상태 카드 확인 → 검색 실행 → KB 문서만 히트 → 히스토리 재적용 플로우 동작
- [ ] 같은 컬렉션을 공유하는 2개 KB로 kb_id 필터 격리 테스트 통과
- [ ] pytest 선행 작성(Red→Green) + 컬렉션 검색 회귀 0
- [ ] Vitest(MSW, `--pool=threads`) 통과
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 레이어 의존성 규칙 위반 0 (`/verify-architecture`)
- [ ] 신규 함수 40줄 이하, if 중첩 2단계 이하
- [ ] 사전 실패 테스트(백엔드 api 28건·infra 30건, 프론트 8건)는 기존 이슈 — 신규 회귀로 오인 금지
- [ ] E2E(Qdrant/ES 실기동) 수동 검증 — 기존 KB 시리즈와 동일하게 공통 이월 체크리스트에 등재

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| KB 플로우로 생성된 컬렉션에 activity_log CREATE 기록이 없어 `_resolve_embedding_model` 실패 → 검색 500/422 | High | Medium | Design에서 KB 생성 경로의 activity_log 기록 여부 실코드 확인. 없으면 KB 검색용 임베딩 해석 폴백(설정 기본 모델 or KB 레코드 기반) 정의 |
| ES 측 kb_id 필터 미지원/필드 불일치로 BM25 결과에 타 KB 문서 혼입 | High | Medium | Design에서 HybridSearchUseCase의 ES metadata_filter 처리 경로 확인 + 격리 테스트(FR-01)로 고정. 요약 계층 ID 계약(rawchunk는 ES `_id`만 일치) 주의 |
| `SearchHistoryRepositoryInterface.save` 시그니처 변경이 컬렉션 검색 저장 회귀 유발 | Medium | Low | kb_id 기본값 None additive + 기존 테스트 유지. repo 컬럼 화이트리스트 누락 시 조용히 미저장되는 선례 있음 — 저장 검증 테스트 필수 |
| 물리 컬렉션 공유 시 가중치 튜닝 결과가 컬렉션 검색과 달라 사용자 혼동 | Low | Medium | 검색 섹션에 "이 KB 문서만 검색" 문구 명시, 응답에 kb_id 포함 |
| V047 이전 문서(kb_id NULL)가 검색에서 빠져 "문서는 보이는데 검색 안 됨" 혼동 | Medium | Low | 문서 목록과 동일한 알려진 한계(D4)로 문서화 — 목록 자체가 kb_id 기준이라 화면 정합성은 유지됨 |
| SearchHistoryPanel이 컬렉션 API에 결합돼 재사용 불가 | Low | Medium | Design에서 컴포넌트 의존 확인 — 결합 시 presentational 분리 or KB용 경량 패널 신규 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트 편입 — Thin DDD(Domain→Application→Infrastructure) 현행 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| KB 검색 API 형태 | ① 컬렉션 검색 재사용(프론트만) ② KB 전용 엔드포인트 신설 | ② `POST /knowledge-bases/{kb_id}/search` | 컬렉션 공유 시 타 KB 문서 혼입 차단(kb_id 필터), KB 권한 모델 적용. 컬렉션 검색은 무변경(기준선 유지) — 사용자 확정 |
| 검색 로직 재사용 방식 | ① CollectionSearchUseCase 직접 호출 ② 내부 스택(임베딩 해석+HybridSearch) 재사용하는 KB 유스케이스 신설 | Design에서 확정 (②안 우선 검토) | ①은 컬렉션 권한 검사가 함께 실행되는 문제 — KB 권한만 타야 함 |
| 히스토리 저장 | ① 컬렉션 히스토리 재사용 ② kb_id 컬럼 추가 + KB 단위 조회 | ② (V049, additive nullable) | KB 단위 정확한 히스토리 — 사용자 확정. 기존 행/경로 무영향 |
| 상태 카드 판정 | ① chunk_count 간이 판정 ② 저장소 실측 | ① (컬렉션과 동일) | 백엔드 무변경 + UX 일관성 — 사용자 확정. 실측은 후속 |
| 문서 단위 검색 | 별도 엔드포인트 vs 동일 엔드포인트 document_id 파라미터 | Design에서 확정 (컬렉션은 별도 path 선례) | KB 소속 검증(404) 필요 — content_browse_guard 재사용 검토 |

### 6.3 Clean Architecture Approach

domain 무변경(search_history 인터페이스에 kb_id 옵션만 additive).
application/knowledge_base에 검색 유스케이스 추가, 라우터는 knowledge_base_router에 엔드포인트 추가 후 위임만.
한 유스케이스 내 단일 세션 규칙(`docs/rules/db-session.md`) 준수.

---

## 7. Convention Prerequisites

- [x] `idt/CLAUDE.md` + `docs/rules/testing.md` 준수 (TDD 필수)
- [x] 로깅: LoggerInterface + request_id (print 금지)
- [x] 프론트: API 상수 `constants/api.ts` 집중, MSW 파일별 3종 훅, Vitest `--pool=threads`
- [x] 마이그레이션: Flyway V049, FK 참조 시 CHARSET/COLLATE 명시 금지 관례
- [x] pytest는 Windows에서 파일 격리 실행 기준으로 판정

신규 환경변수 없음.

---

## 8. Next Steps

1. [ ] `/pdca design kb-retrieval-test` — 임베딩 모델 해석 경로 실증, ES kb_id 필터 경로 확인, 유스케이스/스키마 시그니처, SearchHistoryPanel 재사용성, 문서 단위 검색 API 형태 확정
2. [ ] 구현 (TDD: 마이그레이션·repo → KB 검색 유스케이스 → 라우터 → 프론트 타입/서비스/훅 → 페이지 조립)
3. [ ] `/pdca analyze kb-retrieval-test`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — KB 상세 페이지 상태카드+리트리버 테스트, KB 전용 검색/히스토리 API 방향 확정 (사용자 Q&A 4건 반영) | 배상규 |
