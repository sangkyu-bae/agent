# pdf-table-pipeline-preview Planning Document

> **Summary**: pymupdf4llm 파싱 + table-retrieval-enhancer를 결합한 테스트/프리뷰 API 3종 세트
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pymupdf4llm 파서와 table-retrieval-enhancer(표→의미 문장 변환)가 각각 구현되어 있지만, 전체 파이프라인을 한 눈에 확인할 수 있는 테스트 수단이 없음. Qdrant 저장 없이 파싱/변환 결과를 바로 확인하고 싶고, 실제 컬렉션에 저장하는 전체 흐름도 중간 결과와 함께 보고 싶음 |
| **Solution** | 3개의 프리뷰 API 엔드포인트를 제공. (1) `/preview/parse` — PDF→Markdown 파싱 결과만 확인, (2) `/preview/table-flatten` — Markdown 표→의미 문장 변환 확인, (3) `/preview/ingest` — 전체 파이프라인(파싱→청킹→표 변환→임베딩→Qdrant/ES 저장)을 사용자 지정 컬렉션에 실행하되 각 단계 중간 결과를 상세히 반환 |
| **Function/UX Effect** | PDF 업로드만으로 파싱 품질, 테이블 감지 정확도, 의미 문장 변환 결과를 즉시 확인 가능. 전체 Ingest 시에도 어느 단계에서 무엇이 처리되었는지 투명하게 확인 |
| **Core Value** | 기존 구현된 두 기능의 파이프라인 통합 검증. 금융 문서 테이블 RAG 품질을 실제 데이터로 빠르게 테스트하고 튜닝할 수 있는 디버그 도구 |

---

## 1. Overview

### 1.1 Purpose

`pymupdf4llm-parser`(PDF→Markdown)와 `table-retrieval-enhancer`(표→의미 문장)를 결합한 테스트/프리뷰 API를 제공하여, 전체 파이프라인의 동작을 확인하고 디버깅할 수 있게 한다.

### 1.2 Background

- `pymupdf4llm-parser`: PDF를 페이지별 Markdown으로 변환, 테이블/헤딩/리스트 구조 보존 — **구현 완료**
- `table-retrieval-enhancer`: Markdown 표를 행 단위 의미 문장으로 변환, parent_child 청킹에 통합 — **구현 완료**
- 두 기능 모두 기존 Ingest 파이프라인(`/api/v1/documents/upload-all`)에 통합되어 있으나, 중간 결과를 확인할 방법이 없음
- 테스트용으로 각 단계를 분리해서 확인하는 API + 전체를 한번에 실행하면서 상세 결과를 보는 API가 필요

### 1.3 Related Documents

| 문서 | 관계 |
|------|------|
| `docs/archive/2026-05/pymupdf4llm-parser/` | pymupdf4llm 파서 (아카이브 완료) |
| `docs/archive/2026-05/table-retrieval-enhancer/` | 테이블 검색 향상 (아카이브 완료) |
| `src/infrastructure/parser/pymupdf4llm_parser.py` | 파서 구현체 |
| `src/infrastructure/chunking/table_flattening/` | 테이블 변환 모듈 |
| `src/api/routes/unified_upload_router.py` | 기존 Ingest 라우터 (참고용) |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | **`POST /api/v1/preview/parse`** | PDF 업로드 → pymupdf4llm 파싱 → 페이지별 Markdown + 테이블 감지 결과 반환 |
| 2 | **`POST /api/v1/preview/table-flatten`** | Markdown 텍스트 입력 → 테이블 감지 → 의미 문장 변환 결과 반환 |
| 3 | **`POST /api/v1/preview/ingest`** | 전체 파이프라인 실행: 파싱→청킹(표 변환)→임베딩→Qdrant/ES 저장. 사용자 지정 컬렉션. 각 단계 중간 결과 포함 상세 응답 |
| 4 | **라우터 + Pydantic 응답 스키마** | 각 엔드포인트 전용 응답 모델 |
| 5 | **main.py DI 등록** | 프리뷰 라우터 의존성 주입 |

### 2.2 Out of Scope

| # | 항목 | 사유 |
|---|------|------|
| 1 | 프론트엔드 UI | 백엔드 API만 제공, Swagger UI로 테스트 |
| 2 | 인증/권한 체크 | 테스트용 API, 인증 없이 접근 가능 |
| 3 | 새로운 파서/청킹 구현 | 기존 구현체 그대로 조합 |
| 4 | 성능 최적화 | 디버그 목적, 단건 처리 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | `/preview/parse`: PDF 업로드 시 pymupdf4llm으로 페이지별 Markdown 변환 결과 반환 | High |
| FR-02 | `/preview/parse`: 각 페이지의 `has_table`, `section_title`, 원본 Markdown 텍스트 포함 | High |
| FR-03 | `/preview/table-flatten`: Markdown 텍스트 + section_title 입력 시 표 감지 + 의미 문장 변환 결과 반환 | High |
| FR-04 | `/preview/table-flatten`: 원본 텍스트(parent_text)와 변환 텍스트(child_text)를 나란히 비교 가능 | High |
| FR-05 | `/preview/ingest`: 사용자가 `collection_name`을 지정하여 해당 컬렉션에 저장 | High |
| FR-06 | `/preview/ingest`: 파싱 결과(페이지별), 청킹 결과(parent/child 목록), 표 변환 상세, 저장 결과를 모두 포함하는 상세 응답 | High |
| FR-07 | `/preview/parse`에서 `extract_tables=false` 옵션으로 테이블 제외 파싱 가능 | Medium |
| FR-08 | 기존 엔드포인트(`/documents/upload-all`, `/ingest/pdf`) 동작에 영향 없음 | High |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| 응답 시간 | 10MB PDF 기준 30초 이내 (파싱+변환, 임베딩 제외) |
| 에러 처리 | 각 단계 실패 시 명확한 에러 메시지 + 성공한 단계 결과는 반환 |

---

## 4. API Design

### 4.1 `POST /api/v1/preview/parse`

PDF를 pymupdf4llm으로 파싱하고 결과만 반환. 저장하지 않음.

**Request**: `multipart/form-data`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | UploadFile | Yes | - | PDF 파일 |
| `user_id` | str (Query) | Yes | - | 사용자 ID |
| `extract_tables` | bool (Query) | No | true | false 시 테이블 제거 |

**Response** (`ParsePreviewResponse`):

```json
{
  "filename": "금리안내서.pdf",
  "total_pages": 15,
  "parser": "pymupdf4llm",
  "pages": [
    {
      "page": 1,
      "has_table": true,
      "section_title": "대출 금리 기준표",
      "markdown_text": "## 대출 금리 기준표\n\n| 등급 | 금리 | 한도 |\n|---|---|---|\n| A | 3.5% | 1억 |",
      "char_count": 142
    }
  ]
}
```

### 4.2 `POST /api/v1/preview/table-flatten`

Markdown 텍스트의 표를 의미 문장으로 변환. 저장하지 않음.

**Request**: `application/json`

```json
{
  "markdown_text": "## 대출 금리\n\n| 등급 | 금리 | 한도 |\n|---|---|---|\n| A | 3.5% | 1억 |",
  "section_title": "대출 금리"
}
```

**Response** (`TableFlattenPreviewResponse`):

```json
{
  "table_count": 1,
  "parent_text": "## 대출 금리\n\n| 등급 | 금리 | 한도 |\n|---|---|---|\n| A | 3.5% | 1억 |",
  "child_text": "## 대출 금리\n\n대출 금리에서 등급은(는) A, 금리은(는) 3.5%, 한도은(는) 1억.",
  "tables": [
    {
      "original_markdown": "| 등급 | 금리 | 한도 |\n|---|---|---|\n| A | 3.5% | 1억 |",
      "search_optimized_text": "대출 금리에서 등급은(는) A, 금리은(는) 3.5%, 한도은(는) 1억.",
      "metadata": {
        "columns": ["등급", "금리", "한도"],
        "row_count": 1,
        "has_numeric_data": true
      }
    }
  ]
}
```

### 4.3 `POST /api/v1/preview/ingest`

전체 파이프라인 실행 + 각 단계 중간 결과 반환.

**Request**: `multipart/form-data`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | UploadFile | Yes | - | PDF 파일 |
| `user_id` | str (Query) | Yes | - | 사용자 ID |
| `collection_name` | str (Query) | Yes | - | 대상 Qdrant 컬렉션명 |
| `child_chunk_size` | int (Query) | No | 500 | 자식 chunk 토큰 크기 |
| `child_chunk_overlap` | int (Query) | No | 50 | 자식 chunk 오버랩 |

**Response** (`IngestPreviewResponse`):

```json
{
  "document_id": "uuid",
  "filename": "금리안내서.pdf",
  "status": "completed",
  "parse_result": {
    "total_pages": 15,
    "pages_with_tables": 5,
    "parser": "pymupdf4llm"
  },
  "chunk_result": {
    "total_chunks": 42,
    "parent_chunks": 12,
    "child_chunks": 30,
    "table_flattened_chunks": 8,
    "sample_parent": { "text": "...(200자)...", "metadata": {} },
    "sample_child": { "text": "...(200자)...", "metadata": {} },
    "sample_flattened_child": { "text": "대출 금리에서...", "metadata": {"table_flattened": true} }
  },
  "store_result": {
    "qdrant": { "collection_name": "my-col", "stored_count": 42, "status": "success" },
    "es": { "indexed_count": 42, "status": "success" }
  },
  "chunking_config": {
    "strategy": "parent_child",
    "parent_chunk_size": 2000,
    "child_chunk_size": 500,
    "child_chunk_overlap": 50,
    "table_flattening": true
  }
}
```

---

## 5. Architecture

### 5.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       Preview Router (신규)                       │
│  POST /preview/parse          → PyMuPDF4LLMParser 직접 호출      │
│  POST /preview/table-flatten  → TableFlatteningPreprocessor 직접  │
│  POST /preview/ingest         → UnifiedUploadUseCase 확장 또는    │
│                                 PreviewIngestUseCase (신규)       │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│              기존 구현체 (변경 없음, 재사용)                       │
│                                                                   │
│  PyMuPDF4LLMParser              → PDF → 페이지별 Markdown         │
│  TableFlatteningPreprocessor    → 표 감지 + 의미 문장 변환         │
│  RuleBasedTableContentGenerator → 규칙 기반 변환                   │
│  ChunkingStrategyFactory        → parent_child + table_flattening │
│  UnifiedUploadUseCase           → Qdrant/ES 저장 (ingest용 참고)  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 핵심 설계 결정

| Decision | Selected | Rationale |
|----------|----------|-----------|
| /preview/parse, /preview/table-flatten | 라우터에서 인프라 직접 호출 | 단순 프리뷰. UseCase 불필요 |
| /preview/ingest | 신규 UseCase (`PreviewIngestUseCase`) | UnifiedUploadUseCase를 상속/확장하기엔 응답 구조가 너무 다름. 별도 UseCase가 명확 |
| 라우터 위치 | `src/api/routes/preview_router.py` 단일 파일 | 3개 엔드포인트 모두 프리뷰 목적, 하나의 라우터로 관리 |

---

## 6. Implementation Guide

### 6.1 파일 변경 목록

| 파일 | 작업 | 설명 |
|------|------|------|
| `src/api/routes/preview_router.py` | **신규** | 프리뷰 라우터 3개 엔드포인트 + Pydantic 응답 모델 |
| `src/application/preview/ingest_preview_use_case.py` | **신규** | `/preview/ingest` 전용 UseCase |
| `src/application/preview/__init__.py` | **신규** | 패키지 init |
| `src/api/main.py` | **수정** | 프리뷰 라우터 등록 + DI 설정 |
| `tests/api/routes/test_preview_router.py` | **신규** | 라우터 단위 테스트 |

### 6.2 구현 순서

1. `src/api/routes/preview_router.py` — 라우터 + 응답 스키마 정의
2. `/preview/parse` 엔드포인트 구현 (PyMuPDF4LLMParser 직접 호출)
3. `/preview/table-flatten` 엔드포인트 구현 (TableFlatteningPreprocessor 직접 호출)
4. `src/application/preview/ingest_preview_use_case.py` — Ingest 프리뷰 UseCase
5. `/preview/ingest` 엔드포인트 구현 (UseCase 호출)
6. `src/api/main.py` — DI 등록 + 라우터 포함
7. 테스트 작성

---

## 7. Success Criteria

### 7.1 Definition of Done

- [ ] `/preview/parse` — PDF 업로드 시 페이지별 Markdown + 테이블 감지 결과 반환
- [ ] `/preview/table-flatten` — Markdown 입력 시 parent/child 텍스트 비교 반환
- [ ] `/preview/ingest` — 전체 파이프라인 실행 + 중간 결과 상세 반환, 사용자 지정 컬렉션 저장
- [ ] 기존 `/documents/upload-all`, `/ingest/pdf` 동작 변화 없음
- [ ] Swagger UI에서 3개 엔드포인트 정상 노출

---

## 8. Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| `/preview/ingest`가 UnifiedUploadUseCase와 코드 중복 | Medium | 공통 로직은 private 메서드 추출, 저장 로직은 기존 패턴 재사용 |
| 대용량 PDF에서 /preview/parse 응답이 너무 큼 | Low | 페이지별 텍스트에 최대 글자 수 제한 옵션 추가 가능 |
| 프리뷰 API로 대량 데이터 저장 남용 | Low | 테스트 용도 명시, 필요 시 rate limit 추가 |

---

## 9. Architecture Considerations

### 9.1 Project Level

| Level | Selected |
|-------|:--------:|
| **Enterprise** (Thin DDD) | **Yes** |

### 9.2 Clean Architecture

```
┌─────────────────────────────────────────────────┐
│ api/routes/                                     │
│   - preview_router.py     ← 신규 라우터          │
├─────────────────────────────────────────────────┤
│ application/preview/                            │
│   - ingest_preview_use_case.py  ← 신규 UseCase  │
├─────────────────────────────────────────────────┤
│ infrastructure/ (변경 없음, 재사용만)             │
│   - parser/pymupdf4llm_parser.py                │
│   - chunking/table_flattening/                  │
│   - chunking/chunking_factory.py                │
├─────────────────────────────────────────────────┤
│ domain/ (변경 없음)                              │
└─────────────────────────────────────────────────┘
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-14 | Initial draft | 배상규 |
