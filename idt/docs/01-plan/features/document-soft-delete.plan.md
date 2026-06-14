# Document Soft Delete Planning Document

> **Summary**: 문서 삭제를 3개 저장소(RDB·Qdrant·ES) 물리 삭제에서 `is_deleted`/`deleted_at` 플래그 기반 soft delete로 전환하고, 모든 검색·조회 경로에서 삭제 문서를 제외하며, 백엔드 복구(restore) API를 제공한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-04
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `/collections/{collection}/documents`에서 문서 삭제 시 RDB·Qdrant·ES 3개 저장소 모두 **물리 삭제(hard delete)** → 실수 삭제 시 복구 불가, 데이터 유실 위험 |
| **Solution** | 3개 저장소 모두 soft delete 전환: RDB `deleted_at` 컬럼, Qdrant/ES `is_deleted` 페이로드·필드 플래그. 모든 검색·조회 경로에 삭제 제외 필터 주입 + 백엔드 복구 API 추가 |
| **Function/UX Effect** | 삭제 문서는 목록·RAG 검색에서 즉시 사라지지만 데이터는 보존되어, 복구 API 호출만으로 검색까지 완전 복원. 무기한 보관(수동 purge) |
| **Core Value** | 금융/정책 문서의 실수 삭제로부터 데이터 보호 — 운영 안정성과 복구 가능성 확보 |

---

## 1. Overview

### 1.1 Purpose

현재 문서 삭제는 RDB·Qdrant·ES 3개 저장소에서 모두 물리 삭제를 수행해 복구가 불가능하다.
이를 soft delete로 전환하여 **데이터 보존 + 검색 제외 + 복구 가능**을 달성한다.

### 1.2 Background — 현재 정책 (Hard Delete) 조사 결과

`DeleteDocumentUseCase.execute_single` (`src/application/doc_browse/delete_document_use_case.py`):

| 저장소 | 현재 동작 | 메서드 |
|--------|----------|--------|
| **Qdrant** | `client.delete(FilterSelector(document_id))` — 포인트 물리 삭제 | `_delete_qdrant_chunks` |
| **ES** | `delete_by_query(document_id)` — 청크 물리 삭제 | `_delete_es_chunks` |
| **RDB** | `DELETE FROM document_metadata WHERE document_id` | `DocumentMetadataRepository.delete_by_document_id` |

- `DocumentMetadataModel`에 `is_deleted`/`deleted_at` 컬럼 **없음** (`src/infrastructure/doc_browse/models.py`)
- 배치 삭제(`execute_batch`)는 `execute_single` 반복 → 동일 정책
- 삭제 자체가 best-effort: ES 실패는 warning 후 계속 (`_delete_es_chunks` except)

### 1.3 핵심 난점 — 검색 정합성

3-store soft delete의 가장 큰 작업은 **삭제 문서가 RAG 검색·조회에 다시 잡히지 않도록 모든 read 경로에 제외 필터를 주입**하는 것이다. 한 곳이라도 누락되면 "삭제된 문서가 답변 출처로 등장"하는 정합성 버그가 발생한다.

**영향받는 read 경로 (전수 감사 대상)**:

| # | 경로 | 파일 | 저장소 |
|---|------|------|--------|
| 1 | 목록 조회 | `doc_browse/list_documents_use_case.py` → `document_metadata_repository.find_by_collection` | RDB |
| 2 | 청크 조회 | `doc_browse/get_chunks_use_case.py` `_scroll_filtered` | Qdrant |
| 3 | 하이브리드 BM25 | `hybrid_search/use_case.py` `_fetch_bm25` | ES |
| 4 | 하이브리드 벡터 | `hybrid_search/use_case.py` `_fetch_vector` → `qdrant_vectorstore.search_by_vector` | Qdrant |
| 5 | 벡터스토어 | `infrastructure/vector/qdrant_vectorstore.py` `search_by_vector`/`_build_qdrant_filter` | Qdrant |
| 6 | 리트리버 | `infrastructure/retriever/qdrant_retriever.py` `retrieve_with_scores`/`retrieve_by_metadata` | Qdrant |
| 7 | Parent-Child | `infrastructure/retriever/parent_child_retriever.py` (상속 + `_fetch_parents`) | Qdrant |
| 8 | ES 검색 | `infrastructure/elasticsearch/es_repository.py` `search` | ES |
| 9 | 컬렉션 검색 | `application/collection_search/use_case.py` | Qdrant/ES |

### 1.4 Related Documents

- 기존 코드: `src/application/doc_browse/delete_document_use_case.py` (삭제 흐름)
- 기존 코드: `src/infrastructure/doc_browse/models.py` (스키마)
- 기존 코드: `src/api/routes/doc_browse_router.py` (엔드포인트)
- 규칙: `docs/rules/db-session.md`, `docs/rules/rag-retrieval.md`
- 스킬: `/db-migration` (Flyway 마이그레이션 생성)

---

## 2. Scope

### 2.1 In Scope

- [ ] RDB: `document_metadata.deleted_at DATETIME NULL` 컬럼 + 인덱스 추가 (Flyway 마이그레이션)
- [ ] Qdrant: 삭제 시 `set_payload(is_deleted=true)` (포인트 보존), 검색 시 `must_not is_deleted=true`
- [ ] ES: `is_deleted` 매핑 추가, 삭제 시 `update_by_query(is_deleted=true)`, 검색 시 제외
- [ ] `DeleteDocumentUseCase`: hard → soft 전환 (3개 저장소 플래그 마킹)
- [ ] 9개 read 경로 전수에 삭제 제외 필터 주입
- [ ] 복구 API: 삭제 문서 목록 조회 + 단건/배치 restore (RDB·Qdrant·ES 플래그 해제)
- [ ] 복구 권한 검증 (삭제와 동일 정책 `DocumentDeletePolicy` 재사용/확장)
- [ ] Activity log: soft delete / restore 액션 기록
- [ ] 무기한 보관 (자동 purge 없음)
- [ ] 각 레이어 단위 테스트 (TDD)

### 2.2 Out of Scope

- **프론트 휴지통(trash) UI** — 백엔드 restore API만 (프론트는 후속)
- **자동 영구삭제(retention/purge job)** — 무기한 보관, 수동 purge만 (purge API도 이번엔 제외)
- **원본 업로드 파일 보관/재인제스트 복구** — 본 작업은 플래그 기반 복구라 불필요
- **기존 데이터 백필** — 기존 문서는 `deleted_at=NULL`/`is_deleted` 부재로 자연히 "정상" 취급

### 2.3 Decisions (사용자 확정)

| 항목 | 결정 |
|------|------|
| 저장소 범위 | **RDB + Qdrant + ES 모두 soft** |
| 복구 범위 | **백엔드 복구 API 포함** (프론트 UI 제외) |
| 보관 정책 | **무기한 보관** (수동 purge만) |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | RDB `document_metadata`에 `deleted_at` 컬럼 + 인덱스 추가 | High | Pending |
| FR-02 | 삭제 시 RDB는 `deleted_at=now` UPDATE (물리 DELETE 폐기) | High | Pending |
| FR-03 | 삭제 시 Qdrant는 `set_payload(is_deleted=true)` (delete 폐기) | High | Pending |
| FR-04 | 삭제 시 ES는 `update_by_query(is_deleted=true)` (delete_by_query 폐기) | High | Pending |
| FR-05 | 목록·청크 조회에서 삭제 문서 제외 (RDB `deleted_at IS NULL`, Qdrant scroll 필터) | High | Pending |
| FR-06 | 모든 RAG 검색 경로(하이브리드/벡터/BM25/리트리버/컬렉션검색)에서 삭제 청크 제외 | High | Pending |
| FR-07 | 삭제 문서 목록 조회 API (휴지통 데이터) | High | Pending |
| FR-08 | 단건/배치 복구 API (RDB·Qdrant·ES 플래그 해제) | High | Pending |
| FR-09 | 복구 시 권한 검증 (삭제와 동일 정책) | Medium | Pending |
| FR-10 | soft delete / restore 액티비티 로그 기록 | Medium | Pending |
| FR-11 | 부분 실패 내성 — 한 저장소 실패 시 로깅 후 계속, RDB를 source of truth로 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| 검색 정합성 | 삭제 문서가 어떤 검색/조회에도 노출되지 않음 | 9개 경로 회귀 테스트 |
| 성능 | Qdrant/ES `is_deleted` 필터용 페이로드/필드 인덱스로 지연 최소화 | 검색 응답시간 |
| 스토리지 | 삭제 데이터 보존으로 용량 증가 인지 (무기한 보관) | 모니터링 권고 |
| 복구 정확성 | restore 후 목록·검색에 즉시 복원 | 복구 e2e 테스트 |
| 무회귀 | 기존 문서(플래그 부재)는 정상 노출 | 회귀 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~11 구현
- [ ] 9개 read 경로 삭제 제외 검증 (특히 RAG 검색 출처에 삭제 문서 미등장)
- [ ] 삭제 → 목록/검색 사라짐 → 복구 → 재등장 e2e 시나리오 통과
- [ ] Flyway 마이그레이션 적용 및 롤백 확인
- [ ] 기존 문서 무회귀 (플래그 부재 = 정상)

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상 (변경 모듈)
- [ ] mypy 통과, 레이어 의존성 규칙 준수
- [ ] `print()` 미사용, 구조화 로깅 (LOG-001)
- [ ] Repository 내부 commit/rollback 호출 금지 (UseCase 단일 세션)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| read 경로 누락 → 삭제 문서가 RAG 검색에 노출 | High | High | 9개 경로 체크리스트 전수 감사 + 경로별 회귀 테스트, Design에서 필터 헬퍼 단일화 |
| 3-store 부분 실패로 상태 불일치 (RDB만 soft, Qdrant 실패 등) | High | Medium | RDB를 source of truth로, 저장소별 best-effort + 실패 로깅, 복구 시 재시도 가능하게 멱등 설계 |
| Qdrant/ES 기존 포인트에 `is_deleted` 필드 부재 → 필터 오작동 | Medium | Medium | `must_not match(is_deleted=true)` 방식 사용 → 필드 없는 포인트는 자연 통과(정상 취급), 백필 불필요 |
| 스토리지 무기한 증가 | Medium | High | 무기한 보관은 사용자 결정. 향후 purge/retention 후속 과제로 명시, 용량 모니터링 권고 |
| `is_deleted` 필터 미인덱싱으로 검색 성능 저하 | Medium | Medium | Qdrant payload index + ES keyword/boolean 매핑, RDB `deleted_at` 인덱스 |
| 복구 시 일부 저장소만 복원되어 불일치 | Medium | Medium | restore도 멱등 + 부분 실패 로깅, RDB 우선 복원 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic, complex | ☑ |

> 기존 Thin DDD 구조 유지. 신규 복구 모듈은 `doc_browse` 도메인에 확장.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 저장소 범위 | RDB만 / 3-store | **3-store soft** | 플래그만으로 검색까지 완전 복구 (사용자 결정) |
| RDB 플래그 | `is_deleted bool` / `deleted_at datetime` | **`deleted_at` (NULL=정상)** | 삭제 시각 기록 → 향후 retention 근거, NULL 필터 단순 |
| Qdrant 삭제 | delete / `set_payload` | **`set_payload(is_deleted=true)`** | 포인트 보존, 복구는 페이로드 갱신 |
| ES 삭제 | delete_by_query / `update_by_query` | **`update_by_query(is_deleted=true)`** | 문서 보존, 매핑 필드 토글 |
| 검색 제외 방식 | filter is_deleted=false / `must_not is_deleted=true` | **`must_not match(true)`** | 기존(필드 부재) 데이터 백필 불필요 |
| 복구 UI | 백엔드만 / 풀스택 | **백엔드 API만** | 사용자 결정, 프론트는 후속 |
| 필터 주입 | 경로별 산발 / 공통 헬퍼 | **공통 필터 헬퍼 단일화** | 누락 위험 최소화, Design에서 정의 |

### 6.3 Clean Architecture Approach

```
Enterprise (Thin DDD) — 변경/신규 파일

src/
├── domain/doc_browse/
│   ├── schemas.py            # [확장] DocumentMetadata에 deleted_at, 삭제목록/복구 결과 VO
│   ├── interfaces.py         # [확장] soft delete/restore/find_deleted 메서드
│   └── policies.py           # [확장] DocumentRestorePolicy (또는 can_delete 재사용)
│
├── application/doc_browse/
│   ├── delete_document_use_case.py   # [수정] hard → soft 마킹
│   └── restore_document_use_case.py  # [신규] 복구 UseCase
│
├── infrastructure/
│   ├── doc_browse/
│   │   ├── models.py                       # [수정] deleted_at 컬럼 + 인덱스
│   │   ├── document_metadata_repository.py # [수정] soft delete/restore/find_deleted
│   │   └── session_scoped_metadata_repository.py # [수정] 동일 위임
│   ├── vector/qdrant_vectorstore.py        # [수정] 검색 is_deleted 제외 + soft mark 헬퍼
│   ├── retriever/qdrant_retriever.py        # [수정] 검색 제외 필터
│   ├── retriever/parent_child_retriever.py  # [수정/상속 확인]
│   └── elasticsearch/es_repository.py       # [수정] update_by_query + 검색 제외
│
├── application/
│   ├── hybrid_search/use_case.py            # [수정] _fetch_bm25/_fetch_vector 제외 필터
│   ├── doc_browse/get_chunks_use_case.py    # [수정] scroll 제외
│   ├── doc_browse/list_documents_use_case.py# [수정/위임]
│   └── collection_search/use_case.py        # [수정] 제외 필터
│
├── api/routes/doc_browse_router.py          # [수정] 삭제목록/복구 엔드포인트 추가
│
└── db/migration/Vxxx__add_deleted_at_to_document_metadata.sql  # [신규] Flyway
```

### 6.4 Data Flow — Soft Delete & Restore

```
[Soft Delete]
DELETE /collections/{c}/documents/{id}
   │
   ▼ DeleteDocumentUseCase.execute_single
   ├─ 권한 검증 (DocumentDeletePolicy)
   ├─ Qdrant: set_payload(is_deleted=true)  WHERE document_id   ◄── 보존
   ├─ ES:     update_by_query(is_deleted=true) WHERE document_id ◄── 보존
   ├─ RDB:    UPDATE document_metadata SET deleted_at=now WHERE document_id ◄── 보존
   └─ ActivityLog(DELETE_DOCUMENT)

[검색/조회 — 모든 경로 공통]
   필터에 must_not(is_deleted=true) / deleted_at IS NULL 주입
   → 삭제 문서·청크 제외

[Restore]
POST /collections/{c}/documents/{id}/restore   (또는 배치)
   │
   ▼ RestoreDocumentUseCase
   ├─ 권한 검증
   ├─ RDB:    UPDATE SET deleted_at=NULL   ◄── source of truth 우선
   ├─ Qdrant: set_payload(is_deleted=false) (또는 키 제거)
   ├─ ES:     update_by_query(is_deleted=false)
   └─ ActivityLog(RESTORE_DOCUMENT)
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` + `docs/rules/` (db-session, logging, rag-retrieval)
- [x] Thin DDD 레이어 분리
- [x] pytest TDD
- [x] Flyway 마이그레이션 (`/db-migration` 스킬, `db/migration/Vxxx__*.sql`)
- [x] `DocumentDeletePolicy` 권한 패턴 확립

### 7.2 Conventions to Define/Verify

| Category | Current | To Define | Priority |
|----------|---------|-----------|:--------:|
| 삭제 플래그 네이밍 | 없음 | RDB `deleted_at`, Qdrant/ES `is_deleted` 통일 | High |
| 검색 제외 필터 | 산발 | 공통 헬퍼(`exclude_deleted`)로 단일화 | High |
| 복구 권한 | 삭제만 존재 | restore 권한(삭제와 동일/별도) | Medium |
| 마이그레이션 | Flyway 확립 | `deleted_at` 컬럼 + 인덱스 DDL | High |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Create |
|----------|---------|-------|:---------:|
| (없음) | 기존 인프라만 사용 | - | - |

---

## 8. Implementation Order

### Phase 1: 스키마 & 마이그레이션
1. `db/migration/Vxxx__add_deleted_at_to_document_metadata.sql` (`/db-migration`)
2. `infrastructure/doc_browse/models.py` — `deleted_at` 컬럼 + 인덱스
3. ES 매핑에 `is_deleted` boolean 추가 (인덱스 템플릿/마이그레이션 스크립트)

### Phase 2: Domain
4. `domain/doc_browse/schemas.py` — `deleted_at` 필드, 삭제목록/복구 결과 VO
5. `domain/doc_browse/interfaces.py` — soft delete/restore/find_deleted 시그니처
6. `domain/doc_browse/policies.py` — 복구 권한 정책

### Phase 3: Infrastructure — 쓰기 경로 (soft mark)
7. `document_metadata_repository.py` — `delete_by_document_id`를 soft UPDATE로, `restore`/`find_deleted_by_collection` 추가
8. `qdrant_vectorstore.py` — `mark_deleted`/`mark_restored`(set_payload) 헬퍼
9. `es_repository.py` — `update_by_query` 기반 soft mark/restore

### Phase 4: Infrastructure/Application — 읽기 경로 (제외 필터)
10. 공통 제외 필터 헬퍼 정의 (Qdrant `must_not`, ES `must_not`, RDB `IS NULL`)
11. 9개 read 경로에 순차 적용 + 경로별 테스트 (감사 체크리스트)

### Phase 5: Application — UseCase
12. `delete_document_use_case.py` — soft delete로 전환
13. `restore_document_use_case.py` — 신규 복구 UseCase
14. Activity log: RESTORE_DOCUMENT 액션 추가

### Phase 6: Interface & Verification
15. `doc_browse_router.py` — 삭제목록 조회 + 복구 엔드포인트
16. e2e: 삭제 → 목록/검색 제외 → 복구 → 재등장 시나리오
17. `/verify-architecture`, `/verify-logging`, `/verify-tdd`

---

## 9. Open Questions / Follow-ups

- [ ] **프론트 휴지통 UI** — 백엔드 API 완료 후 별도 PDCA (API 계약 동기화 필요)
- [ ] **영구삭제(purge) API + retention 자동화** — 스토리지 증가 대응 후속
- [ ] **ES 매핑 변경 배포 방식** — 기존 인덱스 reindex 필요 여부 Design에서 확정
- [ ] **collection_search 경로 정확한 구현 확인** — Design 단계 코드 감사

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`/pdca design document-soft-delete`)
2. [ ] 9개 read 경로 코드 전수 감사 (Design)
3. [ ] 코드 리뷰 및 Plan 확정 후 TDD 구현 (`/pdca do`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | Initial draft | 배상규 |
