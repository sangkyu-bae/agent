# document-revision Design Document

> **Summary**: KB 업로드 전에 개정 여부를 판정해 제안하고 운영자가 확정하면, 새 문서를 같은 계보의 다음 버전으로 적재한 뒤 구버전 청크에 `revision_status=superseded` 표식을 남긴다. 검색 최하단(Qdrant·ES)이 이 표식을 기본으로 제외하므로 모든 검색 경로에서 구버전이 빠진다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-11-21
> **Status**: Draft
> **Planning Doc**: [document-revision.plan.md](../../01-plan/features/document-revision.plan.md)
> **Selected Architecture**: Option C — Pragmatic Balance

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 개정본 업로드 시 구·신버전 청크가 함께 검색돼 잘못된 근거가 인용된다 |
| **WHO** | P2 KB 운영자(개정 확정·이력 관리), P1/P4 최종 사용자(최신 근거만 받음), P3 관리자(판정 로그) |
| **RISK** | 오판정으로 멀쩡한 문서가 검색에서 빠짐 / 적재·전환 중간 실패로 둘 다 활성 또는 둘 다 비활성 / 검색 경로 중 필터 누락 경로 |
| **SUCCESS** | 개정 확정 후 모든 검색 경로에서 구버전 청크 0건, 동일 해시 재업로드 차단, 되돌리기 시 구버전 즉시 복귀, 개정 후보 top-1 정확도 ≥ 90%(픽스처 세트) |
| **SCOPE** | KB 업로드 경로 백엔드 + 프론트(업로드 모달·문서 목록·근거 칩). 컬렉션 직접 업로드·레거시 업로드·quick setup의 판정은 제외(단, 검색 제외 필터는 전 경로 공통 적용) |

---

## 1. Overview

### 1.1 Design Goals

1. **누락 없는 검색 제외**: superseded 문서를 호출 지점이 아니라 저장소 검색 최하단에서 기본 제외한다. 새 검색 경로가 생겨도 Qdrant·ES 하이브리드를 거치면 자동 적용된다.
2. **활성 근거 공백 금지**: 어떤 실패 순서에서도 "계보의 모든 버전이 비활성"인 상태를 만들지 않는다. 실패 시 남는 상태는 "둘 다 검색됨(기존과 동일)"뿐이며 화면에 표시하고 재시도할 수 있다.
3. **하위 호환**: 기존 문서·청크에 백필·재색인이 없다. 표식 필드가 없으면 active로 취급한다.
4. **제안과 확정 분리**: 사전 점검은 아무것도 바꾸지 않는다(판정 로그 1행만 쓴다). 상태 변경은 운영자 확정 API에서만 일어난다.
5. **자동화 대비**: 판정 신호 점수·LLM 판정·사람 결정을 한 행에 남겨, 이후 auto 모드 임계값을 실측으로 정한다.

### 1.2 Design Principles

- **MySQL이 진실**: 버전·상태의 원본은 `document_metadata`. 청크 payload의 `revision_status`는 검색 제외용 사본이며, `sync_state`로 사본 반영 여부를 추적한다.
- **멱등 연산만 사용**: 사본 반영은 Qdrant `set_payload(filter=document_id)` 1회 + ES `update_by_query(term=document_id)` 1회. 몇 번을 다시 실행해도 결과가 같다.
- **순서 고정**: 신버전 적재 성공 → MySQL 구버전 superseded(sync pending) → 청크 표식 → sync 완료. 되돌리기는 이전 버전을 먼저 다시 활성화한 뒤 취소된 버전을 분리하거나 삭제한다.
- **일반화**: 파일명 정규화 규칙과 임계값은 부서 특화 하드코딩 없이 일반 패턴과 설정값으로 둔다.
- **LLM 실패가 업로드를 막지 않는다** (`UtilityLLMProviderPort` 계약과 동일).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 업로드 유스케이스에 덧붙임, RAG 도구 lenient 필터만 | MySQL 단일 진실, 검색마다 superseded ID 목록을 포트로 조회해 `must_not` | 신규 모듈, 청크 payload 표식, 검색 최하단 기본 제외 |
| **검색 경로 커버** | RAG 도구 1곳(6곳 누락) | 하이브리드 유스케이스 경유분만 | Qdrant·ES 검색 최하단 5곳 전부 |
| **일관성** | 낮음 | 높음(원자) | 중(멱등 2회 + sync_state 재시도) |
| **검색 비용** | 0 | 검색마다 DB 조회 | 0 |
| **Complexity** | Low | High | Medium |
| **Risk** | High(누락) | Medium | Low |
| **Recommendation** | — | — | **Selected** |

**Selected**: Option C. **Rationale**: 검색 경로 전부를 한 지점에서 막고, 검색 비용과 백필이 없다. 이중 저장소 갱신 위험은 멱등 연산, 실패 시 "둘 다 검색됨" 쪽으로만 기우는 순서, `sync_state` 재시도로 다룬다.

### 2.1 Component Diagram

```
[KbUploadDocumentModal] ──(1) revision-check──▶ RevisionCheckUseCase
        │                                        ├─ FileHasher(sha256) ─ DocumentRevisionRepository.find_by_hash
        │                                        ├─ DocumentParser.parse_bytes → head text
        │                                        ├─ FilenameNormalizer + 같은 KB active 문서 파일명
        │                                        ├─ HeadSimilaritySearch(임베딩 → Qdrant kb_id 필터 → 문서별 max)
        │                                        ├─ CandidateHeadReader(ES 후보 앞 청크) ─▶ LlmRevisionJudge
        │                                        └─ RevisionCheckLogRepository.save
        │
        └──(2) upload + supersedes_document_id──▶ KnowledgeBaseUploadUseCase (수정)
                                                  ├─ 해시 중복 재검사 / 대상 검증 (적재 전)
                                                  ├─ UnifiedUploadUseCase (기존, 계보 필드 저장)
                                                  └─ SupersedeService ─▶ DocumentRevisionRepository (MySQL)
                                                                     └▶ ChunkRevisionMarker (Qdrant set_payload / ES update_by_query)

[검색 경로] RAG도구·멀티쿼리·라우티드·리트리버테스트·컬렉션검색·그래프검색테스트·하이브리드API
   └▶ HybridSearchUseCase ── ES BM25 [revision guard] / QdrantVectorStore.search_by_vector [revision guard]
   └▶ HybridSectionRouter(ES) [guard] · QdrantRetriever.query_points [guard] · EsEvidenceFetcher(Graph) [guard]
```

### 2.2 Data Flow

```
사전 점검: 파일 → sha256 → (중복이면 duplicate 반환)
          → 파싱 → 앞부분 텍스트 → 파일명 후보 ∪ 본문 유사 후보 → 결합 점수 상위 N
          → 상위 M개 LLM 판정(병렬, 타임아웃) → verdict → 판정 로그 저장 → 응답(check_id)

확정 업로드: 파일 + supersedes_document_id + check_id
          → 권한 → 해시 중복 재검사 → 대상 검증(같은 KB·active·계보 최신)
          → 적재(status=completed 여야 함; partial/failed 면 개정 미적용)
          → 신버전 행: lineage_id·version_no·label·hash
          → 구버전 행: superseded, sync_state=pending (커밋)
          → 청크 표식(Qdrant, ES) → 둘 다 성공 시 sync_state=synced
          → 판정 로그 decision=revision 갱신 → 응답.revision

검색: 모든 Qdrant/ES 검색 질의에 must_not(revision_status == "superseded")
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| RevisionCheckUseCase | DocumentParser, EmbeddingFactory, VectorStore, ES repo, UtilityLLMProviderPort, KB repo/policy | 후보 탐지·판정 |
| KnowledgeBaseUploadUseCase | SupersedeService, DocumentRevisionRepository | 확정 업로드 |
| SupersedeService | DocumentRevisionRepository, ChunkRevisionMarker | 상태 전환 + 사본 반영 |
| Rollback/Link/Meta/Sync UseCases | 위 두 컴포넌트, DeleteDocumentUseCase(삭제 모드) | 이력 관리 |
| 검색 가드 | `domain/document_revision/search_guard.py` 상수·ES 절 빌더 | 기본 제외 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/document_revision/value_objects.py
class RevisionStatus(str, Enum):   ACTIVE = "active"; SUPERSEDED = "superseded"
class SyncState(str, Enum):        SYNCED = "synced"; PENDING = "pending"
class CheckVerdict(str, Enum):     NEW = "new"; REVISION_CANDIDATE = "revision_candidate"; DUPLICATE = "duplicate"
class LlmVerdict(str, Enum):       SAME = "same_document_revision"; DIFFERENT = "different_document"; UNCERTAIN = "uncertain"
class LlmStatus(str, Enum):        OK = "ok"; FAILED = "failed"; SKIPPED = "skipped"
class RollbackMode(str, Enum):     DETACH = "detach"; DELETE = "delete"
class RevisionMode(str, Enum):     SUGGEST = "suggest"; AUTO = "auto"   # auto는 이번 사이클 저장 거부

@dataclass(frozen=True)
class DocumentVersion:
    document_id: str; kb_id: str; filename: str
    lineage_id: str            # NULL 컬럼이면 document_id 로 해석
    version_no: int; version_label: str | None; effective_date: date | None
    revision_status: RevisionStatus; sync_state: SyncState
    file_hash: str | None; superseded_by: str | None; superseded_at: datetime | None
    revised_by: str | None; created_at: datetime

@dataclass(frozen=True)
class RevisionCandidate:
    document_id: str; filename: str; version_no: int; version_label: str | None
    filename_score: float; content_score: float; combined_score: float
    llm_verdict: LlmVerdict | None; llm_reason: str | None

@dataclass(frozen=True)
class RevisionCheckResult:
    check_id: str; verdict: CheckVerdict
    duplicate_of: DocumentVersion | None
    candidates: list[RevisionCandidate]       # combined 내림차순, 최대 top_n
    suggested_document_id: str | None
    llm_status: LlmStatus; elapsed_ms: int
```

### 3.2 Entity Relationships

```
lineage (논리 개념, 테이블 없음) 1 ── N document_metadata (version_no 1..n, active는 항상 최대 1개)
knowledge_base 1 ── N document_metadata (kb_id)
knowledge_base 1 ── N document_revision_check (kb_id)
document_revision_check N ── 0..1 document_metadata (decided_document_id / target_document_id, FK 없음 — 문서 삭제 후에도 로그 보존)
```

**불변식**: 한 lineage에서 `revision_status=active`인 행은 최대 1개이며, 항상 그 lineage의 최대 version_no다(되돌리기 중 잠깐 2개가 될 수 있다. 1.2 순서 참고). 이전 버전은 포인터 대신 `(lineage, version_no < 현재)` 중 최대값으로 찾는다. `superseded_by`는 감사용으로만 쓴다.

### 3.3 Database Schema

> Flyway 번호: answer-citation-verification이 V093·V094를 점유한다. 이 기능은 **V095~V097**을 쓰며, 두 PR의 머지 순서를 확인한다(본 기능이 먼저 머지되면 번호 재조정).

```sql
-- V095__alter_document_metadata_add_revision.sql
ALTER TABLE document_metadata
  ADD COLUMN file_hash CHAR(64) NULL COMMENT '원본 파일 SHA-256 (document-revision). 기존 행 NULL',
  ADD COLUMN lineage_id VARCHAR(64) NULL COMMENT '개정 계보 ID. NULL이면 자기 document_id가 계보 ID',
  ADD COLUMN version_no INT NOT NULL DEFAULT 1 COMMENT '계보 내 버전 번호(1부터)',
  ADD COLUMN version_label VARCHAR(100) NULL COMMENT '운영자 입력 버전 라벨(예: 2026-11 개정)',
  ADD COLUMN effective_date DATE NULL COMMENT '시행일(표시용, 전환 시점에 영향 없음)',
  ADD COLUMN revision_status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active|superseded — 검색 제외 원본',
  ADD COLUMN sync_state VARCHAR(20) NOT NULL DEFAULT 'synced' COMMENT 'synced|pending — 청크 payload 표식 반영 여부',
  ADD COLUMN superseded_by VARCHAR(64) NULL COMMENT '이 문서를 대체한 document_id(감사용)',
  ADD COLUMN superseded_at DATETIME NULL COMMENT '대체 확정 시각',
  ADD COLUMN revised_by VARCHAR(128) NULL COMMENT '개정 확정·연결을 수행한 사용자 ID',
  ADD INDEX idx_dm_kb_hash (kb_id, file_hash),
  ADD INDEX idx_dm_lineage (lineage_id, version_no),
  ADD INDEX idx_dm_kb_status (kb_id, revision_status);

-- V096__alter_knowledge_base_add_revision_mode.sql
ALTER TABLE knowledge_base
  ADD COLUMN revision_mode VARCHAR(10) NOT NULL DEFAULT 'suggest' COMMENT '개정 판정 모드 suggest|auto (auto는 후속 사이클)';

-- V097__create_document_revision_check.sql
CREATE TABLE document_revision_check (
  id VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'check_id (uuid4)',
  kb_id VARCHAR(64) NOT NULL COMMENT '대상 KB',
  user_id VARCHAR(128) NOT NULL COMMENT '점검 요청자',
  source VARCHAR(20) NOT NULL COMMENT 'precheck|manual_link|rollback',
  filename VARCHAR(512) NOT NULL COMMENT '새 파일명(수동 연결·되돌리기는 대상 문서 파일명)',
  normalized_name VARCHAR(512) NULL COMMENT '정규화 파일명',
  file_hash CHAR(64) NULL COMMENT '새 파일 SHA-256',
  verdict VARCHAR(30) NOT NULL COMMENT 'new|revision_candidate|duplicate|manual',
  suggested_document_id VARCHAR(64) NULL COMMENT '시스템이 제안한 대상 document_id',
  candidates_json JSON NULL COMMENT '후보별 filename/content/combined 점수·LLM 판정·근거',
  llm_status VARCHAR(10) NOT NULL DEFAULT 'skipped' COMMENT 'ok|failed|skipped',
  elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '점검 소요(ms, 파싱 포함)',
  parse_ms INT NOT NULL DEFAULT 0 COMMENT '파싱 소요(ms) — 파싱 캐시 필요성 판단용',
  decision VARCHAR(20) NULL COMMENT 'revision|new|cancel|rollback_detach|rollback_delete — NULL은 미결정',
  target_document_id VARCHAR(64) NULL COMMENT '운영자가 확정한 대체 대상(구버전) document_id',
  decided_document_id VARCHAR(64) NULL COMMENT '결정으로 생성·변경된 문서 document_id',
  decided_by VARCHAR(128) NULL COMMENT '결정자',
  decided_at DATETIME NULL COMMENT '결정 시각',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  INDEX idx_drc_kb_created (kb_id, created_at)
) COMMENT='문서 개정 판정 로그 (document-revision FR-16)';
```

**청크 payload / ES 문서**: 필드 `revision_status`(keyword). 신규 적재 시에는 쓰지 않는다(부재 = active). 대체·되돌리기 때만 `superseded`/`active`로 갱신한다. ES 매핑 파일에 `revision_status: keyword`를 추가하고, 기존 인덱스에는 `ChunkRevisionMarker`가 첫 갱신 전에 `put_mapping`을 멱등 호출한다.

---

## 4. API Specification

### 4.1 Endpoint List

신규 라우터 `idt/src/api/routes/kb_document_revision_router.py` (prefix `/api/v1/knowledge-bases`, 기존 router 비대화 방지). 기존 엔드포인트 2개는 확장한다.

| # | Method | Path | Description | Auth |
|---|--------|------|-------------|------|
| 1 | POST | `/{kb_id}/documents/revision-check` | 사전 점검(multipart file). 상태 변경 없음 | KB 쓰기 |
| 2 | POST | `/{kb_id}/documents` (확장) | 업로드 + 선택 필드 `supersedes_document_id`·`version_label`·`effective_date`·`revision_check_id` | KB 쓰기 |
| 3 | GET | `/{kb_id}/documents` (확장) | active만 반환 + 버전 필드 | KB 읽기 |
| 4 | GET | `/{kb_id}/documents/{document_id}/versions` | 계보 전체 버전 목록 | KB 읽기 |
| 5 | POST | `/{kb_id}/documents/{document_id}/revision-rollback` | 최신 버전 개정 취소 | KB 쓰기 |
| 6 | POST | `/{kb_id}/documents/{document_id}/revision-link` | 기존 문서 간 사후 개정 연결 | KB 쓰기 |
| 7 | PATCH | `/{kb_id}/documents/{document_id}/revision-meta` | 라벨·시행일 수정 | KB 쓰기 |
| 8 | POST | `/{kb_id}/documents/{document_id}/revision-sync` | sync_state=pending 재반영 | KB 쓰기 |
| 9 | DELETE | `/{kb_id}/documents/{document_id}` (확장) | `?restore_previous=true`(기본 true) | KB 쓰기 |
| 10 | PATCH | `/{kb_id}` (확장) | `revision_mode` (auto → 422) | KB 쓰기 |

### 4.2 Detailed Specification

#### 1. `POST /{kb_id}/documents/revision-check`

Request: `multipart/form-data` — `file`

Response `200`:
```json
{
  "check_id": "8f0c…",
  "verdict": "revision_candidate",
  "duplicate_of": null,
  "suggested_document_id": "a1b2…",
  "candidates": [
    {
      "document_id": "a1b2…", "filename": "여신심사기준_2025.pdf",
      "version_no": 2, "version_label": "2025-03 개정",
      "filename_score": 0.92, "content_score": 0.88, "combined_score": 0.90,
      "llm_verdict": "same_document_revision",
      "llm_reason": "두 문서 모두 '여신심사기준' 제1조(목적) 문구가 같고 시행일만 다르다"
    }
  ],
  "llm_status": "ok",
  "elapsed_ms": 4210
}
```
`verdict=duplicate`일 때 `duplicate_of`에 기존 문서(DocumentVersion 요약)를 담는다. 프론트는 업로드 버튼을 막는다.

**verdict 결정 규칙**
1. 같은 KB에서 해시가 일치하면 `duplicate`. active와 superseded 모두 대상이다. superseded와 일치하면 "이전 버전과 동일 — 이력에서 되돌리기를 사용" 안내를 띄운다.
2. LLM이 `same_document_revision`으로 판정한 후보가 있으면 `revision_candidate`이고, 그중 combined 최대 후보를 제안한다.
3. LLM이 실패(`failed`)하고 combined ≥ `revision_suggest_min_combined`(기본 0.80)인 후보가 있으면 `revision_candidate`로 처리한다. 근거는 "LLM 판정 실패 — 점수 기준 제안"으로 표시한다.
4. 그 밖에는 `new`. 이 경우에도 후보 목록은 함께 내려 운영자가 직접 선택할 수 있게 한다.

#### 2. `POST /{kb_id}/documents` (확장)

추가 Form 필드(모두 선택): `supersedes_document_id`, `version_label`(≤100), `effective_date`(YYYY-MM-DD), `revision_check_id`.

처리 규칙:
- `supersedes_document_id`가 없어도 해시 중복이면 **409 `DUPLICATE_DOCUMENT`**를 반환한다(사전 점검 우회 방지).
- 대상 검증은 적재 전에 한다. 대상은 같은 KB이고 active이며 계보 최신이어야 한다. 어기면 **409 `REVISION_TARGET_INVALID`**(사유: `not_found`·`other_kb`·`not_active`).
- 적재 결과 `status != "completed"`이면 개정을 적용하지 않고 `revision.applied=false`, `reason="ingest_incomplete"`로 응답한다. 신규 문서는 v1 독립 문서로 남는다.
- `revision_check_id`가 있으면 판정 로그 `decision`을 갱신한다. `supersedes_document_id`가 있으면 revision, 없으면 new.

Response `201`(기존 필드 + `revision`):
```json
{
  "...기존 업로드 응답 필드...": "",
  "revision": {
    "applied": true,
    "lineage_id": "a1b2…", "version_no": 3,
    "superseded_document_id": "a1b2…",
    "sync_state": "synced",
    "reason": null
  }
}
```
`sync_state="pending"`이면 프론트가 "구버전 검색 제외 반영 중 실패 — 재시도" 배지를 띄운다.

#### 3. `GET /{kb_id}/documents` (확장)

`KbDocumentInfo`에 `version_no`, `version_label`, `effective_date`, `revision_status`, `sync_state`, `lineage_id`, `has_history`(계보 내 다른 버전 존재)를 추가한다. 기본으로 `revision_status=active`만 반환한다. 단, 이번 사이클에 superseded 문서 중 `sync_state=pending`인 것도 목록에서 볼 수 있도록 `pending_sync` 배열을 따로 내린다(재시도 대상 노출).

#### 4. `GET /{kb_id}/documents/{document_id}/versions`

`{ lineage_id, versions: DocumentVersion[] }`, version_no 내림차순. document_id는 계보의 어느 버전이어도 된다.

#### 5. `POST …/revision-rollback`

Request `{ "mode": "detach" | "delete" }`. 대상은 active이면서 version_no > 1이고, 이전 버전이 있어야 한다. 아니면 409 `ROLLBACK_NOT_ALLOWED`.
순서는 다음과 같다. ① 이전 버전을 active로 바꾸고 청크 표식을 active로 되돌린다. ② 현재 버전을 처리한다. detach면 lineage_id=NULL, version_no=1, revision 필드를 초기화한다. delete면 기존 `DeleteDocumentUseCase.delete_verified`로 지운다. ③ 판정 로그에 `source=rollback` 행을 남긴다.
Response `{ restored_document_id, detached_document_id | deleted_document_id, sync_state }`.

#### 6. `POST …/{document_id}/revision-link`

Request `{ "supersedes_document_id": "…" }`. `{document_id}`가 신버전이다. 조건은 둘 다 같은 KB의 active여야 하고, 서로 달라야 하며, 신버전은 계보가 없는 독립 문서여야 한다(lineage_id NULL이고 다른 버전 없음). 대상은 계보 최신이어야 한다. 실패 시 409 `REVISION_LINK_INVALID`. 처리는 SupersedeService를 재사용하고, 신버전은 대상 계보의 다음 version_no를 받는다. 판정 로그에 `source=manual_link, verdict=manual`로 남긴다.

#### 7. `PATCH …/revision-meta`

`{ version_label?: string|null, effective_date?: string|null }` → 갱신된 DocumentVersion. 검색에는 영향이 없다.

#### 8. `POST …/revision-sync`

MySQL `revision_status`를 기준으로 청크 표식을 다시 반영한다(멱등). 성공하면 `sync_state=synced`. 반환 `{ document_id, revision_status, sync_state }`.

#### 9. `DELETE /{kb_id}/documents/{document_id}?restore_previous=true`

active 최신 버전이고 이전 버전이 있으며 `restore_previous=true`이면, 이전 버전을 먼저 active로 바꾼 뒤 삭제한다. false이면 계보의 다른 버전은 superseded로 남는다(계보가 검색에서 사라진다). 프론트 확인 다이얼로그에서 이 점을 명시한다. superseded(이전 버전)를 삭제하면 이력 항목만 없어진다.

#### 10. `PATCH /{kb_id}` (확장)

`revision_mode`: `suggest`만 허용한다. `auto`는 422 `REVISION_MODE_NOT_AVAILABLE`.

---

## 5. UI/UX Design

### 5.1 Screen Layout

**업로드 모달 (KbUploadDocumentModal, 단계형)**
```
┌ 문서 업로드 ─────────────────────────────────┐
│ [파일 선택] 여신심사기준_2026.pdf              │
│ ── 개정 여부 확인 중… (ProgressCard) ──        │
│ ┌ 결과 ────────────────────────────────────┐ │
│ │ ⓘ 기존 「여신심사기준_2025.pdf」 v2 의      │ │
│ │   개정본으로 보입니다                        │ │
│ │   근거: 제1조(목적) 문구 동일, 시행일만 다름 │ │
│ │   파일명 92% · 본문 88%                     │ │
│ │ ○ 이 문서의 개정본으로 올리기 (v3)          │ │
│ │ ○ 다른 문서의 개정본으로 올리기 [후보 ▾]    │ │
│ │ ○ 새 문서로 올리기                          │ │
│ │ 버전 라벨 [2026-11 개정   ] 시행일 [날짜]   │ │
│ └──────────────────────────────────────────┘ │
│              [취소]  [올리기]                  │
└──────────────────────────────────────────────┘
duplicate: "이미 같은 파일이 있습니다 — 「…」(업로드일)" + 올리기 비활성
new: 결과 영역에 "기존 문서와 일치하는 개정 대상이 없습니다" + (후보 있으면) "개정본으로 지정" 펼침
```

**문서 목록 (KbDocumentTable)**
```
파일명                          | 버전          | 청크 | 청킹 | 업로드일 | 검색 | 관리
여신심사기준_2026.pdf  [v3 · 2026-11 개정] [이력 ▸] | 120 | ... | ... | ⋯ (이력·되돌리기·대체한 문서 지정·라벨 수정·삭제)
  └ (펼침) v2 2025-03 개정 · 2025-03-02 · 홍길동 · 대체됨
           v1 —            · 2024-01-10 ·        · 대체됨
⚠ 구버전 검색 제외 반영 실패 [재시도]   (sync_pending 배너)
```

### 5.2 User Flow

```
파일 선택 → 사전 점검(자동) → [duplicate] 차단 안내 → 다른 파일 선택
                           → [candidate] 개정 확정(기본 선택) / 다른 대상 / 새 문서 → 올리기 → 목록 갱신(v배지)
                           → [new] 올리기
목록 → 이력 펼침 → 되돌리기(분리/삭제 선택 다이얼로그) → 이전 버전 복귀
목록 → ⋯ → 대체한 문서 지정(모달: 같은 KB active 문서 선택) → 연결
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `KbUploadDocumentModal` (수정) | `components/knowledge-base/` | 파일 선택→점검→결정→업로드 단계 |
| `RevisionCheckResult` (신규) | `components/knowledge-base/` | verdict별 안내·후보·선택 라디오·라벨/시행일 입력 |
| `KbDocumentTable` (수정) | `components/knowledge-base/` | 버전 배지, 이력 펼침, 행 메뉴, pending 배너 |
| `DocumentVersionHistory` (신규) | `components/knowledge-base/` | 계보 버전 목록 |
| `RevisionRollbackDialog` (신규) | `components/knowledge-base/` | detach/delete 선택 |
| `RevisionLinkModal` (신규) | `components/knowledge-base/` | 대체 대상 선택 |
| `RevisionMetaDialog` (신규) | `components/knowledge-base/` | 라벨·시행일 수정 |
| 삭제 확인 다이얼로그(수정) | 기존 위치 | `restore_previous` 체크박스 + 문구 |
| `ProgressCard` (재사용) | `components/common/` | 점검 진행 표시 (공통 카드 재사용 규칙) |

### 5.4 Page UI Checklist

#### KnowledgeBaseDetailPage — 업로드 모달
- [ ] 파일 선택 직후 점검 진행 표시(ProgressCard)
- [ ] duplicate: 기존 문서 파일명·업로드일 표시, 올리기 비활성
- [ ] revision_candidate: 제안 대상 파일명·버전, LLM 근거 문장, 파일명/본문 점수(%)
- [ ] 라디오 3종(제안 대상 개정 / 다른 후보 개정 / 새 문서), 기본값=제안 대상
- [ ] llm_status=failed: "자동 판정을 하지 못해 점수로 제안" 안내
- [ ] 버전 라벨 입력(≤100자), 시행일 date input
- [ ] 업로드 응답 revision.sync_state=pending → 경고 토스트
- [ ] 점검 API 실패 시 "점검 없이 새 문서로 올리기" 허용

#### KnowledgeBaseDetailPage — 문서 목록
- [ ] 버전 배지 `v{n}` + 라벨
- [ ] has_history=true 행에 이력 토글, 펼치면 버전·라벨·시행일·업로드일·확정자·상태
- [ ] 행 메뉴: 이력 / 되돌리기(v>1일 때만) / 대체한 문서 지정(독립 문서일 때만) / 라벨 수정 / 삭제
- [ ] pending_sync 배너 + 재시도 버튼
- [ ] 삭제 확인: 이전 버전 있으면 "이전 버전(v2)을 다시 검색에 사용" 체크박스(기본 체크)

#### 답변 근거 칩 / 원문 뷰어
- [ ] 라벨이 `파일명 · v3 (2026-11 개정)` 형식

---

## 6. Error Handling

### 6.1 Error Code Definition

| HTTP | Code | Cause | Handling |
|------|------|-------|----------|
| 409 | `DUPLICATE_DOCUMENT` | 같은 KB에 해시 일치 문서 | 기존 문서 정보와 함께 안내, 업로드 차단 |
| 409 | `REVISION_TARGET_INVALID` | 대상이 없음·다른 KB·비활성·계보 최신 아님 | 모달에서 대상 재선택 |
| 409 | `ROLLBACK_NOT_ALLOWED` | v1이거나 비활성이거나 이전 버전 없음 | 메뉴 비노출로 예방, 응답 시 토스트 |
| 409 | `REVISION_LINK_INVALID` | 연결 조건 위반 | 사유 표시 |
| 409 | `SUMMARY_JOB_RUNNING` | (기존) 요약 잡 진행 중 삭제·되돌리기(delete) | 기존 처리 재사용 |
| 422 | `REVISION_MODE_NOT_AVAILABLE` | auto 저장 시도 | 설정 UI는 suggest 고정 |
| 403 | (기존) | KB 쓰기 권한 없음 | 기존 |
| 200 | `revision.applied=false` | 적재 partial/failed | 신규 v1로 남았음을 안내 |
| 200 | `sync_state=pending` | 청크 표식 실패 | 재시도 배지 |

### 6.2 Error Response Format

기존 KB 라우터의 오류 형식(`HTTPException(detail=...)`)을 따른다. 409 상세는 `{"code": "...", "message": "...", "document": {...}?}`.

---

## 7. Security Considerations

- [ ] 모든 쓰기 API: `KnowledgeBasePolicy.can_write`. 읽기(versions·목록)는 기존 KB 읽기 정책
- [ ] 후보 탐색·해시 조회는 **같은 kb_id로 제한**(다른 KB 문서 파일명 노출 금지). 본문 유사도 검색은 `kb_id` hard filter
- [ ] `supersedes_document_id`·link 대상의 kb_id를 서버에서 재확인(IDOR 방지)
- [ ] LLM 입력은 두 문서 앞부분(설정 길이)만 사용. PII 마스킹 설정이 켜져 있으면 기존 마스킹 경로를 따른다(Do에서 utility LLM 호출 경로의 마스킹 적용 여부 확인)
- [ ] 업로드 파일 크기 제한은 기존 업로드와 동일하게 적용

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | 파일명 정규화, 결합 점수·verdict 규칙, 정책(대상 검증·다음 버전·되돌리기·연결 조건) | pytest | Do |
| Unit | 유스케이스(포트 목) — 순서·실패 분기 | pytest | Do |
| Integration | Qdrant 가드(실 클라이언트 in-memory/로컬), ES 절 빌더, 리포지토리(SQLite/MySQL 테스트 DB) | pytest | Do |
| Contract | 검색 가드 커버리지(지정 5개 파일에 가드 호출 존재) — AST/소스 검사 | pytest | Do |
| Migration | DDL COMMENT 규칙 | 기존 테스트 | Do |
| Frontend | 모달 단계·목록 메뉴·다이얼로그 | Vitest + RTL + MSW | Do |
| L1 | API | curl / TestClient | Check |
| L3 | 업로드→개정→검색→되돌리기 | 실서버 + 브라우저 | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Test | Expected |
|---|----------|------|----------|
| 1 | revision-check | 동일 파일 재점검 | 200, verdict=duplicate, duplicate_of 채움 |
| 2 | revision-check | 파일명 다른 개정본 | 200, revision_candidate, suggested=구버전 |
| 3 | revision-check | 무관 문서 | 200, new |
| 4 | revision-check | LLM 실패 주입 | 200, llm_status=failed, 점수 기준 제안 |
| 5 | upload | 동일 파일(점검 없이) | 409 DUPLICATE_DOCUMENT |
| 6 | upload | 다른 KB 문서를 대상으로 | 409 REVISION_TARGET_INVALID |
| 7 | upload | 정상 개정 | 201, revision.applied, version_no=2, sync synced |
| 8 | upload | 이미 superseded 대상 | 409 |
| 9 | rollback | v2 detach | 200, v1 active, v2 독립 v1 |
| 10 | rollback | v1 대상 | 409 ROLLBACK_NOT_ALLOWED |
| 11 | link | 독립 두 문서 연결 | 200, 대상 superseded |
| 12 | sync | 표식 실패 후 재시도 | 200, synced |
| 13 | 권한 | 쓰기 권한 없는 사용자 점검 | 403 |
| 14 | KB PATCH | revision_mode=auto | 422 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|----------------|
| 1 | KB 상세 | 파일 선택 | 점검 진행 → 결과 패널 |
| 2 | KB 상세 | duplicate 결과 | 올리기 비활성 |
| 3 | KB 상세 | 개정으로 올리기 | 목록에 v2 배지 |
| 4 | KB 상세 | 이력 펼치기 | v1 대체됨 행 |
| 5 | KB 상세 | 되돌리기(분리) | v1 복귀, 분리 문서 별도 행 |
| 6 | KB 상세 | pending 배너 재시도 | 배너 사라짐 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 개정 후 근거 (SC-1) | v1 업로드 → 리트리버 테스트에서 v1 조문 확인 → 개정본 확정 업로드 → 같은 질의 | v1 청크 0건, v2 청크만. RAG 에이전트 답변 근거 칩도 v2 |
| 2 | 되돌리기 (SC-4) | 1 이후 되돌리기(분리) → 같은 질의 | v1 복귀(분리된 v2는 독립 문서로 함께 검색됨 — 안내 문구 확인) |
| 3 | Graph RAG 보조 검색 | 그래프 on KB에서 1 수행 | 보조 검색 근거에 v1 청크 없음 |
| 4 | 화면 폐루프 (SC-8) | 업로드→개정→검색→되돌리기 | DB/Swagger 조작 0 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| 개정 쌍 픽스처 | 10쌍 | 동일 파일명 개정 3, 파일명 변경 개정 3, 무관 문서 3, 완전 동일 1. PDF 위주 + HWP 1 + 엑셀 1. 커밋 가능한 공개 샘플 또는 합성 문서만 사용 |
| 평가 스크립트 | 1 | `idt/scripts/eval_revision_candidates.py` — top-1 정확도·오제안율 (SC-3) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Interfaces | 라우터·요청/응답 스키마 | `src/api/routes/kb_document_revision_router.py`, `src/interfaces/schemas/document_revision.py` (+ 기존 KB 스키마 확장) |
| Application | 유스케이스·조율 | `src/application/document_revision/` |
| Domain | VO·정책·정규화·포트·검색 가드 상수 | `src/domain/document_revision/` |
| Infrastructure | MySQL 리포지토리·LLM 판정·유사도 검색·청크 표식·검색 가드 적용 | `src/infrastructure/document_revision/` + 기존 검색 어댑터 수정 |

### 9.2 Dependency Rules

`api → application → domain ← infrastructure`. 검색 가드의 ES 절 빌더는 순수 dict 함수로 domain(`search_guard.py`)에 둔다. application 계층의 `HybridSearchUseCase`가 이미 ES 질의 dict를 직접 만들고 있어 이 위치가 필요하다. Qdrant `FieldCondition` 생성은 infrastructure에 둔다.

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `RevisionStatus` 등 VO, `DocumentVersion`, `RevisionCandidate` | Domain | `domain/document_revision/value_objects.py` |
| `normalize_filename`, `filename_similarity` | Domain | `domain/document_revision/filename_normalizer.py` |
| `RevisionPolicy`(대상 검증·다음 버전·되돌리기·연결 조건·verdict 결정·결합 점수) | Domain | `domain/document_revision/policy.py` |
| 포트: `DocumentRevisionRepositoryPort`, `RevisionCheckLogRepositoryPort`, `ChunkRevisionMarkerPort`, `RevisionJudgePort`, `HeadSimilaritySearchPort`, `CandidateHeadReaderPort` | Domain | `domain/document_revision/interfaces.py` |
| `REVISION_STATUS_FIELD`, `SUPERSEDED`, `es_revision_guard_clause()` | Domain | `domain/document_revision/search_guard.py` |
| `RevisionCheckUseCase`, `SupersedeService`, `RollbackRevisionUseCase`, `LinkRevisionUseCase`, `DocumentVersionsUseCase`, `UpdateRevisionMetaUseCase`, `RetryRevisionSyncUseCase` | Application | `application/document_revision/` |
| `KnowledgeBaseUploadUseCase`(수정), KB 문서 목록·삭제 유스케이스(수정) | Application | `application/knowledge_base/` |
| `DocumentRevisionRepository`, `RevisionCheckLogRepository`(+ 모델) | Infrastructure | `infrastructure/document_revision/` |
| `QdrantEsChunkRevisionMarker` | Infrastructure | `infrastructure/document_revision/chunk_revision_marker.py` |
| `LlmRevisionJudge` | Infrastructure | `infrastructure/document_revision/llm_revision_judge.py` |
| `QdrantHeadSimilaritySearch`, `EsCandidateHeadReader` | Infrastructure | `infrastructure/document_revision/` |
| 검색 가드 적용 | Infrastructure/Application | 아래 §9.5 |

### 9.5 검색 가드 적용 지점 (계약 테스트 대상)

| # | File | 적용 |
|---|------|------|
| G1 | `infrastructure/vector/qdrant_vectorstore.py` `search_by_vector` | `_apply_revision_guard`를 **요약 가드와 별도로** 항상 적용. 요약 가드는 요약 타입 요청 시 early-return하므로 같은 함수에 넣으면 라우티드 요약 검색에서 가드가 빠진다 |
| G2 | `infrastructure/retriever/qdrant_retriever.py` `query_points` + `retrieve_by_metadata`의 `scroll` | `must_not` 추가 (Do에서 scroll 경로도 포함) |
| G3 | `application/hybrid_search/use_case.py` BM25 질의 | 항상 `bool.must_not`(=`es_revision_guard_clause()`) 포함. 필터가 없을 때도 bool로 감싼다 |
| G4 | `infrastructure/routed_retrieval/hybrid_section_router.py` ES 질의 | 동일 |
| G5 | `infrastructure/graph_rag/es_evidence_fetcher.py` `build_filters` | 동일 |

**가드 제외(의도)**: `browse_sources`(문서 단위 콘텐츠 브라우저, 구버전 열람 허용), `doc_browse/get_chunks_use_case`(문서 단위 청크 조회), `es_chunk_reader`(그래프 추출 입력), `es_chunk_expander`(라우팅이 이미 고른 문서 안 확장), `parent_child_retriever`(가드된 child 히트의 parent 조회), `section_summary/qdrant_section_source`(요약 생성용 문서 지정 조회), `wiki_source_provider`(KB 문서 아님), `rag_tool_router`(메타데이터 키 샘플링), `delete_by_metadata`(삭제).
계약 테스트 `tests/contracts/test_revision_search_guard_coverage.py`는 G1~G5 각 파일에 가드 호출이 있는지 확인한다. 또 `src/`(domain 제외) 전체에서 `ESSearchQuery(`·`.query_points(`·`.scroll(`을 호출하는 파일 목록이 "적용 + 의도 제외" 목록과 정확히 일치하는지 검사한다. 이렇게 하면 새 검색 경로가 생길 때 테스트가 실패해 가드 적용 여부를 결정하게 만든다. `search_by_vector` 호출자는 G1이 최하단에서 가드하므로 대상에서 뺀다(Do에서 확정).

---

## 10. Coding Convention Reference

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 설정값 | `src/config.py` Settings: `revision_head_chars=2000`, `revision_candidate_top_n=3`, `revision_llm_top_m=2`, `revision_filename_min=0.6`, `revision_content_min=0.75`, `revision_weight_filename=0.4`, `revision_weight_content=0.6`, `revision_suggest_min_combined=0.80`, `revision_llm_timeout_s=8` |
| 로깅 | LOG-001: request_id, kb_id, check_id, elapsed_ms/parse_ms, llm_status. 예외는 `exception=` 로 |
| DI | `main.py` 단일 등록 |
| 주석 | `# Design Ref: document-revision §x.y — …` |
| 프론트 상수 | 엔드포인트는 `src/constants/api.ts`, 상수 union은 `src/types/*.ts` (`as const`) |
| MSW | 업로드 핸들러에서 `request.formData()` 사용 금지(기존 함정) |
| 파일명 정규화 규칙 | 확장자, 괄호 안 `개정·수정·최종·final·v\d+·ver\d+·rev\d+·\d+`, 날짜(`\d{4}[-._]?\d{2}([-._]?\d{2})?`, `\d{6,8}`), 꼬리 `_\d+`, `(\d+)`, 구분자(`_ - . 공백`) 정리, 소문자화. 부서 특화 단어 금지 |

### 10.5 알고리즘 상세

**본문 유사 후보 (`QdrantHeadSimilaritySearch`)**: 앞부분 텍스트를 `revision_head_chars`에서 3토막으로 나눈다. 각 토막을 해당 컬렉션의 임베딩 모델로 임베딩한다(`UnifiedUploadUseCase._resolve_embedding_model`과 같은 해석 경로를 쓰고, 공용 헬퍼로 뺀다). 이를 `search_by_vector(top_k=30, filter kb_id + chunk_type=child)`로 찾는다. 이 경로에도 가드가 적용돼 superseded는 자동으로 빠진다. 결과를 document_id별로 모아 토막별 최고 점수의 평균을 `content_score`로 쓴다.

**파일명 점수**: 정규화 결과가 같으면 1.0, 다르면 `difflib.SequenceMatcher.ratio`.

**후보 집합**: 같은 KB active 문서 중 `filename_score ≥ filename_min` ∪ `content_score ≥ content_min`. 후보마다 두 점수를 모두 계산하고 없는 쪽은 0으로 둔다. `combined = wf·filename + wc·content`, 상위 `top_n`.

**LLM 판정 (`LlmRevisionJudge`)**: 상위 `top_m` 후보에 병렬로 호출하고 각각 `revision_llm_timeout_s`로 끊는다. 입력은 새 파일명·앞부분 1500자와 후보 파일명·앞 청크(ES, `document_id`, `chunk_type=child`, `chunk_index` 오름차순, 1500자)다. 출력은 `with_structured_output` `{verdict, reason(≤200자), confidence}`. `UtilityLLMProviderPort.get()`이 None이면 `skipped`, 예외나 타임아웃이면 `failed`.

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  db/migration/V095__alter_document_metadata_add_revision.sql
  db/migration/V096__alter_knowledge_base_add_revision_mode.sql
  db/migration/V097__create_document_revision_check.sql
  src/domain/document_revision/{__init__,value_objects,filename_normalizer,policy,interfaces,search_guard}.py
  src/application/document_revision/{__init__,revision_check_use_case,supersede_service,rollback_use_case,link_use_case,versions_use_case,meta_use_case,retry_sync_use_case,schemas}.py
  src/infrastructure/document_revision/{__init__,models,revision_repository,check_log_repository,chunk_revision_marker,llm_revision_judge,head_similarity_search,candidate_head_reader,qdrant_guard}.py
  src/api/routes/kb_document_revision_router.py
  src/interfaces/schemas/document_revision.py
  (수정) src/infrastructure/doc_browse/models.py, document_metadata_repository.py, src/domain/doc_browse/schemas.py
  (수정) src/application/unified_upload/{schemas,use_case}.py — 계보 필드·해시 저장
  (수정) src/application/knowledge_base/{upload_use_case,delete_document_use_case}.py, KB 목록/수정 유스케이스
  (수정) src/infrastructure/persistence/models/knowledge_base.py (+ 도메인 엔티티·스키마)
  (수정) 검색 가드 G1~G5, src/infrastructure/elasticsearch/es_index_mappings.py
  (수정) src/application/agent_run/run_sources.py, src/domain/agent_run/source_policy.py, src/application/source_viewer/enricher.py
  (수정) src/api/routes/knowledge_base_router.py (업로드 Form·목록·삭제·PATCH), src/main.py (DI), src/config.py
  tests/... (각 모듈 대응 + tests/contract/test_revision_search_guard_coverage.py)
  scripts/eval_revision_candidates.py
idt_front/src/
  types/knowledgeBase.ts (+ revision 타입), constants/api.ts
  services/knowledgeBaseService.ts, hooks/useKnowledgeBases.ts (또는 hooks/useDocumentRevision.ts)
  components/knowledge-base/{KbUploadDocumentModal,RevisionCheckResult,KbDocumentTable,DocumentVersionHistory,RevisionRollbackDialog,RevisionLinkModal,RevisionMetaDialog}.tsx
  components/chat/SourceCitation.tsx · components/sourceViewer/* (라벨이 프론트 조립이면 수정)
  __tests__ / mocks (MSW 핸들러)
```

### 11.2 Implementation Order

1. [ ] 마이그레이션 3종 + 모델·도메인 스키마 확장 + DDL COMMENT 테스트
2. [ ] 도메인: VO, 정규화(경계 테스트 다수), 정책, 포트, 검색 가드 상수
3. [ ] 검색 가드 G1~G5 + ES 매핑 + 계약 테스트 → **기존 검색 회귀 0 확인**(필드 부재 = 통과)
4. [ ] 리포지토리(revision·check log) + ChunkRevisionMarker(Qdrant set_payload, ES update_by_query, put_mapping)
5. [ ] SupersedeService(순서·실패 분기) → 업로드 유스케이스 통합(해시·대상 검증·적재 후 전환)
6. [ ] RevisionCheckUseCase + 유사도·헤드 리더·LLM 판정 어댑터 + 점검 엔드포인트
7. [ ] 이력·되돌리기·연결·메타·sync·삭제 확장·KB PATCH 엔드포인트
8. [ ] 근거 칩·원문 뷰어 버전 라벨
9. [ ] 프론트 타입·서비스·훅·MSW → 업로드 모달 → 문서 목록·다이얼로그
10. [ ] 픽스처·평가 스크립트로 SC-3 측정, L3 실서버 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 데이터 모델·도메인 | `module-1` | V095~V097, 모델·스키마 확장, VO·정규화·정책·포트·가드 상수 | 20-30 |
| 검색 가드 | `module-2` | G1~G5, ES 매핑, 계약 테스트, 기존 검색 회귀 | 15-25 |
| 상태 전환 | `module-3` | 리포지토리, ChunkRevisionMarker, SupersedeService, 업로드 유스케이스 통합(해시 409·대상 검증) | 25-35 |
| 사전 점검 | `module-4` | RevisionCheckUseCase, 유사도·헤드·LLM 어댑터, 판정 로그, 점검 엔드포인트, 설정 | 25-35 |
| 이력 관리 API | `module-5` | versions·rollback·link·meta·sync, 삭제 restore_previous, KB revision_mode, 목록 확장 | 25-35 |
| 인용 라벨 | `module-6` | run_sources·source_policy·enricher 버전 라벨 | 10-15 |
| 프론트 기반 | `module-7` | 타입·상수·서비스·훅·MSW | 15-20 |
| 업로드 모달 | `module-8` | 단계형 모달, RevisionCheckResult | 20-25 |
| 문서 목록 | `module-9` | 배지·이력·되돌리기·연결·메타·pending 배너·삭제 다이얼로그 | 25-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` | 40-50 |
| Session 2 | Do | `--scope module-3` | 30-35 |
| Session 3 | Do | `--scope module-4` | 30-35 |
| Session 4 | Do | `--scope module-5,module-6` | 35-45 |
| Session 5 | Do | `--scope module-7,module-8` | 35-45 |
| Session 6 | Do | `--scope module-9` | 25-30 |
| Session 7 | Check + Report | 전체 | 30-40 |

---

## 12. Plan 대비 조정 사항

| Plan 항목 | Design 결정 | 이유 |
|-----------|-------------|------|
| NFR 성능 "사전 점검 p95 ≤ 10초" | 파싱 시간을 따로 기록한다(`parse_ms`). **파싱 제외 p95 ≤ 10초**를 기준으로 하고, 파싱 캐시는 실측 후 후속 사이클로 미룬다 | Option C 선택(파싱 2회 허용). 대용량 PDF 파싱 시간은 기능이 통제할 수 없다 |
| FR-10 목록 기본 active만 | `pending_sync` 배열 별도 제공 | 실패한 구버전 전환을 운영자가 볼 수 있어야 함 |
| FR-15 auto | PATCH 시 422 | "저장 불가" 쪽을 택해 오해 방지 |
| FR-19 삭제 | `restore_previous` 기본 true | 근거 공백 방지가 기본 |
| 기존 문서 해시 | NULL 유지(백필 없음). 레거시 동일 파일은 파일명·본문 점수로 후보에 잡힘 | 하위 호환 원칙 |

### 12.1 Do 단계 확정 사항 (module-3, 2026-11-23)

| 항목 | 결정 | 이유 |
|------|------|------|
| 업로드 유스케이스 진입점 | `execute_with_revision()` 신설 → `KbUploadOutcome`. 기존 `execute()` 3-tuple 은 위임으로 유지 | quick create·기존 테스트 계약 보존 |
| 업로드 엔드포인트 확장 | module-5 가 아니라 module-3 에서 Form 4필드·409·`revision` 응답까지 반영 | 개정 업로드를 서버 단독으로 검증 가능하게 |
| 해시 중복 | 같은 KB의 active·superseded 모두 대상, active 일치를 우선 안내 | §4.2 verdict 규칙 1 |
| 적재 미완료(partial/failed) | 신규 행은 `assign_lineage(None, 1)` 로 계보에서 분리 | 같은 계보에 active 2개 방지 |
| 트랜잭션 경계 | MySQL 은 요청 종료 시 커밋, 청크 표식은 즉시 반영. 요청이 표식 뒤에 실패하면 MySQL 만 롤백될 수 있음 → 구버전은 검색 제외·신버전은 검색됨(근거 공백 없음). 불일치는 module-5 `revision-sync` 로 정정 | 세션 규칙(요청 1건 = 트랜잭션 1건) 유지 |
| ES 매핑 | `QdrantEsChunkRevisionMarker` 가 인덱스당 1회 `put_mapping`(실패해도 갱신 진행). 동적 text 매핑이어도 소문자 단일 토큰이라 term 가드 동작 | 기존 인덱스 재생성 없이 적용 |

### 12.2 Do 단계 확정 사항 (module-4, 2026-11-23)

| 항목 | 결정 | 이유 |
|------|------|------|
| 본문 유사도 필터 | `kb_id` 만 (chunk_type 필터 없음). 요약은 요약 가드, superseded 는 개정 가드가 뺀다 | 청킹 전략별 chunk_type 이 달라(clause·excel 등) child 고정 시 후보 누락 |
| 앞부분 토막 | 3토막, 토막이 20자 미만이 되면 나누지 않음 | 짧은 문서에서 한두 글자 토막 임베딩 방지 |
| 임베딩 해석 | `CollectionHeadEmbedder`(infra) 가 업로드와 같은 규칙(컬렉션 CREATE 로그 → 모델 레지스트리)으로 해석. UnifiedUploadUseCase 리팩터링은 하지 않음 | 업로드 경로 회귀 위험 회피, 중복 20줄 수준 |
| 후보 앞부분 | parent 청크가 있으면 parent 만, chunk_index 순 이어 붙임. 계약 테스트 EXEMPT 등록 | child 는 parent 부분 텍스트라 중복 |
| 파싱 | `asyncio.to_thread` 로 이벤트 루프 밖에서 실행, `parse_ms` 로그 | 대용량 PDF 동기 파싱이 서버를 막지 않게 |
| llm_status 집계 | 하나라도 실패 → failed, 아니면 하나라도 판정 → ok, 그 외 skipped | 실패가 섞이면 점수 폴백 규칙이 적용되도록 |
| DI | `create_revision_check_factory(unified_upload_factory)` — 업로드와 같은 파서·임베딩 팩토리·ES 저장소를 `components` 로 공유 | 파서 구성 중복 방지 |

### 12.3 Do 단계 확정 사항 (module-5·6, 2026-11-23)

| 항목 | 결정 | 이유 |
|------|------|------|
| 유스케이스 구성 | #4~#8 을 `RevisionManagementUseCase` 한 클래스로 (KbDocumentGuard 로 KB 소속·읽기 검증 + can_write) | DI 1개, 가드 규칙 공유 |
| 되돌리기 delete | `DeleteKbDocumentUseCase` 를 `check()`(가드·삭제 권한·요약 잡) / `delete_checked()` 로 분리. check 실패 시 상태 변경 없음 | 이전 버전을 복귀시킨 뒤 삭제가 막혀 두 버전이 모두 활성으로 남는 경우 방지 |
| 삭제 restore_previous | 유스케이스 기본 False(직접 호출 하위 호환), API 기본 True. 응답 `restored_document_id` | 근거 공백 방지가 사용자 경로 기본 |
| 목록 | `find_by_kb_id(active_only=True)` 는 KB 문서 목록만 사용(그래프 잡 목록 등 다른 호출부는 기존 동작). `has_history = lineage_id 존재` | 활성 최신본은 v2+ 일 때만 계보 소속 |
| revision_mode API | `PATCH /{kb_id}/revision-mode` (기존에 범용 PATCH `/{kb_id}` 가 없어 `/chunking` 과 같은 하위 경로 방식). 권한은 청킹 설정과 같은 can_manage_settings | 기존 KB 설정 API 관례 |
| 인용 라벨 | `find_version_labels` → `RunEvidence.version_labels`. 라벨 `파일명 · v3 (라벨)`, v1·라벨 없음은 그대로. 칩 중복 제거 키 = 파일명+버전 | 원문 뷰어는 칩 라벨을 그대로 써 별도 수정 없음 |

### 12.4 Do 단계 확정 사항 (module-7·8 프론트, 2026-11-23)

| 항목 | 결정 | 이유 |
|------|------|------|
| 훅 위치 | 개정 훅은 `hooks/useDocumentRevision.ts`, 업로드·삭제는 기존 `useKnowledgeBases.ts` 확장 | 기존 훅 소비자 영향 최소 |
| 업로드 훅 입력 | `useUploadKbDocument` mutate 인자를 `{file, revision?}` 로 변경(호출부는 모달 1곳). 서비스 `uploadKbDocument(kbId, file, revision?)` 는 3번째 인자 선택이라 quick setup 무변경 | 하위 호환 |
| 삭제 훅 | 입력 `string | {documentId, restorePrevious}` — 기존 문자열 호출 유지, 서비스는 옵션 없으면 쿼리 생략(서버 기본 true) | module-9 삭제 다이얼로그 대비 |
| 결정 로직 | `components/knowledge-base/revisionDecision.ts` 순수 함수(initialDecision·toUploadOptions·canUpload) | 컴포넌트 파일 런타임 export 금지 규칙 |
| 목록 타입 | `KbDocumentInfo` 의 버전 필드는 선택(미존재 = v1·active) | 기존 픽스처·이전 응답 호환 |
| 모달 | 파일 선택 즉시 점검. 점검 실패는 경고 후 새 문서 업로드 허용. 업로드 409 `REVISION_TARGET_INVALID` 는 "다시 점검" 버튼 | Plan SC-7, §6.1 |
| revision_mode UI | 서비스 메서드만 추가, 화면은 만들지 않음 | auto 가 422 인 동안 설정 화면 불필요(YAGNI) |

### 12.5 Do 단계 확정 사항 (module-9 문서 목록, 2026-11-23)

| 항목 | 결정 | 이유 |
|------|------|------|
| 행 메뉴 | ⋯ 드롭다운 대신 관리 열의 아이콘 버튼(되돌리기 v2+·대체한 문서 지정 lineage 없음·라벨 수정·삭제). 콜백을 넘길 때만 렌더 | 기존 삭제 아이콘 패턴과 일치, 기존 테이블 테스트 무변경 |
| 버전 열 | 모든 행에 `v{n}`(라벨 있으면 `v{n} · 라벨`) 배지, v2+ 는 brand 톤. 이력 토글은 `has_history` 행만, 펼침 행에서 `DocumentVersionHistory` 조회 | §5.1 |
| 삭제 확인 | 대상이 v2+ 면 "이전 버전(vN)을 다시 검색에 사용" 체크(기본 켬), 끄면 "모든 버전이 검색에서 빠집니다" 경고 | §4.2 #9 |
| 오류 문구 | `revisionErrors.ts` 가 409 `detail.reason` 을 한국어 문장으로 변환 | 서버 reason 은 코드값 |
| 연결 후보 | 현재 목록 페이지(최대 20건)의 활성 문서. 페이지 밖 문서는 목록을 넘겨 지정 | 별도 검색 API 없이 시작(후속 개선 후보) |

### 12.6 Check·Act-1 확정 사항 (2026-11-23, analysis 참조)

| 항목 | 결정 | 근거 |
|------|------|------|
| 본문 임계값 (C1) | `revision_content_min` 기본 **0.75 → 0.5**. §10.4 표의 값도 이것으로 대체 | 합성 평가: 개정 쌍 0.65~0.70, 무관 0.31~0.35. 0.75 에서 top-1 40%, 0.5 에서 100%·오제안 0%. 앞부분 토막 대 청크 전체 비교라 거의 같은 문서도 0.7 안팎. 실문서 분포는 판정 로그로 재확인 |
| 되돌리기 delete 의 복귀 실패 (I2) | 이전 버전 재활성이 `synced` 가 아니면 삭제하지 않고 **detach 로 낮춘다**(응답 `detached_document_id`, `sync_state=pending`, 목록 재반영 배너로 이어짐) | 근거 공백 방지(§1.1 목표 2) |
| 최신 삭제의 복귀 실패 (I2) | 삭제를 멈추고 **409 `RESTORE_PENDING`**. 요청 롤백으로 MySQL 은 원상복구되므로 이전 버전 청크 표식도 superseded 로 되돌린다(최선 시도) | 사용자가 명시한 "삭제"를 다른 동작으로 바꾸지 않음 |
| 사전 점검 파싱 실패 (I3) | 미지원 확장자는 422(업로드와 동일), 그 밖의 파싱 예외는 본문 신호 없이 **파일명 점수만으로** 계속 | Plan SC-7 |
| FR-19 계보 전체 삭제 (I4) | 이번 사이클 범위 밖. 대신 최신 삭제에서 "이전 버전 복귀"를 끄면 계보가 검색에서 빠지는 경로가 있다 | 사용 빈도 낮음, 개별 삭제로 대체 가능 |
| detach 라벨 (M5) | detach 시 `version_label`·`effective_date` 도 비운다 | 독립 v1 에 이전 계보 라벨이 남지 않게 |
| 업로드 상태코드 (M6) | 기존 업로드 엔드포인트 계약 그대로 **200** (§4.2 #2 의 201 표기 정정) | 하위 호환 |
| 점수 폴백 범위 (M7) | `failed` 뿐 아니라 `skipped`(보조 LLM 미설정)에도 점수 기준 제안 적용 | LLM 미설정 환경에서도 제안 기능 유지 |
| ES 버전 충돌 (M8) | `update_by_query` 응답의 `version_conflicts > 0` 이면 실패 → `sync_state=pending` | 일부 청크 누락을 성공으로 오판하지 않게 |
| quick setup 중복 (M9) | quick setup 도 해시 중복을 막는다(같은 파일 2개면 하나는 파일 단위 실패) | 중복 차단이 섞임의 직접 원인이라 경로 무관 적용 |
| 삭제 실패 후 표식 (M10) | 저장소 삭제 예외 시 이전 버전 청크가 active 로 남을 수 있음 → 두 버전 동시 검색(근거 공백 아님). 후속 개선 후보 | 위험 방향이 안전 쪽 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-21 | 초안 — Option C 선택, 검색 가드 5지점·계약 테스트, 데이터 모델 V095~V097 | 배상규 |
