# pdf-analyzer Planning Document

> **Summary**: PDF 앞 N페이지 샘플링 → 유형 분류(text/ocr/table/multimodal) → 분류 결과만 반환하는 PDFAnalyzer 계층
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 `ParserFactory`는 설정 기반으로 파서를 선택하지만 PDF 내용 특성(OCR/텍스트/표/멀티모달)을 분석하지 않음 — 모든 PDF를 동일 파서로 처리하여 품질 편차 발생 |
| **Solution** | PDF 앞 N페이지를 샘플링하여 유형을 분류하는 `PDFAnalyzer` 계층을 domain/application에 추가, 분류 결과(enum + 메트릭)만 반환하여 라우팅 계층이 파서를 선택하도록 분리 |
| **Function/UX Effect** | 업로드 시 PDF 특성에 맞는 최적 파서가 자동 선택 → 표 위주 문서는 표 파서, OCR 문서는 OCR 파서로 라우팅되어 파싱 품질 향상 |
| **Core Value** | "파서 선택을 사람이 결정"에서 "PDF 특성 기반 자동 라우팅"으로 전환 — 분류와 파싱의 책임 분리로 파서 확장 시 Analyzer 수정 불필요 |

---

## 1. Overview

### 1.1 Purpose

PDF 파일의 앞 N페이지를 샘플링하여 내용 특성을 분석하고, **4가지 유형(text-heavy / ocr-heavy / table-heavy / multimodal)** 중 하나로 분류한다. Analyzer는 분류 결과만 반환하며, 이후 라우팅 계층이 결과를 기반으로 적절한 파서를 선택한다.

### 1.2 Background

현재 파서 인프라:
- `PDFParserInterface` → `PyMuPDFParser`(텍스트 전용), `LlamaParserAdapter`(OCR 지원)
- `ParserFactory`가 `ParserType` enum 기반으로 파서 생성
- PDF 내용 특성을 분석하는 계층 없음 → 파서 선택이 수동/고정

**핵심 인사이트**: PDF 유형별로 최적 파서가 다르다.
- 텍스트 위주 → PyMuPDF (빠르고 정확)
- OCR 위주 (스캔 문서) → OCR 파서 (Tesseract, LlamaParse 등)
- 표 위주 → 표 전용 파서 (Camelot, Tabula 등)
- 복잡한 멀티모달 → 멀티모달 파서 (LlamaParse, Document AI 등)

분류 로직을 파싱과 분리하면 파서를 추가/교체해도 Analyzer는 변경 불필요.

### 1.3 Related Documents

- 현행 파서 인터페이스: `src/domain/parser/interfaces.py`
- 현행 파서 스키마: `src/domain/parser/schemas.py`
- 현행 VO: `src/domain/parser/value_objects.py`
- PyMuPDF 구현: `src/infrastructure/parser/pymupdf_parser.py`
- LlamaParse 구현: `src/infrastructure/parser/llamaparser.py`
- 파서 팩토리: `src/infrastructure/parser/parser_factory.py`
- 파싱 UseCase: `src/application/use_cases/pdf_parse_use_case.py`

---

## 2. Scope

### 2.1 In Scope

| # | Item | Description |
|---|------|-------------|
| 1 | **PDFDocumentType enum** | `TEXT_HEAVY`, `OCR_HEAVY`, `TABLE_HEAVY`, `MULTIMODAL` 4가지 유형 정의 (domain) |
| 2 | **AnalysisConfig VO** | 샘플 페이지 수(`sample_pages`, 기본 5), 분석 임계값 설정 — 추후 유연한 변경 가능 |
| 3 | **PageFeatures VO** | 페이지별 특성 메트릭: text_char_count, image_count, image_area_ratio, table_count, has_extractable_text |
| 4 | **AnalysisResult schema** | 분류 결과: document_type, confidence, page_features[], summary_metrics |
| 5 | **PDFAnalyzerInterface** | domain 인터페이스: `analyze(file_bytes, config) -> AnalysisResult` |
| 6 | **PyMuPDFAnalyzer** | infrastructure 구현: fitz로 N페이지 샘플링 후 특성 추출 |
| 7 | **AnalyzePDFUseCase** | application UseCase: Analyzer 호출 → AnalysisResult 반환 |

### 2.2 Out of Scope

| # | Item | Reason |
|---|------|--------|
| 1 | 라우팅 계층 구현 | Analyzer는 분류만 담당, 라우팅은 별도 feature |
| 2 | 새 파서 추가 (Camelot, Tabula 등) | 분류 결과를 소비하는 파서는 별도 구현 |
| 3 | LLM 기반 분류 | 1단계는 rule-based (heuristic), LLM 분류는 추후 확장 |
| 4 | 전체 페이지 분석 | 성능상 샘플링만 수행, 전체 분석은 옵션으로 추후 추가 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | PDF bytes 입력 → 앞 N페이지 샘플링 (기본 5페이지) | Must |
| FR-02 | 페이지별 특성 추출: 텍스트 문자 수, 이미지 개수, 이미지 면적 비율, 표 개수, 추출 가능 텍스트 여부 | Must |
| FR-03 | 특성 기반 유형 분류: TEXT_HEAVY / OCR_HEAVY / TABLE_HEAVY / MULTIMODAL | Must |
| FR-04 | 분류 결과에 confidence score 포함 (0.0~1.0) | Should |
| FR-05 | sample_pages 값을 AnalysisConfig로 외부에서 주입 가능 (유연한 변경) | Must |
| FR-06 | 총 페이지 수가 sample_pages 미만이면 전체 페이지 분석 | Must |
| FR-07 | file_path 기반 분석도 지원 (bytes와 동일 인터페이스) | Should |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | 분석 시간 < 2초 (50페이지 PDF 기준, 5페이지 샘플링) |
| NFR-02 | 메모리: 샘플 페이지만 로드하여 대용량 PDF에서도 안정적 |
| NFR-03 | LOG-001 준수: 분석 시작/완료/실패 로깅 |
| NFR-04 | domain 레이어에 외부 라이브러리 의존 없음 |

---

## 4. Architecture

### 4.1 Layer Design (Thin DDD)

```
domain/pdf_analyzer/
├── schemas.py              # PDFDocumentType, AnalysisResult, PageFeatures
├── value_objects.py         # AnalysisConfig (sample_pages, thresholds)
├── interfaces.py            # PDFAnalyzerInterface (ABC)
└── policies.py              # ClassificationPolicy (분류 규칙)

application/pdf_analyzer/
├── use_case.py              # AnalyzePDFUseCase
└── schemas.py               # AnalyzePDFRequest, AnalyzePDFResponse

infrastructure/pdf_analyzer/
└── pymupdf_analyzer.py      # PyMuPDFAnalyzer (fitz 기반 구현)
```

### 4.2 Data Flow

```
[PDF bytes/path]
    │
    ▼
AnalyzePDFUseCase
    │
    ▼
PDFAnalyzerInterface.analyze()
    │  (infrastructure: PyMuPDFAnalyzer)
    │
    ├── 1) fitz.open() → 앞 N페이지만 로드
    ├── 2) 페이지별 특성 추출 (PageFeatures)
    │      - text: page.get_text() → char count
    │      - images: page.get_images() → count, area ratio
    │      - tables: page.find_tables() → count (fitz 1.23.0+)
    │      - extractable_text: len(text.strip()) > threshold
    │
    ├── 3) ClassificationPolicy.classify(page_features[])
    │      - 규칙 기반 분류 (domain policy)
    │
    └── 4) AnalysisResult 반환
              - document_type: PDFDocumentType
              - confidence: float
              - page_features: List[PageFeatures]
              - summary_metrics: dict
```

### 4.3 Classification Policy (Rule-based)

```python
# domain/pdf_analyzer/policies.py — 분류 규칙 정의

# 1) 전체 샘플 페이지의 평균 메트릭 계산
avg_text_chars      = mean(page.text_char_count for page in samples)
avg_image_area_ratio = mean(page.image_area_ratio for page in samples)
avg_table_count     = mean(page.table_count for page in samples)
has_text_ratio      = count(page.has_extractable_text) / len(samples)

# 2) 분류 우선순위 (앞선 조건 먼저 매칭)
if has_text_ratio < 0.3:
    → OCR_HEAVY        # 대부분 페이지에서 텍스트 추출 불가 = 스캔 문서
elif avg_table_count >= 2.0:
    → TABLE_HEAVY      # 페이지당 평균 2개 이상 표
elif avg_image_area_ratio > 0.4 and avg_table_count >= 1.0:
    → MULTIMODAL       # 이미지 + 표 혼합
elif avg_image_area_ratio > 0.5:
    → MULTIMODAL       # 이미지 비중이 절반 이상
else:
    → TEXT_HEAVY        # 기본값: 텍스트 위주
```

> **임계값은 AnalysisConfig에서 조정 가능** — 도메인 정책 분리로 추후 LLM 기반 분류로 교체 시 policies.py만 변경하면 됨.

---

## 5. Detailed Design

### 5.1 Domain Layer

#### 5.1.1 PDFDocumentType (Enum)

```python
class PDFDocumentType(str, Enum):
    TEXT_HEAVY = "text_heavy"       # 텍스트 위주 (일반 문서, 보고서)
    OCR_HEAVY = "ocr_heavy"         # 스캔/이미지 기반 (OCR 필요)
    TABLE_HEAVY = "table_heavy"     # 표 위주 (재무제표, 통계)
    MULTIMODAL = "multimodal"       # 혼합 (이미지+표+텍스트)
```

#### 5.1.2 PageFeatures (VO)

```python
@dataclass(frozen=True)
class PageFeatures:
    page_number: int
    text_char_count: int
    image_count: int
    image_area_ratio: float     # 0.0 ~ 1.0
    table_count: int
    has_extractable_text: bool  # text_char_count > min_threshold
```

#### 5.1.3 AnalysisConfig (VO)

```python
@dataclass(frozen=True)
class AnalysisConfig:
    sample_pages: int = 5
    min_text_threshold: int = 50          # 추출 가능 텍스트 최소 문자 수
    ocr_text_ratio_threshold: float = 0.3 # 이하이면 OCR_HEAVY
    table_avg_threshold: float = 2.0      # 이상이면 TABLE_HEAVY
    image_area_threshold: float = 0.4     # multimodal 판단 기준
    image_only_threshold: float = 0.5     # 이미지만 많으면 MULTIMODAL
```

#### 5.1.4 AnalysisResult (Schema)

```python
class AnalysisResult(BaseModel):
    document_type: PDFDocumentType
    confidence: float                     # 0.0 ~ 1.0
    total_pages: int
    sampled_pages: int
    page_features: List[PageFeatures]
    summary_metrics: SummaryMetrics

class SummaryMetrics(BaseModel):
    avg_text_chars: float
    avg_image_count: float
    avg_image_area_ratio: float
    avg_table_count: float
    extractable_text_ratio: float         # 텍스트 추출 가능 페이지 비율
```

#### 5.1.5 PDFAnalyzerInterface (ABC)

```python
class PDFAnalyzerInterface(ABC):
    @abstractmethod
    def analyze_bytes(
        self, file_bytes: bytes, config: Optional[AnalysisConfig] = None
    ) -> AnalysisResult: ...

    @abstractmethod
    def analyze_path(
        self, file_path: str, config: Optional[AnalysisConfig] = None
    ) -> AnalysisResult: ...
```

### 5.2 Application Layer

#### 5.2.1 AnalyzePDFUseCase

```python
class AnalyzePDFUseCase:
    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(self, request: AnalyzePDFRequest) -> AnalyzePDFResponse:
        # 1. 로깅 시작
        # 2. analyzer.analyze_bytes() 또는 analyze_path() 호출
        # 3. AnalysisResult → AnalyzePDFResponse 변환
        # 4. 로깅 완료
```

### 5.3 Infrastructure Layer

#### 5.3.1 PyMuPDFAnalyzer

```python
class PyMuPDFAnalyzer(PDFAnalyzerInterface):
    def analyze_bytes(self, file_bytes, config=None) -> AnalysisResult:
        config = config or AnalysisConfig()
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            total_pages = doc.page_count
            sample_count = min(config.sample_pages, total_pages)
            pages_to_analyze = range(sample_count)

            page_features = []
            for page_idx in pages_to_analyze:
                page = doc[page_idx]
                features = self._extract_features(page, page_idx + 1, config)
                page_features.append(features)

        summary = self._compute_summary(page_features)
        doc_type, confidence = ClassificationPolicy.classify(
            page_features, summary, config
        )

        return AnalysisResult(
            document_type=doc_type,
            confidence=confidence,
            total_pages=total_pages,
            sampled_pages=sample_count,
            page_features=page_features,
            summary_metrics=summary,
        )
```

---

## 6. Implementation Order

| Phase | Task | Files | Dependency |
|-------|------|-------|------------|
| 1 | Domain 스키마/VO 정의 | `domain/pdf_analyzer/schemas.py`, `value_objects.py` | None |
| 2 | Domain 인터페이스 + 분류 정책 | `domain/pdf_analyzer/interfaces.py`, `policies.py` | Phase 1 |
| 3 | Infrastructure 구현 (PyMuPDFAnalyzer) | `infrastructure/pdf_analyzer/pymupdf_analyzer.py` | Phase 2 |
| 4 | Application UseCase | `application/pdf_analyzer/use_case.py`, `schemas.py` | Phase 3 |
| 5 | 테스트 (TDD: 각 Phase에서 테스트 먼저) | `tests/domain/pdf_analyzer/`, `tests/application/pdf_analyzer/`, `tests/infrastructure/pdf_analyzer/` | All |

---

## 7. Testing Strategy

### 7.1 Domain Tests

| Test | Description |
|------|-------------|
| `test_classification_policy_text_heavy` | 텍스트 위주 PageFeatures → TEXT_HEAVY 분류 |
| `test_classification_policy_ocr_heavy` | extractable_text_ratio < 0.3 → OCR_HEAVY |
| `test_classification_policy_table_heavy` | avg_table_count >= 2.0 → TABLE_HEAVY |
| `test_classification_policy_multimodal` | 이미지+표 혼합 → MULTIMODAL |
| `test_analysis_config_defaults` | 기본값 검증 (sample_pages=5) |
| `test_analysis_config_custom` | 커스텀 설정 적용 검증 |

### 7.2 Infrastructure Tests

| Test | Description |
|------|-------------|
| `test_pymupdf_analyzer_text_pdf` | 텍스트 PDF → TEXT_HEAVY |
| `test_pymupdf_analyzer_scanned_pdf` | 스캔 PDF (이미지만) → OCR_HEAVY |
| `test_pymupdf_analyzer_sample_pages` | 10페이지 PDF + sample_pages=3 → 3페이지만 분석 |
| `test_pymupdf_analyzer_short_pdf` | 3페이지 PDF + sample_pages=5 → 전체 분석 |

### 7.3 Application Tests

| Test | Description |
|------|-------------|
| `test_analyze_use_case_success` | 정상 분석 흐름 |
| `test_analyze_use_case_logging` | LOG-001 준수 검증 |
| `test_analyze_use_case_error` | 파서 오류 시 에러 로깅 + 재raise |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| fitz `find_tables()` API가 특정 버전에서만 지원 | 표 감지 불가 | PyMuPDF 1.23.0+ 의존, fallback으로 table_count=0 |
| 5페이지 샘플링이 전체 문서 특성을 대표하지 못함 | 분류 오류 | confidence score로 불확실성 표현, sample_pages 조정 가능 |
| 분류 임계값이 도메인별로 다를 수 있음 | 금융 문서에 부적합 | AnalysisConfig 외부 주입으로 도메인별 튜닝 가능 |
| 대용량 PDF (1000+페이지) 메모리 | OOM | fitz.open() 후 샘플 페이지만 접근, 전체 로드 안 함 |

---

## 9. Future Extensions

| Extension | Description | Trigger |
|-----------|-------------|---------|
| 라우팅 계층 | AnalysisResult → 파서 자동 선택 + 실행 | pdf-analyzer 완료 후 |
| LLM 기반 분류 | rule-based → LLM classifier 교체 | 분류 정확도 개선 필요 시 |
| 표 전용 파서 추가 | Camelot/Tabula 기반 TABLE_HEAVY 파서 | 표 파싱 품질 이슈 시 |
| 샘플링 전략 확장 | 앞 N페이지 → 균등 샘플링, 랜덤 샘플링 | 긴 문서 분류 정확도 이슈 시 |
| 분석 캐싱 | 동일 PDF 재분석 방지 (hash 기반) | 성능 최적화 필요 시 |
