# pdf-analyzer Design Document

> **Summary**: PDF 유형 분류 계층의 전체 코드 수준 상세 설계 — Domain/Application/Infrastructure 레이어별 구현 명세
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-12
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/pdf-analyzer.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `ParserFactory`가 PDF 내용 특성을 모른 채 고정 파서를 사용 — OCR/표/멀티모달 문서 파싱 품질 편차 |
| **Solution** | 3-레이어 `pdf_analyzer` 모듈: domain(4-type enum + 분류 정책) → application(UseCase) → infrastructure(fitz 특성 추출) |
| **Function/UX Effect** | PDF 업로드 시 앞 N페이지 자동 샘플링 → 유형 분류 결과(enum+confidence+metrics)만 반환 → 라우팅 계층이 최적 파서 선택 |
| **Core Value** | 분류와 파싱의 책임 분리 — 파서 추가/교체 시 Analyzer 수정 불필요, 임계값은 AnalysisConfig로 도메인별 튜닝 |

---

## 1. File Structure

```
src/
├── domain/pdf_analyzer/
│   ├── __init__.py
│   ├── schemas.py              # PDFDocumentType, AnalysisResult, SummaryMetrics, PageFeatures
│   ├── value_objects.py         # AnalysisConfig
│   ├── interfaces.py            # PDFAnalyzerInterface (ABC)
│   └── policies.py              # ClassificationPolicy
│
├── application/pdf_analyzer/
│   ├── __init__.py
│   ├── schemas.py               # AnalyzePDFRequest, AnalyzePDFResponse
│   └── use_case.py              # AnalyzePDFUseCase
│
└── infrastructure/pdf_analyzer/
    ├── __init__.py
    └── pymupdf_analyzer.py      # PyMuPDFAnalyzer

tests/
├── domain/pdf_analyzer/
│   ├── __init__.py
│   ├── test_schemas.py
│   ├── test_value_objects.py
│   └── test_policies.py
│
├── application/pdf_analyzer/
│   ├── __init__.py
│   └── test_use_case.py
│
└── infrastructure/pdf_analyzer/
    ├── __init__.py
    └── test_pymupdf_analyzer.py
```

**총 신규 파일**: 프로덕션 10개 + 테스트 6개 = 16개

---

## 2. Domain Layer

### 2.1 `domain/pdf_analyzer/schemas.py`

```python
"""PDF 분석 결과 스키마.

PDFDocumentType, PageFeatures, SummaryMetrics, AnalysisResult 정의.
외부 라이브러리 의존 없음 (pydantic + typing만 사용).
"""
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class PDFDocumentType(str, Enum):
    TEXT_HEAVY = "text_heavy"
    OCR_HEAVY = "ocr_heavy"
    TABLE_HEAVY = "table_heavy"
    MULTIMODAL = "multimodal"


class PageFeatures(BaseModel):
    page_number: int = Field(ge=1)
    text_char_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    image_area_ratio: float = Field(ge=0.0, le=1.0)
    table_count: int = Field(ge=0)
    has_extractable_text: bool

    model_config = {"frozen": True}


class SummaryMetrics(BaseModel):
    avg_text_chars: float = Field(ge=0.0)
    avg_image_count: float = Field(ge=0.0)
    avg_image_area_ratio: float = Field(ge=0.0, le=1.0)
    avg_table_count: float = Field(ge=0.0)
    extractable_text_ratio: float = Field(ge=0.0, le=1.0)

    model_config = {"frozen": True}


class AnalysisResult(BaseModel):
    document_type: PDFDocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    total_pages: int = Field(ge=1)
    sampled_pages: int = Field(ge=1)
    page_features: List[PageFeatures]
    summary_metrics: SummaryMetrics

    model_config = {"frozen": True}
```

**설계 판단**:
- `PageFeatures`를 `dataclass(frozen=True)` 대신 `pydantic.BaseModel(frozen=True)` 사용 — 프로젝트 전체가 pydantic 기반이며, Field validation으로 invariant 보장
- `AnalysisResult`는 불변 — 생성 후 수정 불가, 라우팅 계층에 안전하게 전달

---

### 2.2 `domain/pdf_analyzer/value_objects.py`

```python
"""PDF 분석 설정 값 객체.

AnalysisConfig — 샘플링/분류 임계값 설정.
외부 라이브러리 의존 없음.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisConfig:
    sample_pages: int = 5
    min_text_threshold: int = 50
    ocr_text_ratio_threshold: float = 0.3
    table_avg_threshold: float = 2.0
    image_area_threshold: float = 0.4
    image_only_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.sample_pages < 1:
            raise ValueError("sample_pages must be >= 1")
        if self.min_text_threshold < 0:
            raise ValueError("min_text_threshold must be >= 0")
        if not (0.0 <= self.ocr_text_ratio_threshold <= 1.0):
            raise ValueError("ocr_text_ratio_threshold must be 0.0~1.0")
        if self.table_avg_threshold < 0.0:
            raise ValueError("table_avg_threshold must be >= 0.0")
        if not (0.0 <= self.image_area_threshold <= 1.0):
            raise ValueError("image_area_threshold must be 0.0~1.0")
        if not (0.0 <= self.image_only_threshold <= 1.0):
            raise ValueError("image_only_threshold must be 0.0~1.0")
```

**설계 판단**:
- `dataclass(frozen=True)` 사용 — 기존 `domain/parser/value_objects.py`의 `ParserConfig`와 동일 패턴 유지
- `__post_init__`에서 모든 invariant 검증 — 잘못된 설정이 policy까지 전파되지 않도록 방어

---

### 2.3 `domain/pdf_analyzer/interfaces.py`

```python
"""PDF 분석기 인터페이스.

Infrastructure 레이어에서 구현할 추상 계약.
"""
from abc import ABC, abstractmethod
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class PDFAnalyzerInterface(ABC):

    @abstractmethod
    def analyze_bytes(
        self,
        file_bytes: bytes,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        pass

    @abstractmethod
    def analyze_path(
        self,
        file_path: str,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        pass
```

**설계 판단**:
- 기존 `PDFParserInterface`와 동일한 bytes/path 이중 메서드 패턴
- 동기 메서드 — fitz는 CPU-bound이므로 UseCase에서 `asyncio.to_thread`로 감싸서 호출 (기존 `PDFParseUseCase` 패턴 동일)

---

### 2.4 `domain/pdf_analyzer/policies.py`

```python
"""PDF 유형 분류 정책.

Rule-based 분류 로직. 임계값은 AnalysisConfig에서 주입.
LLM 기반 분류로 교체 시 이 파일만 변경.
"""
from typing import List, Tuple

from src.domain.pdf_analyzer.schemas import (
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class ClassificationPolicy:

    @staticmethod
    def classify(
        page_features: List[PageFeatures],
        summary: SummaryMetrics,
        config: AnalysisConfig,
    ) -> Tuple[PDFDocumentType, float]:
        if not page_features:
            return PDFDocumentType.TEXT_HEAVY, 0.0

        # Priority 1: OCR_HEAVY — 대부분 텍스트 추출 불가
        if summary.extractable_text_ratio < config.ocr_text_ratio_threshold:
            confidence = 1.0 - summary.extractable_text_ratio
            return PDFDocumentType.OCR_HEAVY, round(confidence, 2)

        # Priority 2: TABLE_HEAVY — 페이지당 평균 표 개수 높음
        if summary.avg_table_count >= config.table_avg_threshold:
            confidence = min(summary.avg_table_count / 5.0, 1.0)
            return PDFDocumentType.TABLE_HEAVY, round(confidence, 2)

        # Priority 3: MULTIMODAL — 이미지+표 혼합 또는 이미지 비중 높음
        if (
            summary.avg_image_area_ratio > config.image_area_threshold
            and summary.avg_table_count >= 1.0
        ):
            confidence = (
                summary.avg_image_area_ratio * 0.6
                + min(summary.avg_table_count / 3.0, 1.0) * 0.4
            )
            return PDFDocumentType.MULTIMODAL, round(min(confidence, 1.0), 2)

        if summary.avg_image_area_ratio > config.image_only_threshold:
            confidence = summary.avg_image_area_ratio
            return PDFDocumentType.MULTIMODAL, round(confidence, 2)

        # Default: TEXT_HEAVY
        confidence = summary.extractable_text_ratio
        return PDFDocumentType.TEXT_HEAVY, round(confidence, 2)

    @staticmethod
    def compute_summary(page_features: List[PageFeatures]) -> SummaryMetrics:
        if not page_features:
            return SummaryMetrics(
                avg_text_chars=0.0,
                avg_image_count=0.0,
                avg_image_area_ratio=0.0,
                avg_table_count=0.0,
                extractable_text_ratio=0.0,
            )

        n = len(page_features)
        return SummaryMetrics(
            avg_text_chars=sum(p.text_char_count for p in page_features) / n,
            avg_image_count=sum(p.image_count for p in page_features) / n,
            avg_image_area_ratio=sum(p.image_area_ratio for p in page_features) / n,
            avg_table_count=sum(p.table_count for p in page_features) / n,
            extractable_text_ratio=sum(
                1 for p in page_features if p.has_extractable_text
            ) / n,
        )
```

**설계 판단**:
- `classify`와 `compute_summary` 모두 `@staticmethod` — 상태 없는 순수 함수, 테스트 용이
- confidence 계산: 각 유형별로 가장 강한 시그널 기반 (OCR → 텍스트 부재 비율, TABLE → 표 밀도, MULTIMODAL → 이미지+표 가중 평균)
- 분류 우선순위: OCR > TABLE > MULTIMODAL > TEXT (Plan 4.3 정의와 일치)

---

## 3. Application Layer

### 3.1 `application/pdf_analyzer/schemas.py`

```python
"""PDF 분석 요청/응답 스키마.

UseCase 입출력용 DTO.
"""
from typing import Optional

from pydantic import BaseModel, field_validator


class AnalyzePDFRequest(BaseModel):
    filename: str
    user_id: str
    request_id: str
    file_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    sample_pages: Optional[int] = None

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class AnalyzePDFResponse(BaseModel):
    document_type: str
    confidence: float
    total_pages: int
    sampled_pages: int
    avg_text_chars: float
    avg_image_count: float
    avg_image_area_ratio: float
    avg_table_count: float
    extractable_text_ratio: float
    request_id: str
```

**설계 판단**:
- `AnalyzePDFRequest`는 기존 `ParseDocumentRequest`와 동일 validator 패턴
- `AnalyzePDFResponse`는 `AnalysisResult`를 평탄화 — 라우팅 계층이 소비하기 쉬운 flat 구조
- `document_type`을 `str`로 반환 — API 경계에서 enum 직렬화 이슈 방지
- `sample_pages`를 Optional로 받아 호출측에서 동적 조정 가능 (FR-05)

---

### 3.2 `application/pdf_analyzer/use_case.py`

```python
"""PDF 분석 UseCase.

PDF 파일의 유형을 분석하여 분류 결과를 반환.
LOG-001 준수: 시작/완료/실패 로깅.
"""
import asyncio
from typing import Optional

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.application.pdf_analyzer.schemas import AnalyzePDFRequest, AnalyzePDFResponse


class AnalyzePDFUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        logger: LoggerInterface,
    ) -> None:
        self._analyzer = analyzer
        self._logger = logger

    async def execute(
        self,
        request: AnalyzePDFRequest,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalyzePDFResponse:
        if config is None and request.sample_pages is not None:
            config = AnalysisConfig(sample_pages=request.sample_pages)

        self._logger.info(
            "PDF analysis started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            sample_pages=config.sample_pages if config else 5,
        )

        try:
            if request.file_bytes is not None:
                result = await asyncio.to_thread(
                    self._analyzer.analyze_bytes,
                    file_bytes=request.file_bytes,
                    config=config,
                )
            elif request.file_path is not None:
                result = await asyncio.to_thread(
                    self._analyzer.analyze_path,
                    file_path=request.file_path,
                    config=config,
                )
            else:
                raise ValueError(
                    "Either file_bytes or file_path must be provided"
                )
        except Exception as exc:
            self._logger.error(
                "PDF analysis failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise

        self._logger.info(
            "PDF analysis completed",
            request_id=request.request_id,
            filename=request.filename,
            document_type=result.document_type.value,
            confidence=result.confidence,
            total_pages=result.total_pages,
            sampled_pages=result.sampled_pages,
        )

        return AnalyzePDFResponse(
            document_type=result.document_type.value,
            confidence=result.confidence,
            total_pages=result.total_pages,
            sampled_pages=result.sampled_pages,
            avg_text_chars=result.summary_metrics.avg_text_chars,
            avg_image_count=result.summary_metrics.avg_image_count,
            avg_image_area_ratio=result.summary_metrics.avg_image_area_ratio,
            avg_table_count=result.summary_metrics.avg_table_count,
            extractable_text_ratio=result.summary_metrics.extractable_text_ratio,
            request_id=request.request_id,
        )
```

**설계 판단**:
- `asyncio.to_thread` — 기존 `PDFParseUseCase` 패턴과 동일, fitz CPU-bound 작업을 이벤트 루프에서 분리
- `config` 이중 주입: `request.sample_pages`로 간편 조정 또는 `AnalysisConfig` 직접 전달
- 에러 처리: LOG-001 준수 (error + exception + re-raise)

---

## 4. Infrastructure Layer

### 4.1 `infrastructure/pdf_analyzer/pymupdf_analyzer.py`

```python
"""PyMuPDF 기반 PDF 분석기.

fitz 라이브러리로 페이지별 특성(텍스트/이미지/표)을 추출.
PyMuPDF >= 1.24.0 (find_tables() 지원).
"""
from typing import List, Optional

import fitz

from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.policies import ClassificationPolicy
from src.domain.pdf_analyzer.schemas import AnalysisResult, PageFeatures
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class PyMuPDFAnalyzer(PDFAnalyzerInterface):

    def analyze_bytes(
        self,
        file_bytes: bytes,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        config = config or AnalysisConfig()
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return self._analyze_document(doc, config)

    def analyze_path(
        self,
        file_path: str,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        config = config or AnalysisConfig()
        with fitz.open(file_path) as doc:
            return self._analyze_document(doc, config)

    def _analyze_document(
        self,
        doc: fitz.Document,
        config: AnalysisConfig,
    ) -> AnalysisResult:
        total_pages = doc.page_count
        sample_count = min(config.sample_pages, total_pages)

        page_features: List[PageFeatures] = []
        for page_idx in range(sample_count):
            page = doc[page_idx]
            features = self._extract_page_features(page, page_idx + 1, config)
            page_features.append(features)

        summary = ClassificationPolicy.compute_summary(page_features)
        document_type, confidence = ClassificationPolicy.classify(
            page_features, summary, config,
        )

        return AnalysisResult(
            document_type=document_type,
            confidence=confidence,
            total_pages=total_pages,
            sampled_pages=sample_count,
            page_features=page_features,
            summary_metrics=summary,
        )

    def _extract_page_features(
        self,
        page: fitz.Page,
        page_number: int,
        config: AnalysisConfig,
    ) -> PageFeatures:
        text = page.get_text()
        text_char_count = len(text.strip())

        images = page.get_images(full=True)
        image_count = len(images)
        image_area_ratio = self._compute_image_area_ratio(page, images)

        table_count = self._count_tables(page)

        has_extractable_text = text_char_count >= config.min_text_threshold

        return PageFeatures(
            page_number=page_number,
            text_char_count=text_char_count,
            image_count=image_count,
            image_area_ratio=round(image_area_ratio, 4),
            table_count=table_count,
            has_extractable_text=has_extractable_text,
        )

    def _compute_image_area_ratio(
        self,
        page: fitz.Page,
        images: list,
    ) -> float:
        if not images:
            return 0.0

        page_rect = page.rect
        page_area = page_rect.width * page_rect.height
        if page_area <= 0:
            return 0.0

        total_image_area = 0.0
        for img in images:
            xref = img[0]
            try:
                img_rects = page.get_image_rects(xref)
                for rect in img_rects:
                    total_image_area += rect.width * rect.height
            except Exception:
                pass

        ratio = total_image_area / page_area
        return min(ratio, 1.0)

    def _count_tables(self, page: fitz.Page) -> int:
        try:
            tables = page.find_tables()
            return len(tables.tables)
        except Exception:
            return 0
```

**설계 판단**:

1. **`_analyze_document` 내부 메서드**: `analyze_bytes`/`analyze_path`의 중복 제거 — fitz.open 방식만 다르고 이후 로직 동일
2. **`_compute_image_area_ratio`**: `page.get_image_rects(xref)`로 이미지 실제 렌더링 영역 계산 — `get_images()`만으로는 면적 알 수 없음
3. **`_count_tables`**: `page.find_tables()` 사용 (PyMuPDF 1.23.0+), 실패 시 0 반환 — 구버전 fallback
4. **`image_area_ratio`를 `min(ratio, 1.0)`로 클램핑**: 이미지 겹침으로 1.0 초과 가능

---

## 5. Dependency Map

```
domain/pdf_analyzer/
├── schemas.py          ← (의존 없음, pydantic만)
├── value_objects.py    ← (의존 없음, dataclass만)
├── interfaces.py       ← schemas, value_objects
└── policies.py         ← schemas, value_objects

application/pdf_analyzer/
├── schemas.py          ← (의존 없음, pydantic만)
└── use_case.py         ← domain/pdf_analyzer/interfaces
                        ← domain/pdf_analyzer/value_objects
                        ← domain/logging/interfaces/logger_interface
                        ← application/pdf_analyzer/schemas

infrastructure/pdf_analyzer/
└── pymupdf_analyzer.py ← domain/pdf_analyzer/interfaces
                        ← domain/pdf_analyzer/policies
                        ← domain/pdf_analyzer/schemas
                        ← domain/pdf_analyzer/value_objects
                        ← fitz (PyMuPDF)
                        ← infrastructure/logging
```

**레이어 의존 방향**: `infrastructure → domain ← application` (Thin DDD 준수)

---

## 6. Implementation Order (TDD)

| Step | Layer | File | Test File | Description |
|------|-------|------|-----------|-------------|
| 1 | domain | `schemas.py` | `test_schemas.py` | PDFDocumentType enum, PageFeatures, SummaryMetrics, AnalysisResult 모델 정의 + validation 테스트 |
| 2 | domain | `value_objects.py` | `test_value_objects.py` | AnalysisConfig 기본값/커스텀값/validation 테스트 |
| 3 | domain | `interfaces.py` | - | PDFAnalyzerInterface ABC (테스트 불필요 — 추상 클래스) |
| 4 | domain | `policies.py` | `test_policies.py` | ClassificationPolicy.classify + compute_summary — 4유형 분류 규칙 테스트 |
| 5 | infra | `pymupdf_analyzer.py` | `test_pymupdf_analyzer.py` | PyMuPDFAnalyzer — 실제 fitz로 특성 추출 + 분류 통합 테스트 |
| 6 | app | `schemas.py` | - | AnalyzePDFRequest/Response DTO (validator는 기존 패턴 동일) |
| 7 | app | `use_case.py` | `test_use_case.py` | AnalyzePDFUseCase — mock analyzer + 로깅 검증 |

---

## 7. Test Specifications

### 7.1 Domain — `test_schemas.py`

```python
def test_pdf_document_type_values():
    """4가지 유형 enum 값 확인"""
    assert PDFDocumentType.TEXT_HEAVY.value == "text_heavy"
    assert PDFDocumentType.OCR_HEAVY.value == "ocr_heavy"
    assert PDFDocumentType.TABLE_HEAVY.value == "table_heavy"
    assert PDFDocumentType.MULTIMODAL.value == "multimodal"

def test_page_features_validation():
    """page_number < 1, image_area_ratio > 1.0 등 거부"""

def test_page_features_frozen():
    """생성 후 속성 변경 시 에러"""

def test_analysis_result_construction():
    """정상 생성 + 모든 필드 접근"""
```

### 7.2 Domain — `test_value_objects.py`

```python
def test_analysis_config_defaults():
    """기본값: sample_pages=5, min_text_threshold=50"""
    config = AnalysisConfig()
    assert config.sample_pages == 5
    assert config.min_text_threshold == 50

def test_analysis_config_custom():
    """커스텀 값 적용"""
    config = AnalysisConfig(sample_pages=10, min_text_threshold=100)
    assert config.sample_pages == 10

def test_analysis_config_invalid_sample_pages():
    """sample_pages=0 → ValueError"""
    with pytest.raises(ValueError):
        AnalysisConfig(sample_pages=0)

def test_analysis_config_invalid_threshold():
    """ocr_text_ratio_threshold=1.5 → ValueError"""
    with pytest.raises(ValueError):
        AnalysisConfig(ocr_text_ratio_threshold=1.5)
```

### 7.3 Domain — `test_policies.py`

```python
def test_classify_text_heavy():
    """텍스트 위주 페이지 → TEXT_HEAVY"""
    features = [
        PageFeatures(page_number=1, text_char_count=2000, image_count=0,
                     image_area_ratio=0.0, table_count=0, has_extractable_text=True),
        # ... 5 pages similar
    ]
    summary = ClassificationPolicy.compute_summary(features)
    doc_type, conf = ClassificationPolicy.classify(features, summary, AnalysisConfig())
    assert doc_type == PDFDocumentType.TEXT_HEAVY
    assert conf > 0.5

def test_classify_ocr_heavy():
    """텍스트 추출 불가 페이지 비율 > 70% → OCR_HEAVY"""
    features = [
        PageFeatures(page_number=i, text_char_count=10, image_count=1,
                     image_area_ratio=0.9, table_count=0, has_extractable_text=False)
        for i in range(1, 6)
    ]
    summary = ClassificationPolicy.compute_summary(features)
    doc_type, _ = ClassificationPolicy.classify(features, summary, AnalysisConfig())
    assert doc_type == PDFDocumentType.OCR_HEAVY

def test_classify_table_heavy():
    """페이지당 평균 표 2개 이상 → TABLE_HEAVY"""
    features = [
        PageFeatures(page_number=i, text_char_count=500, image_count=0,
                     image_area_ratio=0.0, table_count=3, has_extractable_text=True)
        for i in range(1, 6)
    ]
    summary = ClassificationPolicy.compute_summary(features)
    doc_type, _ = ClassificationPolicy.classify(features, summary, AnalysisConfig())
    assert doc_type == PDFDocumentType.TABLE_HEAVY

def test_classify_multimodal():
    """이미지 면적 > 40% + 표 >= 1 → MULTIMODAL"""
    features = [
        PageFeatures(page_number=i, text_char_count=300, image_count=2,
                     image_area_ratio=0.5, table_count=1, has_extractable_text=True)
        for i in range(1, 6)
    ]
    summary = ClassificationPolicy.compute_summary(features)
    doc_type, _ = ClassificationPolicy.classify(features, summary, AnalysisConfig())
    assert doc_type == PDFDocumentType.MULTIMODAL

def test_classify_empty_features():
    """빈 리스트 → TEXT_HEAVY, confidence=0.0"""
    doc_type, conf = ClassificationPolicy.classify([], SummaryMetrics(...), AnalysisConfig())
    assert doc_type == PDFDocumentType.TEXT_HEAVY
    assert conf == 0.0

def test_compute_summary():
    """평균 메트릭 계산 정확성"""
    features = [
        PageFeatures(page_number=1, text_char_count=100, image_count=2,
                     image_area_ratio=0.3, table_count=1, has_extractable_text=True),
        PageFeatures(page_number=2, text_char_count=200, image_count=0,
                     image_area_ratio=0.1, table_count=0, has_extractable_text=True),
    ]
    summary = ClassificationPolicy.compute_summary(features)
    assert summary.avg_text_chars == 150.0
    assert summary.avg_image_count == 1.0
    assert summary.extractable_text_ratio == 1.0

def test_classify_custom_config():
    """커스텀 임계값 적용 — table_avg_threshold=1.0 → 더 쉽게 TABLE_HEAVY"""
    config = AnalysisConfig(table_avg_threshold=1.0)
    features = [
        PageFeatures(page_number=i, text_char_count=500, image_count=0,
                     image_area_ratio=0.0, table_count=1, has_extractable_text=True)
        for i in range(1, 6)
    ]
    summary = ClassificationPolicy.compute_summary(features)
    doc_type, _ = ClassificationPolicy.classify(features, summary, config)
    assert doc_type == PDFDocumentType.TABLE_HEAVY
```

### 7.4 Infrastructure — `test_pymupdf_analyzer.py`

```python
# 테스트용 PDF 생성 헬퍼 (fitz로 in-memory PDF 생성)

def _create_text_pdf(pages: int = 5) -> bytes:
    """텍스트만 있는 PDF 생성"""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1} " + "텍스트 내용 " * 50)
    data = doc.tobytes()
    doc.close()
    return data

def _create_image_pdf(pages: int = 5) -> bytes:
    """이미지만 있는 PDF 생성 (텍스트 없음)"""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        # 전체 페이지 크기 이미지 삽입
        img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), 1)
        img.set_rect(img.irect, (255, 0, 0))
        page.insert_image(page.rect, pixmap=img)
    data = doc.tobytes()
    doc.close()
    return data

def test_analyze_text_pdf():
    """텍스트 PDF → TEXT_HEAVY"""
    analyzer = PyMuPDFAnalyzer()
    pdf_bytes = _create_text_pdf()
    result = analyzer.analyze_bytes(pdf_bytes)
    assert result.document_type == PDFDocumentType.TEXT_HEAVY
    assert result.sampled_pages == 5
    assert result.total_pages == 5
    assert result.confidence > 0.0

def test_analyze_image_pdf():
    """이미지만 PDF → OCR_HEAVY"""
    analyzer = PyMuPDFAnalyzer()
    pdf_bytes = _create_image_pdf()
    result = analyzer.analyze_bytes(pdf_bytes)
    assert result.document_type == PDFDocumentType.OCR_HEAVY

def test_analyze_sample_pages_limit():
    """10페이지 PDF + sample_pages=3 → 3페이지만 분석"""
    analyzer = PyMuPDFAnalyzer()
    pdf_bytes = _create_text_pdf(pages=10)
    config = AnalysisConfig(sample_pages=3)
    result = analyzer.analyze_bytes(pdf_bytes, config=config)
    assert result.sampled_pages == 3
    assert result.total_pages == 10
    assert len(result.page_features) == 3

def test_analyze_short_pdf():
    """2페이지 PDF + sample_pages=5 → 전체 2페이지 분석"""
    analyzer = PyMuPDFAnalyzer()
    pdf_bytes = _create_text_pdf(pages=2)
    result = analyzer.analyze_bytes(pdf_bytes)
    assert result.sampled_pages == 2
    assert result.total_pages == 2

def test_analyze_from_path(tmp_path):
    """file_path 기반 분석"""
    pdf_bytes = _create_text_pdf()
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(pdf_bytes)
    analyzer = PyMuPDFAnalyzer()
    result = analyzer.analyze_path(str(pdf_file))
    assert result.document_type == PDFDocumentType.TEXT_HEAVY

def test_page_features_extraction():
    """개별 PageFeatures 필드 검증"""
    analyzer = PyMuPDFAnalyzer()
    pdf_bytes = _create_text_pdf(pages=1)
    result = analyzer.analyze_bytes(pdf_bytes, config=AnalysisConfig(sample_pages=1))
    pf = result.page_features[0]
    assert pf.page_number == 1
    assert pf.text_char_count > 0
    assert pf.has_extractable_text is True
    assert 0.0 <= pf.image_area_ratio <= 1.0
```

### 7.5 Application — `test_use_case.py`

```python
@pytest.fixture
def mock_analyzer():
    analyzer = Mock(spec=PDFAnalyzerInterface)
    analyzer.analyze_bytes.return_value = AnalysisResult(
        document_type=PDFDocumentType.TEXT_HEAVY,
        confidence=0.95,
        total_pages=10,
        sampled_pages=5,
        page_features=[...],  # 5개 PageFeatures
        summary_metrics=SummaryMetrics(
            avg_text_chars=1500.0,
            avg_image_count=0.0,
            avg_image_area_ratio=0.0,
            avg_table_count=0.0,
            extractable_text_ratio=1.0,
        ),
    )
    return analyzer

@pytest.fixture
def mock_logger():
    return Mock(spec=LoggerInterface)

@pytest.mark.asyncio
async def test_execute_success(mock_analyzer, mock_logger):
    """정상 분석 → AnalyzePDFResponse 반환"""
    use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
    request = AnalyzePDFRequest(
        filename="test.pdf",
        user_id="user1",
        request_id="req1",
        file_bytes=b"fake-pdf",
    )
    response = await use_case.execute(request)
    assert response.document_type == "text_heavy"
    assert response.confidence == 0.95
    mock_analyzer.analyze_bytes.assert_called_once()

@pytest.mark.asyncio
async def test_execute_logging(mock_analyzer, mock_logger):
    """LOG-001: info 2회 (started + completed)"""
    use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
    request = AnalyzePDFRequest(
        filename="test.pdf", user_id="user1",
        request_id="req1", file_bytes=b"fake-pdf",
    )
    await use_case.execute(request)
    assert mock_logger.info.call_count == 2

@pytest.mark.asyncio
async def test_execute_error_logging(mock_logger):
    """에러 시 error 로깅 + re-raise"""
    analyzer = Mock(spec=PDFAnalyzerInterface)
    analyzer.analyze_bytes.side_effect = RuntimeError("parse error")
    use_case = AnalyzePDFUseCase(analyzer=analyzer, logger=mock_logger)
    request = AnalyzePDFRequest(
        filename="test.pdf", user_id="user1",
        request_id="req1", file_bytes=b"fake-pdf",
    )
    with pytest.raises(RuntimeError):
        await use_case.execute(request)
    mock_logger.error.assert_called_once()

@pytest.mark.asyncio
async def test_execute_no_input_raises(mock_analyzer, mock_logger):
    """file_bytes와 file_path 둘 다 없으면 ValueError"""
    use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
    request = AnalyzePDFRequest(
        filename="test.pdf", user_id="user1", request_id="req1",
    )
    with pytest.raises(ValueError, match="Either file_bytes or file_path"):
        await use_case.execute(request)

@pytest.mark.asyncio
async def test_execute_with_sample_pages(mock_analyzer, mock_logger):
    """request.sample_pages → AnalysisConfig 자동 생성"""
    use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
    request = AnalyzePDFRequest(
        filename="test.pdf", user_id="user1",
        request_id="req1", file_bytes=b"fake-pdf",
        sample_pages=3,
    )
    await use_case.execute(request)
    call_kwargs = mock_analyzer.analyze_bytes.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert config.sample_pages == 3
```

---

## 8. Error Handling

| Scenario | Handler | Action |
|----------|---------|--------|
| file_bytes/file_path 둘 다 없음 | UseCase | `ValueError` raise |
| fitz.open 실패 (깨진 PDF) | PyMuPDFAnalyzer | exception propagate → UseCase에서 로깅 |
| find_tables() 지원 안 되는 fitz 버전 | `_count_tables` | `try/except → return 0` |
| get_image_rects 실패 | `_compute_image_area_ratio` | `try/except → skip image` |
| 빈 PDF (0페이지) | PyMuPDFAnalyzer | `fitz.open()` 시 예외 → UseCase에서 처리 |
| AnalysisConfig 잘못된 값 | `__post_init__` | `ValueError` 즉시 raise |

---

## 9. Integration Points

### 9.1 현재 파서 인프라와의 관계 (참조만, 수정 없음)

```
현재 파이프라인:              향후 라우팅 파이프라인 (Out of Scope):
─────────────────           ────────────────────────────────────
PDF → ParserFactory          PDF → AnalyzePDFUseCase
     → PyMuPDFParser              → AnalysisResult
     → Document[]                 → Router(AnalysisResult)
                                       → TEXT_HEAVY → PyMuPDFParser
                                       → OCR_HEAVY  → LlamaParser
                                       → TABLE_HEAVY → CamelotParser
                                       → MULTIMODAL  → LlamaParser
```

### 9.2 DI 등록 (향후 router에서 연결 시)

```python
# 향후 src/api/dependencies.py에 추가 예정
def get_pdf_analyzer() -> PDFAnalyzerInterface:
    return PyMuPDFAnalyzer()

def get_analyze_pdf_use_case(
    analyzer: PDFAnalyzerInterface = Depends(get_pdf_analyzer),
    logger: LoggerInterface = Depends(get_logger),
) -> AnalyzePDFUseCase:
    return AnalyzePDFUseCase(analyzer=analyzer, logger=logger)
```

> DI 등록은 이 feature의 scope 밖 — 라우팅 계층 구현 시 함께 추가.
