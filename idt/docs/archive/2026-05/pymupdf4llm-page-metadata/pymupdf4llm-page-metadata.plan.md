# pymupdf4llm-page-metadata Planning Document

> **Summary**: pymupdf4llm 파서가 `page_chunks=True`로 페이지별 Document를 생성하여 page/section/table 메타데이터를 보존하도록 개선
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pymupdf4llm이 `to_markdown()`으로 전체 PDF를 단일 markdown 문자열로 변환하여 page=1, total_pages=1로 고정됨 → chunking 후 Qdrant payload에 page 번호, 섹션명, 테이블 존재 여부 등 메타데이터가 전부 소실 |
| **Solution** | `to_markdown(page_chunks=True)` 옵션으로 페이지별 markdown 리스트를 받아 페이지당 Document를 생성하고, markdown 헤딩 파싱으로 section_title, has_table 플래그를 메타데이터에 추가 |
| **Function/UX Effect** | RAG 검색 결과에 "3페이지, §대출한도 산출기준, 테이블 포함" 같은 정밀한 출처 정보가 표시됨 → 사용자가 원문 위치를 즉시 확인 가능, 검색 필터링도 page/section/table 기준으로 가능 |
| **Core Value** | "markdown 품질은 좋지만 출처를 모르는 RAG"에서 "markdown 품질 + 정확한 출처 추적이 가능한 RAG"로 전환 — pymupdf4llm의 구조 보존 장점을 살리면서 pymupdf 수준의 메타데이터 정밀도 확보 |

---

## 1. Overview

### 1.1 Purpose

pymupdf4llm 파서가 PDF를 페이지별로 markdown 변환하여, 각 Document에 정확한 page 번호·섹션 제목·테이블 존재 여부 메타데이터를 부여한다. 이를 통해 chunking → Qdrant 저장 시 payload가 완전히 보존되어, RAG 검색 결과의 출처 추적과 필터링 정확도를 크게 향상시킨다.

### 1.2 Background

**현재 문제**:

```
pymupdf4llm.to_markdown(pdf_doc)
  → 전체 PDF가 하나의 markdown 문자열로 합쳐짐
  → Document 1개 생성 (page=1, total_pages=1)
  → chunking 후 모든 chunk가 page=1
  → Qdrant payload에 실제 페이지 정보 없음
```

**비교 — pymupdf 파서는 정상 동작**:

```
pymupdf_parser: 페이지별 순회 → Document N개 (page=1~N, total_pages=N)
  → chunking 후 각 chunk가 원래 페이지 번호 유지
  → Qdrant payload에 정확한 page 정보 보존
```

**pymupdf4llm을 쓰는 이유**: markdown 변환 품질이 우수(테이블→마크다운표, 헤딩→#, 리스트→-)하여 RAG 청킹 품질이 plain text 대비 크게 향상됨. 하지만 현재 구현은 이 장점을 살리면서 메타데이터를 잃어버리는 상태.

**해결 키**: `pymupdf4llm.to_markdown(doc, page_chunks=True)`는 페이지별 딕셔너리 리스트를 반환:

```python
[
    {
        "metadata": {"page": 0, "width": 595.0, "height": 842.0, ...},
        "text": "# 1장 개요\n\n이 문서는...",
        "images": [...],
        "tables": [...]
    },
    {
        "metadata": {"page": 1, ...},
        "text": "## 2.1 대출한도\n\n| 구분 | 한도 |\n...",
        ...
    }
]
```

### 1.3 Related Documents

- 현행 pymupdf4llm 파서: `src/infrastructure/parser/pymupdf4llm_parser.py`
- 비교 대상 pymupdf 파서: `src/infrastructure/parser/pymupdf_parser.py`
- 파서 인터페이스: `src/domain/parser/interfaces.py`
- 도메인 VO: `src/domain/parser/value_objects.py`
- Chunking 전략: `src/infrastructure/chunking/strategies/`
- Qdrant 벡터스토어: `src/infrastructure/vector/qdrant_vectorstore.py`

---

## 2. Scope

### 2.1 In Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | pymupdf4llm 파서 페이지별 변환 | `page_chunks=True` 적용, 페이지당 Document 생성 |
| 2 | page 메타데이터 정확한 보존 | page, total_pages가 실제 PDF 페이지와 일치 |
| 3 | section_title 메타데이터 추가 | 각 페이지 markdown에서 첫 번째 헤딩(#, ##)을 추출하여 메타데이터에 포함 |
| 4 | has_table 메타데이터 추가 | 페이지 내 마크다운 테이블 존재 여부를 boolean 플래그로 추가 |
| 5 | DocumentMetadata VO 확장 | section_title, has_table 필드 추가 (Optional) |
| 6 | 기존 테스트 업데이트 + 신규 테스트 | 페이지별 Document 생성, 메타데이터 정확도 검증 |

### 2.2 Out of Scope

| # | 항목 | 사유 |
|---|------|------|
| 1 | 기존 인제스트 데이터 마이그레이션 | 신규 개발 중이라 기존 데이터 없음 |
| 2 | Qdrant 인덱스 스키마 변경 | payload는 스키마리스 — 필드 추가에 별도 마이그레이션 불필요 |
| 3 | chunking 전략 변경 | 현재 FullToken/ParentChild 전략은 per-page Document를 그대로 처리 가능 |
| 4 | 프론트엔드 검색 UI 변경 | 별도 feature로 분리 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | pymupdf4llm 파서가 `page_chunks=True`로 페이지별 Document 리스트를 반환한다 | P0 |
| FR-02 | 각 Document의 `page` 메타데이터가 실제 PDF 페이지 번호(1-indexed)와 일치한다 | P0 |
| FR-03 | 각 Document의 `total_pages`가 PDF 전체 페이지 수와 일치한다 | P0 |
| FR-04 | 각 Document에 `section_title` 메타데이터가 포함된다 (해당 페이지의 첫 번째 마크다운 헤딩, 없으면 빈 문자열) | P1 |
| FR-05 | 각 Document에 `has_table` 메타데이터가 포함된다 (해당 페이지에 마크다운 테이블이 있으면 True) | P1 |
| FR-06 | 빈 페이지(텍스트 없음)는 Document를 생성하지 않고 건너뛴다 | P0 |
| FR-07 | `extract_tables=False` 설정 시 테이블이 제거된 markdown을 반환하되, `has_table` 메타데이터는 제거 전 기준으로 설정한다 | P1 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 파싱 성능: 100페이지 PDF 기준 기존 대비 10% 이내 성능 저하 |
| NFR-02 | 기존 pymupdf 파서와 동일한 `PDFParserInterface` 계약 준수 |
| NFR-03 | 기존 chunking 전략과의 호환성 유지 (추가 수정 없이 동작) |

---

## 4. Technical Approach

### 4.1 핵심 변경: `_convert_to_documents()` 리팩토링

**Before** (현재):
```python
def _convert_to_documents(self, pdf_doc, ...):
    md_text = pymupdf4llm.to_markdown(pdf_doc)  # 전체를 하나로
    metadata = DocumentMetadata(page=1, total_pages=1)  # 페이지 정보 소실
    return [Document(page_content=md_text, metadata=metadata.to_dict())]
```

**After** (개선):
```python
def _convert_to_documents(self, pdf_doc, ...):
    page_chunks = pymupdf4llm.to_markdown(pdf_doc, page_chunks=True)
    total_pages = len(page_chunks)
    documents = []
    
    for chunk in page_chunks:
        page_num = chunk["metadata"]["page"] + 1  # 0-indexed → 1-indexed
        md_text = chunk["text"]
        
        if not md_text.strip():
            continue
        
        section_title = self._extract_first_heading(md_text)
        has_table = self._detect_table(md_text)
        
        metadata = DocumentMetadata(
            filename=filename,
            user_id=user_id,
            page=page_num,
            total_pages=total_pages,
            parser=self.get_parser_name(),
            document_id=document_id,
        )
        meta_dict = metadata.to_dict()
        meta_dict["output_format"] = "markdown"
        meta_dict["section_title"] = section_title
        meta_dict["has_table"] = has_table
        
        if not config.extract_tables:
            md_text = self._strip_markdown_tables(md_text)
        
        documents.append(Document(page_content=md_text, metadata=meta_dict))
    
    return documents
```

### 4.2 section_title 추출 로직

```python
@staticmethod
def _extract_first_heading(md_text: str) -> str:
    """페이지 markdown에서 첫 번째 헤딩을 추출."""
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""
```

### 4.3 has_table 감지 로직

```python
@staticmethod
def _detect_table(md_text: str) -> bool:
    """마크다운 테이블 존재 여부를 감지."""
    lines = md_text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("|") and "---" in next_line:
                    return True
    return False
```

### 4.4 DocumentMetadata VO 변경 (최소한)

`DocumentMetadata`는 frozen dataclass이므로 `section_title`, `has_table`을 필드로 추가하지 않고, `to_dict()` 이후 dictionary 레벨에서 추가한다. 이유:

- DocumentMetadata는 3개 파서(pymupdf, pymupdf4llm, llamaparse)가 공유하는 도메인 VO
- `section_title`, `has_table`은 pymupdf4llm 전용 메타데이터
- VO에 Optional 필드를 추가하면 다른 파서에 불필요한 의존성 발생

따라서 **파서 레벨에서 meta_dict에 직접 추가**하는 방식 채택.

### 4.5 데이터 흐름 (개선 후)

```
pymupdf4llm.to_markdown(pdf_doc, page_chunks=True)
  → List[Dict] (페이지별 markdown + metadata)
    → 페이지별 Document 생성
      ├─ page = chunk["metadata"]["page"] + 1
      ├─ total_pages = len(page_chunks)
      ├─ section_title = _extract_first_heading()
      ├─ has_table = _detect_table()
      └─ output_format = "markdown"
        → FullTokenStrategy.chunk() or ParentChildStrategy.chunk()
          ├─ 각 chunk가 원본 Document의 page 메타데이터 상속
          └─ section_title, has_table도 함께 상속
            → Qdrant payload에 완전한 메타데이터 보존
```

---

## 5. Affected Files

| # | 파일 | 변경 유형 | 설명 |
|---|------|-----------|------|
| 1 | `src/infrastructure/parser/pymupdf4llm_parser.py` | **수정** | `_convert_to_documents()` 리팩토링, `_extract_first_heading()`, `_detect_table()` 추가 |
| 2 | `tests/infrastructure/parser/test_pymupdf4llm_parser.py` | **수정/추가** | 페이지별 Document 생성, 메타데이터 정확도, 빈 페이지 스킵, 테이블 감지 테스트 |

---

## 6. Implementation Order

| 순서 | 작업 | 파일 | 예상 시간 |
|------|------|------|-----------|
| 1 | 테스트 작성 (Red) | `tests/infrastructure/parser/test_pymupdf4llm_parser.py` | 30분 |
| 2 | `_convert_to_documents()` 리팩토링 | `pymupdf4llm_parser.py` | 30분 |
| 3 | `_extract_first_heading()` 구현 | `pymupdf4llm_parser.py` | 10분 |
| 4 | `_detect_table()` 구현 | `pymupdf4llm_parser.py` | 10분 |
| 5 | 테스트 통과 확인 (Green) | 전체 | 15분 |
| 6 | 리팩토링 + edge case 테스트 | 전체 | 15분 |

**총 예상 시간**: ~2시간

---

## 7. Risk & Mitigation

| 리스크 | 영향 | 대응 |
|--------|------|------|
| `page_chunks=True` 반환 형식이 pymupdf4llm 버전에 따라 다를 수 있음 | 파싱 실패 | 반환값 구조 검증 테스트 추가, pymupdf4llm 버전 고정 |
| 페이지별 변환 시 cross-page 테이블이 잘리는 경우 | 테이블 불완전 | has_table 메타데이터로 인접 페이지 연결 힌트 제공 가능 (후속 개선) |
| section_title 추출이 부정확한 경우 (markdown이 아닌 # 포함 텍스트) | 잘못된 메타데이터 | 빈 문자열 기본값으로 안전 처리, 정규식 대신 단순 startswith 사용 |

---

## 8. Test Plan

### 8.1 단위 테스트 (TDD)

| # | 테스트 | 검증 대상 |
|---|--------|-----------|
| T-01 | 3페이지 PDF 파싱 시 Document 3개 반환 | FR-01 |
| T-02 | 각 Document의 page가 1, 2, 3으로 설정됨 | FR-02 |
| T-03 | 모든 Document의 total_pages가 3 | FR-03 |
| T-04 | 헤딩이 있는 페이지의 section_title이 정확히 추출됨 | FR-04 |
| T-05 | 헤딩이 없는 페이지의 section_title이 빈 문자열 | FR-04 |
| T-06 | 테이블이 있는 페이지의 has_table이 True | FR-05 |
| T-07 | 테이블이 없는 페이지의 has_table이 False | FR-05 |
| T-08 | 빈 페이지가 건너뛰어짐 | FR-06 |
| T-09 | extract_tables=False 시 테이블 제거되지만 has_table은 True | FR-07 |
| T-10 | `_extract_first_heading()` 유틸 단독 테스트 | edge cases |
| T-11 | `_detect_table()` 유틸 단독 테스트 | edge cases |

### 8.2 통합 테스트

| # | 테스트 | 검증 대상 |
|---|--------|-----------|
| T-12 | pymupdf4llm 파싱 → FullToken chunking → metadata 상속 확인 | 파이프라인 연동 |
| T-13 | pymupdf4llm 파싱 → ParentChild chunking → metadata 상속 확인 | 파이프라인 연동 |
