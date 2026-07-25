---
title: 미니 ERD — 지식베이스 도메인 (knowledge_base/chunking_profile/문서·검색 메타)
status: draft
source_type: conversation
source_refs:
  - idt/src/infrastructure/persistence/models/knowledge_base.py
  - idt/src/infrastructure/persistence/models/chunking_profile.py
  - idt/src/infrastructure/persistence/models/section_summary_job.py
  - idt/src/infrastructure/doc_browse/models.py
  - idt/src/infrastructure/collection_search/models.py
  - idt/db/migration/V047__alter_document_metadata_add_kb_id.sql
confidence: 0.9
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

구조는 SQLAlchemy 모델에서 도출(2026-07-21 기준). 실선=실제 FK, 점선=소프트 참조.
실제 청크/벡터는 MySQL이 아니라 ES/Qdrant에 있다 — 여기는 메타데이터 계층만.

```mermaid
erDiagram
    users ||--o{ knowledge_base : "owner_id (FK)"
    departments |o--o{ knowledge_base : "department_id (SET NULL)"
    chunking_profile |o--o{ knowledge_base : "chunking_profile_id (FK)"
    knowledge_base |o..o{ document_metadata : "kb_id (soft, V047)"
    knowledge_base |o..o{ section_summary_job : "kb_id (soft)"
    knowledge_base |o..o{ search_history : "kb_id (soft, V049)"
    llm_model |o..o| chunking_profile : "summary_llm_model_id (soft)"
    document_metadata |o..o| section_summary_job : "document_id (soft, UQ)"

    knowledge_base {
        string id PK
        bigint owner_id FK
        string scope "PERSONAL|DEPARTMENT|PUBLIC"
        string collection_name "물리 컬렉션 soft ref"
        string status "active=행 유지 soft-delete"
        bool use_clause_chunking "조항 청킹 opt-in"
        string chunking_profile_id FK
        bool use_custom_chunking "V048 독립 opt-in"
        json custom_chunking_config
    }
    chunking_profile {
        string id PK
        json boundary_rules
        int parent_chunk_size
        bool is_default
        string summary_llm_model_id "soft, NULL=요약 비활성"
        string status
    }
    section_summary_job {
        string id PK
        string document_id "UQ — 문서당 1잡"
        string kb_id
        string llm_model_id "잡 시점 스냅샷"
        string status "pending|running|done|failed"
        int done_sections
    }
    document_metadata {
        bigint id PK
        string document_id UK
        string collection_name
        string kb_id "NULL=일반 업로드"
        int chunk_count
        string chunk_strategy
    }
    search_history {
        bigint id PK
        string user_id
        string collection_name
        string kb_id "NULL=컬렉션 검색"
        float bm25_weight
        float vector_weight
    }
```

## 각주 (코드에 안 보이는 규칙)

- **`kb_id` 소프트 참조 3곳은 의도적으로 FK가 없다.** V047 주석: KB soft-delete와 독립적으로 문서 메타를 남기기 위해서다 (+ FK 시 CHARSET/COLLATE 금지 — [[mysql-fk-collation]]).
- **NULL 의미론이 계약이다**: `document_metadata.kb_id` NULL=일반(비 KB) 업로드, `search_history.kb_id` NULL=컬렉션 단위 검색. backfill은 하지 않기로 결정됨 (kb-management-ui D4).
- **`use_clause_chunking`과 `use_custom_chunking`은 상호배타**지만 DB 제약이 아니라 앱 레이어 검증(V-07)이다. 독립 bool opt-in으로 추가한 이유는 기존 enum 확장 거부 결정 때문 ([[additive-contract-extension]]).
- `chunking_profile.summary_llm_model_id`는 FK 없는 소프트 참조 — NULL이면 섹션 요약 파이프라인 자체가 비활성 (card-section-summary D2).
- `section_summary_job`은 **문서당 1행(UQ)이고 행 존재+status가 곧 요약 진행 상태**다. 재시도는 행 갱신으로 처리된다.
- KB 검색 격리는 이 테이블들이 아니라 Qdrant payload `kb_id` 필터로 실현된다 (kb-rag-filter). E2E 실측은 [[e2e-carryover-checklist]]에 이월 중.
