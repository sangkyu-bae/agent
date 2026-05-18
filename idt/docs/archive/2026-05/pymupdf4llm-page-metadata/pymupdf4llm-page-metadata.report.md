# pymupdf4llm-page-metadata Completion Report

> **Feature**: pymupdf4llm-page-metadata
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Completed

---

## Executive Summary

### 1.1 Overview

| Item | Value |
|------|-------|
| **Feature** | pymupdf4llm-page-metadata |
| **Start Date** | 2026-05-13 |
| **Completion Date** | 2026-05-13 |
| **Duration** | ~2 hours (single session) |

### 1.2 Results

| Metric | Value |
|--------|-------|
| **Match Rate** | 98% |
| **Iteration Count** | 0 (first pass) |
| **Files Changed** | 2 (production 1 + test 1) |
| **Lines Changed** | ~350 (production 177 + test 340) |
| **Tests** | 42 passed / 0 failed |
| **Regression** | 0 (전체 parser 92 tests passed) |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | pymupdf4llm이 `to_markdown()`으로 전체 PDF를 단일 markdown 문자열로 변환하여 `page=1, total_pages=1`로 고정 → Qdrant payload에 page/section/table 메타데이터 전부 소실 |
| **Solution** | `to_markdown(page_chunks=True)` 적용으로 페이지별 Document 생성 + `_extract_first_heading()`, `_detect_table()` 헬퍼로 section_title/has_table 메타데이터 보강 |
| **Function/UX Effect** | RAG 검색 결과에 "3페이지, §대출한도 산출기준, 테이블 포함" 같은 정밀한 출처 정보 표시 → 사용자가 원문 위치 즉시 확인 가능, page/section/table 기준 필터링 가능 |
| **Core Value** | 수정 파일 1개(+테스트 1개), 0 iteration으로 pymupdf4llm의 markdown 품질과 pymupdf 수준의 메타데이터 정밀도를 동시 확보 — domain 변경 없이 infrastructure만 수정 |

---

## 2. PDCA Cycle Summary

### 2.1 Phase Timeline

| Phase | Timestamp | Action | Duration |
|-------|-----------|--------|----------|
| Plan | 2026-05-13 18:00 | Plan 문서 작성 — 문제 분석, `page_chunks=True` 접근 결정, FR 7개 정의 | ~30min |
| Design | 2026-05-13 18:30 | Design 문서 작성 — 코드 수준 상세 설계, Before/After 비교, 테스트 사양 28개 | ~30min |
| Do | 2026-05-13 19:00 | TDD 구현 — Red(1 failed) → Green(42 passed), 전체 parser 92 passed | ~30min |
| Check | 2026-05-13 19:30 | Gap 분석 — 98 items checked, 96 matched, Match Rate 98% | ~15min |
| Report | 2026-05-13 19:45 | 완료 보고서 생성 | ~5min |

### 2.2 Phase Flow

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ (98%) → [Report] ✅
```

---

## 3. Technical Changes

### 3.1 Changed Files

| File | Type | Description |
|------|------|-------------|
| `src/infrastructure/parser/pymupdf4llm_parser.py` | Modified | `_convert_to_documents()` 리팩토링, `_extract_first_heading()`, `_detect_table()` 추가 |
| `tests/infrastructure/parser/test_pymupdf4llm_parser.py` | Modified | 기존 11 tests → 42 tests (mock 전환 + 신규 추가) |

### 3.2 Key Changes Detail

#### `_convert_to_documents()` Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| `to_markdown()` call | 단일 markdown 문자열 | `page_chunks=True` → 페이지별 dict 리스트 |
| Document count | 항상 1개 | 페이지 수 (빈 페이지 제외) |
| `page` metadata | 항상 `1` | 실제 PDF 페이지 번호 (1-indexed) |
| `total_pages` | 항상 `1` | `pdf_doc.page_count` |
| `source_total_pages` | 있음 (중복) | 제거 (`total_pages`가 정확하므로) |
| `section_title` | 없음 | 페이지 첫 마크다운 헤딩 |
| `has_table` | 없음 | 마크다운 테이블 존재 여부 |

#### 신규 헬퍼 메서드

| Method | Input | Output | Purpose |
|--------|-------|--------|---------|
| `_extract_first_heading(md_text)` | markdown 문자열 | 첫 번째 `#` 헤딩 텍스트 (없으면 `""`) | section_title 추출 |
| `_detect_table(md_text)` | markdown 문자열 | `True`/`False` | 마크다운 테이블 감지 |

### 3.3 Unchanged Files (by design)

| File | Reason |
|------|--------|
| `src/domain/parser/interfaces.py` | PDFParserInterface 변경 없음 |
| `src/domain/parser/value_objects.py` | DocumentMetadata VO 변경 없음 — 파서 전용 메타데이터는 `meta_dict`에 직접 추가 |
| `src/infrastructure/chunking/strategies/*` | `merge_metadata`로 새 필드 자동 상속 — 수정 불필요 |
| `src/infrastructure/vector/qdrant_vectorstore.py` | Qdrant schemaless payload — 필드 추가에 스키마 변경 불필요 |

---

## 4. Test Results

### 4.1 Test Summary

| Category | Count | Status |
|----------|:-----:|:------:|
| Interface compliance | 3 | PASS |
| Parse (page-level) | 11 | PASS |
| Parse bytes | 2 | PASS |
| Section title | 4 | PASS |
| Has table | 4 | PASS |
| Table extraction | 2 | PASS |
| `_extract_first_heading` unit | 7 | PASS |
| `_detect_table` unit | 5 | PASS |
| `_strip_markdown_tables` unit | 4 | PASS |
| **Total** | **42** | **ALL PASS** |

### 4.2 Regression Check

```
tests/infrastructure/parser/ — 92 passed, 0 failed
  test_llamaparser.py         16 passed
  test_parser_factory.py      19 passed
  test_pymupdf4llm_parser.py  42 passed
  test_pymupdf_parser.py      15 passed
```

---

## 5. Gap Analysis Summary

| Category | Score |
|----------|:-----:|
| Production Code Match | 100% |
| Test Code Match | 97% |
| Architecture Compliance | 100% |
| Domain Unchanged | 100% |
| Convention Compliance | 100% |
| **Overall Match Rate** | **98%** |

**Gap 2건** (경미 — 테스트 이름 미세 차이):
- `test_section_title_extracted_from_heading` → `test_section_title_extracted_from_h1` (더 명확)
- `test_section_title_h2_heading` → `test_section_title_extracted_from_h2` (일관성)

**추가 구현 6건** (Design 초과, positive):
- `_setup_mock_fitz` 헬퍼, `test_parse_zero_page_pdf_returns_empty`, `test_section_title_per_page`, `test_has_table_per_page`, `test_parse_bytes_opens_with_stream`, `show_progress` assertion

---

## 6. Architecture Compliance

| Rule | Status |
|------|:------:|
| Layer direction: infrastructure → domain | PASS |
| No domain changes (Thin DDD) | PASS |
| No infrastructure → presentation dependency | PASS |
| Logging via `get_logger` (not `print()`) | PASS |
| Function length < 40 lines | PASS (longest: `_convert_to_documents` 32줄) |
| Single responsibility | PASS |
| Type hints on all methods | PASS |

---

## 7. Data Flow (After)

```
PDF File
  ↓
pymupdf4llm.to_markdown(pdf_doc, page_chunks=True)
  ↓
List[Dict] — 페이지별 {"metadata": {"page": N}, "text": "..."}
  ↓
페이지별 Document 생성
  ├─ page = N+1 (1-indexed)
  ├─ total_pages = pdf_doc.page_count
  ├─ section_title = _extract_first_heading(text)
  ├─ has_table = _detect_table(text)
  └─ output_format = "markdown"
  ↓
Chunking Strategy (FullToken / ParentChild)
  ├─ merge_metadata → page, section_title, has_table 상속
  ↓
Qdrant Vector Store
  └─ payload: {content, page, total_pages, section_title, has_table, ...}
```

---

## 8. Lessons Learned

### What Went Well

1. **`page_chunks=True`**: pymupdf4llm이 이미 페이지별 분할 기능을 제공하고 있어, 최소 변경으로 문제 해결
2. **Domain 변경 없이 해결**: `section_title`, `has_table`을 VO에 추가하지 않고 `meta_dict`에 직접 추가하여 다른 파서에 영향 없음
3. **TDD 효과**: Red → Green → Refactor 순서로 진행하여 42개 테스트가 모든 요구사항 커버, 0 iteration으로 98% 달성

### Design Decision

- `has_table` 감지를 `_strip_markdown_tables()` **전에** 수행 — `extract_tables=False` 설정에서도 원본 기준으로 테이블 존재 여부를 정확히 판단 (FR-07)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-13 | Initial completion report | 배상규 |
