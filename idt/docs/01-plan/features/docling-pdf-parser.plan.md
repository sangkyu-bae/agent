# docling-pdf-parser Planning Document

> **Summary**: Docling 기반 3번째 PDF 파서 추가 — Markdown 출력 + 테이블 추출 지원, CPU 로컬 실행
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 PyMuPDF는 테이블 구조를 보존하지 못하고, LlamaParse는 유료 클라우드 API라 모든 문서에 적용하기엔 비용 부담 — 테이블이 포함된 일반 문서를 로컬에서 고품질로 파싱할 수단이 없음 |
| **Solution** | IBM Docling을 3번째 파서로 `ParserFactory`에 추가하여 Markdown 출력(테이블 보존)을 지원하고, pdf-analyzer의 라우팅과 연동하여 복잡한 문서만 LlamaParse로 보내고 나머지는 Docling으로 처리 |
| **Function/UX Effect** | 업로드된 PDF가 자동으로 복잡도 판단 후 적절한 파서로 라우팅 → 테이블이 Markdown 표로 변환되어 RAG 청킹 품질 향상, LlamaParse API 호출 감소로 비용 절감 |
| **Core Value** | "모든 문서를 동일 파서로 처리"에서 "복잡도 기반 자동 라우팅"으로 전환 — 비용 효율과 파싱 품질을 동시에 확보하며, 로컬 실행으로 외부 의존성 최소화 |

---

## 1. Overview

### 1.1 Purpose

Docling(IBM 오픈소스 문서 파서)을 `PDFParserInterface` 구현체로 추가하여, PDF를 Markdown으로 변환하고 테이블 구조를 보존한다. pdf-analyzer의 분류 결과와 연동하여 복잡한 문서(OCR/멀티모달)만 LlamaParse로, 나머지(텍스트/테이블)는 Docling으로 자동 라우팅한다.

### 1.2 Background

현재 파서 인프라:
- **PyMuPDF**: 빠르고 가벼움, 테이블 구조 보존 불가, OCR 미지원
- **LlamaParse**: 테이블/OCR 모두 지원, 유료 클라우드 API (문서당 과금)
- **pdf-analyzer** (Plan 존재): PDF 유형 분류 계층 설계 완료 (TEXT_HEAVY / OCR_HEAVY / TABLE_HEAVY / MULTIMODAL)

**핵심 Gap**: 테이블이 포함된 일반 문서(금융 보고서, 정책 문서)를 로컬에서 고품질로 파싱할 파서가 없다.

**Docling 선택 이유**:
- MIT 라이선스, IBM Research 개발
- PDF → Markdown 변환 품질 우수 (테이블을 Markdown 표로 변환)
- 레이아웃 분석 + OCR 기본 지원
- CPU 환경에서 동작 가능 (GPU 선택적)
- LangChain 통합 지원 (`DoclingLoader`)

### 1.3 Related Documents

- 현행 파서 인터페이스: `src/domain/parser/interfaces.py`
- 현행 VO: `src/domain/parser/value_objects.py`
- 파서 팩토리: `src/infrastructure/parser/parser_factory.py`
- PyMuPDF 구현: `src/infrastructure/parser/pymupdf_parser.py`
- LlamaParse 구현: `src/infrastructure/parser/llamaparser.py`
- 파이프라인 파싱 노드: `src/infrastructure/pipeline/nodes/parse_node.py`
- PDF Analyzer Plan: `docs/01-plan/features/pdf-analyzer.plan.md`

---

## 2. Scope

### 2.1 In Scope

| # | Item | Description |
|---|------|-------------|
| 1 | **DoclingParser 구현** | `PDFParserInterface`를 구현하는 `DoclingParser` 클래스 (infrastructure) |
| 2 | **ParserFactory 확장** | `ParserType.DOCLING` enum 추가 및 팩토리 메서드 확장 |
| 3 | **Markdown 출력** | Docling의 Markdown 변환 결과를 `Document.page_content`에 저장 |
| 4 | **테이블 보존** | PDF 내 테이블을 Markdown 표(`\| col \|`) 형식으로 변환하여 보존 |
| 5 | **페이지별 Document 분할** | 기존 파서와 동일하게 페이지별 `Document` 객체 생성 + `DocumentMetadata` |
| 6 | **ParserConfig 호환** | 기존 `ParserConfig` VO와 호환 (language, extract_tables 등) |
| 7 | **TDD 테스트** | 단위 테스트 + 통합 테스트 (샘플 PDF 포함) |

### 2.2 Out of Scope

| # | Item | Reason |
|---|------|--------|
| 1 | pdf-analyzer 라우팅 로직 구현 | pdf-analyzer는 별도 feature, 이 Plan은 파서 추가만 담당 |
| 2 | GPU 가속 설정 | 1단계는 CPU only, GPU 지원은 추후 확장 |
| 3 | 이미지 추출/저장 | Docling의 이미지 추출 기능은 추후 별도 feature |
| 4 | DOCX/PPTX 지원 | Docling이 지원하지만 현재 인터페이스는 PDF 전용 |
| 5 | 기존 파서 제거/변경 | PyMuPDF, LlamaParse 기존 코드 무변경 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `DoclingParser`가 `PDFParserInterface`를 구현 (`parse`, `parse_bytes`, `get_parser_name`, `supports_ocr`) | Must | Pending |
| FR-02 | PDF → Markdown 변환 결과를 `Document.page_content`에 저장 | Must | Pending |
| FR-03 | 테이블을 Markdown 표 형식으로 변환하여 보존 | Must | Pending |
| FR-04 | 페이지별 `Document` 객체 생성 (기존 메타데이터 구조 유지: `DocumentMetadata`) | Must | Pending |
| FR-05 | `ParserFactory`에 `ParserType.DOCLING` 추가 및 인스턴스 생성 | Must | Pending |
| FR-06 | `ParserConfig.language` 설정 반영 (Docling OCR 언어 설정) | Should | Pending |
| FR-07 | `ParserConfig.extract_tables` 플래그에 따라 테이블 추출 on/off | Should | Pending |
| FR-08 | Docling 모델 초기화를 lazy loading으로 처리 (첫 호출 시 다운로드) | Should | Pending |

### 3.2 Non-Functional Requirements

| ID | Category | Criteria |
|----|----------|----------|
| NFR-01 | Performance | 10페이지 PDF 파싱 < 30초 (CPU, 첫 호출 모델 다운로드 제외) |
| NFR-02 | Memory | 50페이지 PDF 파싱 시 메모리 사용량 < 2GB |
| NFR-03 | Logging | LOG-001 준수: 파싱 시작/완료/실패 로깅 (파서명, 페이지 수, 소요시간) |
| NFR-04 | Architecture | domain 레이어 변경 없음 (기존 `PDFParserInterface` 그대로 사용) |
| NFR-05 | Dependency | `docling` 패키지만 추가, 기존 의존성 충돌 없음 확인 |

---

## 4. Architecture

### 4.1 Layer Design (Thin DDD)

```
[변경 없음] domain/parser/
├── interfaces.py           # PDFParserInterface (기존 유지)
├── value_objects.py         # ParserConfig, DocumentMetadata (기존 유지)
└── schemas.py               # (기존 유지)

[변경] infrastructure/parser/
├── pymupdf_parser.py        # (기존 유지)
├── llamaparser.py           # (기존 유지)
├── docling_parser.py        # ★ 신규: DoclingParser
└── parser_factory.py        # ★ 수정: ParserType.DOCLING 추가
```

### 4.2 Data Flow

```
[PDF bytes/path]
    │
    ▼
DoclingParser.parse_bytes() / parse()
    │
    ├── 1) DocumentConverter 초기화 (lazy, 모델 캐싱)
    │      - PipelineOptions: OCR/테이블 설정
    │      - InputFormat.PDF
    │
    ├── 2) converter.convert() → DoclingDocument
    │
    ├── 3) DoclingDocument → Markdown 변환
    │      - doc.export_to_markdown()
    │      - 테이블 → Markdown 표 자동 변환
    │
    ├── 4) 페이지별 분할
    │      - Docling 페이지 경계 기반 분할
    │      - 또는 전체 Markdown을 페이지 마커로 split
    │
    └── 5) List[Document] 반환
           - page_content: Markdown 텍스트
           - metadata: DocumentMetadata (filename, page, parser="docling", ...)
```

### 4.3 ParserFactory 확장

```python
class ParserType(Enum):
    PYMUPDF = "pymupdf"
    LLAMAPARSER = "llamaparser"
    DOCLING = "docling"           # ★ 추가

class ParserFactory:
    @staticmethod
    def create(parser_type, api_key=None):
        ...
        if parser_type == ParserType.DOCLING:
            return DoclingParser()  # API key 불필요 (로컬)
```

### 4.4 DoclingParser 핵심 설계

```python
class DoclingParser(PDFParserInterface):
    def __init__(self) -> None:
        self._converter: Optional[DocumentConverter] = None  # lazy init

    def _get_converter(self, config: ParserConfig) -> DocumentConverter:
        """Docling DocumentConverter lazy 초기화."""
        if self._converter is None:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = config.ocr_enabled
            pipeline_options.do_table_structure = config.extract_tables

            self._converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options
                    )
                },
            )
        return self._converter

    def parse_bytes(self, file_bytes, filename, user_id, config=None):
        config = config or ParserConfig()
        converter = self._get_converter(config)
        # temp file 생성 → convert → Markdown export → 페이지별 Document 분할
        ...

    def get_parser_name(self) -> str:
        return "docling"

    def supports_ocr(self) -> bool:
        return True  # Docling 내장 OCR 지원
```

---

## 5. Detailed Design

### 5.1 페이지별 분할 전략

Docling은 전체 문서를 하나의 `DoclingDocument`로 변환하므로, 페이지별 `Document` 객체 분할 전략이 필요하다.

**선택지 분석**:

| 전략 | 장점 | 단점 |
|------|------|------|
| A. `doc.export_to_markdown()` 후 페이지 마커 기반 split | 단순, Markdown 품질 보존 | Docling이 페이지 마커를 항상 제공하지 않을 수 있음 |
| B. `DoclingDocument.pages` 순회하며 페이지별 export | 정확한 페이지 경계 | Docling API 버전에 따라 지원 여부 다름 |
| C. 전체 Markdown을 하나의 Document로 반환 | 가장 단순 | 기존 파서와 메타데이터 구조 불일치 (page별 분리 안 됨) |

**선택: B → A 폴백**
- 우선 `DoclingDocument`의 페이지 구조를 활용하여 페이지별 분할
- 페이지 구조가 불명확한 경우 전체 Markdown을 하나의 Document로 반환 (page=1, total_pages=1)

### 5.2 Docling 설정 매핑

| ParserConfig 필드 | Docling 매핑 | 기본값 |
|-------------------|-------------|--------|
| `language` | `OcrOptions.lang` | "ko" |
| `extract_tables` | `PdfPipelineOptions.do_table_structure` | True |
| `ocr_enabled` | `PdfPipelineOptions.do_ocr` | False |
| `extract_images` | (미사용, Out of Scope) | False |

### 5.3 모델 관리

Docling은 첫 실행 시 레이아웃 분석 모델을 다운로드한다 (~수백 MB).

- **다운로드 위치**: `~/.docling/models/` (Docling 기본 경로)
- **캐싱**: 한 번 다운로드 후 재사용 (Docling 내장 캐시)
- **lazy init**: `DoclingParser._converter`를 첫 `parse` 호출 시 초기화
- **환경변수**: `DOCLING_MODELS_PATH`로 모델 경로 커스터마이징 가능 (선택)

---

## 6. Implementation Order

| Phase | Task | Files | Dependency |
|-------|------|-------|------------|
| 1 | `docling` 패키지 설치 + 의존성 확인 | `pyproject.toml` | None |
| 2 | `DoclingParser` 구현 (TDD) | `src/infrastructure/parser/docling_parser.py` | Phase 1 |
| 3 | `ParserFactory` 확장 | `src/infrastructure/parser/parser_factory.py` | Phase 2 |
| 4 | 통합 테스트 (실제 PDF 파싱) | `tests/infrastructure/parser/test_docling_parser.py` | Phase 2 |
| 5 | 팩토리 테스트 업데이트 | `tests/infrastructure/parser/test_parser_factory.py` | Phase 3 |

---

## 7. Testing Strategy

### 7.1 Unit Tests (TDD)

| Test | Description |
|------|-------------|
| `test_docling_parser_implements_interface` | `PDFParserInterface` 구현 확인 |
| `test_docling_parser_get_parser_name` | `"docling"` 반환 확인 |
| `test_docling_parser_supports_ocr` | `True` 반환 확인 |
| `test_docling_parser_parse_bytes_returns_documents` | bytes 입력 → `List[Document]` 반환 |
| `test_docling_parser_parse_path_returns_documents` | file_path 입력 → `List[Document]` 반환 |
| `test_docling_parser_metadata_structure` | `DocumentMetadata` 필드 (filename, page, parser, document_id) 검증 |
| `test_docling_parser_markdown_output` | `page_content`에 Markdown 형식 텍스트 포함 확인 |
| `test_docling_parser_table_preservation` | 테이블 포함 PDF → Markdown 표(`\|`) 형식 변환 확인 |
| `test_docling_parser_empty_page_skip` | 빈 페이지 → Document 생성 안 함 |
| `test_docling_parser_config_language` | `ParserConfig(language="en")` 적용 확인 |

### 7.2 Factory Tests

| Test | Description |
|------|-------------|
| `test_parser_factory_create_docling` | `ParserType.DOCLING` → `DoclingParser` 생성 확인 |
| `test_parser_factory_from_string_docling` | `"docling"` 문자열 → `DoclingParser` 생성 확인 |

### 7.3 Integration Tests

| Test | Description |
|------|-------------|
| `test_docling_parser_real_text_pdf` | 실제 텍스트 PDF 파싱 (sample fixture) |
| `test_docling_parser_real_table_pdf` | 실제 테이블 포함 PDF 파싱 → Markdown 표 확인 |
| `test_docling_parser_pipeline_node_compat` | `parse_node`에서 DoclingParser 사용 가능 확인 |

---

## 8. Success Criteria

### 8.1 Definition of Done

- [ ] `DoclingParser`가 `PDFParserInterface` 4개 메서드 모두 구현
- [ ] `ParserFactory`에서 `ParserType.DOCLING`으로 생성 가능
- [ ] 테이블 포함 PDF → Markdown 표 형식으로 출력 확인
- [ ] 기존 `parse_node` 파이프라인과 호환 확인
- [ ] 모든 단위/통합 테스트 통과
- [ ] LOG-001 준수 (파싱 시작/완료/실패 로깅)

### 8.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] 기존 PyMuPDF/LlamaParse 테스트 깨짐 없음
- [ ] mypy 타입 검사 통과

---

## 9. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Docling 모델 다운로드 크기 (수백 MB) | 첫 실행 느림, 디스크 사용 | High | lazy init + 로그 안내, 모델 경로 설정 가능 |
| CPU 환경에서 파싱 속도 저하 | 대용량 PDF 처리 시간 증가 | Medium | NFR-01 기준 (10p < 30초) 준수 확인, 초과 시 경고 로깅 |
| Docling 페이지별 분할 API 변경 | 페이지 경계 분할 로직 깨짐 | Medium | 폴백 전략 (전체 Markdown → 단일 Document), 버전 고정 |
| 기존 의존성과 충돌 (torch, transformers 등) | 패키지 설치 실패 | Medium | `docling[cpu]` 경량 설치, 의존성 사전 검증 |
| Markdown 출력이 기존 chunking 로직과 비호환 | 청킹 품질 저하 | Low | Markdown 특화 chunker 추후 추가 가능 (Out of Scope) |

---

## 10. Dependencies

### 10.1 New Package

```toml
# pyproject.toml
[project.dependencies]
docling = ">=2.0.0"
```

### 10.2 Environment Variables (Optional)

| Variable | Purpose | Required |
|----------|---------|----------|
| `DOCLING_MODELS_PATH` | Docling 모델 저장 경로 커스터마이징 | No (기본: ~/.docling/models/) |

---

## 11. Future Extensions

| Extension | Description | Trigger |
|-----------|-------------|---------|
| pdf-analyzer 라우팅 연동 | `AnalysisResult` → `ParserType` 자동 매핑 (TEXT/TABLE → Docling, OCR/MULTIMODAL → LlamaParse) | pdf-analyzer 구현 완료 후 |
| GPU 가속 | `docling[gpu]` 설치 + CUDA 설정 | CPU 성능 부족 시 |
| Markdown 특화 chunker | Markdown 헤더/테이블 경계 기반 청킹 | RAG 품질 개선 필요 시 |
| DOCX/PPTX 지원 | Docling 멀티포맷 활용 `PDFParserInterface` 확장 또는 별도 인터페이스 | 비PDF 문서 지원 요청 시 |
| 이미지 추출 | Docling의 이미지 추출 → 별도 저장/벡터화 | 멀티모달 RAG 필요 시 |

---

## 12. Next Steps

1. [ ] Design 문서 작성 (`docling-pdf-parser.design.md`)
2. [ ] `docling` 패키지 설치 및 의존성 검증
3. [ ] TDD 사이클 시작 (Phase 1~5 순서)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-12 | Initial draft | 배상규 |
