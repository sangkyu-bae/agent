# advanced-document-parser Design Document

> **Summary**: 좌표 기반 PDF 요소 추출 → 레이아웃 분석 → 구조화 → 품질 검증 → fallback → section-aware 청킹 파이프라인 상세 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft
> **Planning Doc**: [advanced-document-parser.plan.md](../01-plan/features/advanced-document-parser.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `page.get_text()`/`to_markdown()`의 단순 텍스트 추출로 헤더/푸터 노이즈, 읽기 순서 깨짐, 표 구조 소실, 품질 검증·fallback 부재 |
| **Solution** | 좌표 기반 요소 추출 → 7단계 layout 분석 파이프라인 → 품질 점수 기반 fallback → section-aware 청킹 |
| **Function/UX Effect** | 금융 규정 표가 의미 문장으로 변환, 파싱 실패 자동 복구, 검색 결과에 페이지·섹션·표 출처 정확 표시 |
| **Core Value** | "단순 텍스트 추출"에서 "좌표 기반 구조 분석 + 품질 검증 + 적응적 처리"로 전환 |

---

## 1. Overview

### 1.1 Design Goals

1. **기존 인터페이스 유지**: `PDFParserInterface`, `ChunkingStrategy` 변경 없음 — 기존 파서/청킹 전략 호환
2. **parse_node 내부 확장**: LangGraph 파이프라인의 `parse → classify → chunk → store` 흐름 불변, parse 내부에서 layout 분석 실행
3. **단계별 독립 모듈**: layout/ 패키지의 각 모듈이 단일 책임, 독립 테스트 가능
4. **품질 기반 방어**: 품질 점수 0.7 미만 시 자동 fallback으로 파싱 실패 방지
5. **금융 도메인 특화**: 표 의미 문장 생성에서 금리/한도/등급 컨텍스트 보존

### 1.2 Design Principles

- **Single Responsibility**: 각 layout 모듈은 하나의 변환 책임만 담당
- **Open-Closed**: 새 모듈 추가 시 기존 모듈 수정 불필요 (파이프라인에 추가만)
- **Dependency Inversion**: domain VO는 infrastructure 의존 없음, infrastructure가 domain VO를 생성
- **Fail-Safe**: 각 단계 실패 시 이전 단계 결과로 graceful degradation

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline (기존)                         │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │  parse   │──▶│ classify │──▶│  chunk   │──▶│  store   │        │
│  └────┬─────┘   └──────────┘   └────┬─────┘   └──────────┘        │
│       │                              │                              │
│       ▼ (내부 확장)                   ▼ (신규 전략 추가)              │
│  ┌─────────────────────┐      ┌─────────────────────┐              │
│  │ LayoutAnalyzer      │      │ SectionAwareStrategy│              │
│  │ (오케스트레이터)      │      │ (섹션 기반 청킹)     │              │
│  │                     │      └─────────────────────┘              │
│  │ ElementExtractor    │                                           │
│  │ NoiseRemover        │      ┌─────────────────────┐              │
│  │ ColumnDetector      │      │ FallbackParser      │              │
│  │ ReadingOrder        │      │ (품질 기반 전환)      │              │
│  │ TableHandler        │      └─────────────────────┘              │
│  │ SectionBuilder      │                                           │
│  │ QualityScorer       │                                           │
│  └─────────────────────┘                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Assignment

```
domain/parser/
├── interfaces.py              # PDFParserInterface (변경 없음)
├── value_objects.py           # ParserConfig, DocumentMetadata (변경 없음)
├── document_element.py        # ★ BoundingBox, BlockType, DocumentElement
├── parse_quality.py           # ★ ParseQualityScore
├── section_tree.py            # ★ SectionNode
└── layout_interfaces.py       # ★ LayoutAnalyzerInterface (ABC)

domain/chunking/
├── interfaces.py              # ChunkingStrategy (변경 없음)
└── value_objects.py           # ChunkingConfig, ChunkMetadata (변경 없음)

infrastructure/parser/
├── pymupdf_parser.py          # 기존 유지 (fallback primary)
├── pymupdf4llm_parser.py      # page_chunks=True 개선 (Phase 1)
├── llamaparser.py             # 기존 유지 (fallback tertiary)
├── docling_parser.py          # ★ Phase 3 추가
├── parser_factory.py          # ParserType에 DOCLING 추가
│
├── layout/                    # ★ 신규 패키지 전체
│   ├── __init__.py
│   ├── element_extractor.py
│   ├── noise_remover.py
│   ├── column_detector.py
│   ├── reading_order.py
│   ├── table_handler.py
│   ├── section_builder.py
│   ├── quality_scorer.py
│   └── layout_analyzer.py     # 오케스트레이터 (7단계 조합)
│
└── fallback_parser.py         # ★ 품질 기반 fallback 오케스트레이터

infrastructure/chunking/
├── chunking_factory.py        # StrategyType에 SECTION_AWARE 추가
└── strategies/
    └── section_aware_strategy.py  # ★ 신규
```

### 2.3 Data Flow (상세)

```
[PDF bytes]
    │
    ▼
FallbackParser.parse_with_fallback()
    │
    ├── Attempt 1: LayoutAnalyzer (PyMuPDF 기반)
    │   │
    │   ▼
    │   1. ElementExtractor.extract(page)
    │   │  fitz.Page.get_text("dict") → List[DocumentElement]
    │   │  블록/라인/스팬 순회, bbox + font_size + text 추출
    │   │
    │   ▼
    │   2. NoiseRemover.remove(pages_elements, page_height)
    │   │  상단 10% / 하단 10% 영역 후보 → 전체 페이지 60%+ 반복 텍스트 제거
    │   │
    │   ▼
    │   3. ColumnDetector.detect(elements, page_width)
    │   │  x좌표 분포 분석 → LayoutType(SINGLE|DOUBLE|MIXED)
    │   │
    │   ▼
    │   4. ReadingOrderReconstructor.reconstruct(elements, layout_type)
    │   │  컬럼별 y→x 정렬, full-width 블록은 zone 분리자 역할
    │   │
    │   ▼
    │   5. TableHandler.process(elements, section_title)
    │   │  표 영역 감지 → markdown 보존 + 행별 의미 문장 생성
    │   │
    │   ▼
    │   6. SectionBuilder.build(elements, page_height)
    │   │  font_size 기반 heading 감지 → section_title 부여 → 트리 구성
    │   │
    │   ▼
    │   7. QualityScorer.score(elements, page_height)
    │      텍스트량 + 단어 길이 + 순서 일관성 → score 0.0~1.0
    │
    │   score >= 0.7 → List[Document] 반환
    │   score < 0.7 ──┐
    │                  │
    ├── Attempt 2: DoclingParser (Phase 3)
    │   score < 0.7 ──┐
    │                  │
    └── Attempt 3: LlamaParserAdapter (유료, 최종 fallback)
         │
         ▼
    List[Document] (with enriched metadata)
         │
         ▼
    classify_node → chunk_node (SectionAwareStrategy) → store_node
```

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| LayoutAnalyzer | ElementExtractor, NoiseRemover, ColumnDetector, ReadingOrder, TableHandler, SectionBuilder, QualityScorer | 7단계 오케스트레이션 |
| FallbackParser | LayoutAnalyzer, DoclingParser, LlamaParserAdapter, QualityScorer, LoggerInterface | 품질 기반 파서 전환 |
| SectionAwareStrategy | BaseTokenChunker, ChunkingConfig | 섹션/표 인식 청킹 |
| ElementExtractor | fitz (PyMuPDF), DocumentElement (domain VO) | 좌표 기반 요소 추출 |
| TableHandler | DocumentElement | 표 → markdown + 의미 문장 |
| QualityScorer | DocumentElement, ParseQualityScore (domain VO) | 품질 점수 산출 |

---

## 3. Data Model

### 3.1 Domain Value Objects (신규)

#### 3.1.1 BoundingBox

```python
# domain/parser/document_element.py

@dataclass(frozen=True)
class BoundingBox:
    """PDF 페이지 내 요소의 좌표 영역."""
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0:
            raise ValueError("x1 must be >= x0")
        if self.y1 < self.y0:
            raise ValueError("y1 must be >= y0")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        return self.width * self.height

    def is_within_top_ratio(self, page_height: float, ratio: float = 0.10) -> bool:
        """요소가 페이지 상단 ratio 영역 안에 있는지 판단."""
        return self.y1 <= page_height * ratio

    def is_within_bottom_ratio(self, page_height: float, ratio: float = 0.90) -> bool:
        """요소가 페이지 하단 ratio 영역 안에 있는지 판단."""
        return self.y0 >= page_height * ratio
```

#### 3.1.2 DocumentElement

```python
# domain/parser/document_element.py

from typing import Literal

BlockType = Literal[
    "title", "heading", "paragraph", "table", "table_row",
    "header", "footer", "footnote", "figure_caption", "reference",
    "list_item", "page_number",
]

@dataclass(frozen=True)
class DocumentElement:
    """PDF 페이지에서 추출한 원자 요소."""
    page_no: int
    text: str
    bbox: BoundingBox
    block_type: BlockType
    section_title: str = ""
    reading_order: int = 0
    font_size: float = 0.0
    is_bold: bool = False
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError("page_no must be >= 1")
        if not isinstance(self.bbox, BoundingBox):
            raise TypeError("bbox must be a BoundingBox instance")
```

#### 3.1.3 ParseQualityScore

```python
# domain/parser/parse_quality.py

@dataclass(frozen=True)
class ParseQualityScore:
    """파싱 결과 품질 점수."""
    page: int
    score: float                    # 0.0 ~ 1.0
    text_char_count: int
    avg_word_length: float
    order_consistency: float        # 0.0 ~ 1.0
    issues: tuple[str, ...]         # immutable list of issue codes

    FALLBACK_THRESHOLD: ClassVar[float] = 0.7

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError("score must be between 0.0 and 1.0")
        if not (0.0 <= self.order_consistency <= 1.0):
            raise ValueError("order_consistency must be between 0.0 and 1.0")

    @property
    def fallback_required(self) -> bool:
        return self.score < self.FALLBACK_THRESHOLD
```

#### 3.1.4 SectionNode

```python
# domain/parser/section_tree.py

@dataclass
class SectionNode:
    """문서 섹션 트리의 노드."""
    title: str
    level: int                      # 1 = top heading, 2 = sub, ...
    elements: list[DocumentElement]
    children: list["SectionNode"]
    page_range: tuple[int, int]     # (start_page, end_page)

    @property
    def text_content(self) -> str:
        """섹션 내 모든 요소의 텍스트를 순서대로 결합."""
        return "\n".join(e.text for e in self.elements)

    @property
    def has_table(self) -> bool:
        return any(e.block_type in ("table", "table_row") for e in self.elements)

    def flatten(self) -> list["SectionNode"]:
        """트리를 평탄화하여 모든 노드를 리스트로 반환."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result
```

### 3.2 기존 모델 변경 없음

| 기존 모델 | 변경 | 이유 |
|-----------|------|------|
| `PDFParserInterface` | 없음 | 기존 파서 호환 |
| `ChunkingStrategy` | 없음 | 기존 전략 호환 |
| `PipelineState` | 필드 2개 추가 (`quality_score`, `layout_metadata`) | 하위 호환 — Optional |
| `DocumentMetadata` | 없음 | 기존 메타데이터 호환 |
| `ChunkingConfig` | 없음 | 기존 설정 호환 |

### 3.3 PipelineState 확장

```python
# domain/pipeline/state/pipeline_state.py — 추가 필드

class PipelineState(TypedDict):
    # ... 기존 필드 모두 유지 ...

    # ★ 신규 (Optional — 기존 파이프라인에서는 미사용)
    quality_score: float              # 0.0 ~ 1.0, 기본 0.0
    layout_metadata: dict             # {"parser_used": str, "fallback_count": int, ...}
```

---

## 4. Infrastructure Module 상세 설계

### 4.1 ElementExtractor

```python
# infrastructure/parser/layout/element_extractor.py

class ElementExtractor:
    """PyMuPDF get_text("dict")를 DocumentElement 리스트로 변환."""

    def extract(self, page: fitz.Page, page_no: int) -> list[DocumentElement]:
        """한 페이지에서 좌표 기반 원자 요소를 추출.

        Args:
            page: PyMuPDF Page 객체
            page_no: 1-indexed 페이지 번호

        Returns:
            정렬되지 않은 DocumentElement 리스트
        """
        data = page.get_text("dict")
        elements: list[DocumentElement] = []

        for block in data["blocks"]:
            if block["type"] == 0:  # text block
                elements.extend(
                    self._extract_text_block(block, page_no)
                )

        return elements

    def _extract_text_block(
        self, block: dict, page_no: int
    ) -> list[DocumentElement]:
        """텍스트 블록에서 라인 단위 DocumentElement 추출."""
        results = []
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue

            spans = line["spans"]
            font_size = spans[0]["size"] if spans else 0.0
            is_bold = any("Bold" in (s.get("font", "") or "") for s in spans)

            bbox = BoundingBox(
                x0=line["bbox"][0],
                y0=line["bbox"][1],
                x1=line["bbox"][2],
                y1=line["bbox"][3],
            )

            results.append(DocumentElement(
                page_no=page_no,
                text=text.strip(),
                bbox=bbox,
                block_type="paragraph",  # 초기값, SectionBuilder가 재분류
                font_size=font_size,
                is_bold=is_bold,
            ))

        return results

    def extract_tables(self, page: fitz.Page, page_no: int) -> list[DocumentElement]:
        """PyMuPDF의 find_tables()로 표 영역을 별도 추출.

        Returns:
            block_type="table" 또는 "table_row"인 DocumentElement 리스트
        """
        tables = page.find_tables()
        elements = []

        for table in tables:
            table_bbox = BoundingBox(
                x0=table.bbox[0], y0=table.bbox[1],
                x1=table.bbox[2], y1=table.bbox[3],
            )

            # 전체 표를 하나의 요소로
            header = table.header
            rows = table.extract()

            if not rows:
                continue

            # Markdown 표 텍스트 구성
            md_lines = []
            if header and header.names:
                md_lines.append("| " + " | ".join(str(h) for h in header.names) + " |")
                md_lines.append("| " + " | ".join("---" for _ in header.names) + " |")

            for row in rows:
                md_lines.append("| " + " | ".join(str(c) if c else "" for c in row) + " |")

            elements.append(DocumentElement(
                page_no=page_no,
                text="\n".join(md_lines),
                bbox=table_bbox,
                block_type="table",
                font_size=0.0,
            ))

        return elements
```

**인터페이스 계약**:
- Input: `fitz.Page`, `page_no: int`
- Output: `list[DocumentElement]` (정렬되지 않은 상태)
- 예외: PyMuPDF 내부 오류 시 빈 리스트 반환 (fail-safe)

### 4.2 NoiseRemover

```python
# infrastructure/parser/layout/noise_remover.py

class NoiseRemover:
    """좌표 + 반복 빈도 기반 헤더/푸터/페이지번호 제거."""

    HEADER_RATIO: float = 0.10       # 상단 10%
    FOOTER_RATIO: float = 0.90       # 하단 10% (y >= 90%)
    REPEAT_THRESHOLD: float = 0.60   # 전체 페이지의 60%+ 반복 시 노이즈

    def remove(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
    ) -> dict[int, list[DocumentElement]]:
        """여러 페이지에서 반복 헤더/푸터를 제거.

        Args:
            pages_elements: {page_no: [elements]} 딕셔너리
            page_height: PDF 페이지 높이 (pt)

        Returns:
            노이즈가 제거된 pages_elements
        """
        total_pages = len(pages_elements)
        if total_pages < 2:
            return pages_elements

        # 1. 상단/하단 영역 텍스트 수집
        header_texts = self._collect_zone_texts(pages_elements, page_height, "header")
        footer_texts = self._collect_zone_texts(pages_elements, page_height, "footer")

        # 2. 반복 빈도 기반 노이즈 텍스트 식별
        noise_texts = self._find_repeated_texts(
            header_texts | footer_texts, total_pages
        )

        # 3. 페이지번호 패턴 추가 (숫자만 있는 하단 요소)
        noise_texts |= self._detect_page_numbers(pages_elements, page_height)

        # 4. 필터링
        return self._filter_elements(pages_elements, noise_texts, page_height)

    def _collect_zone_texts(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
        zone: str,
    ) -> dict[str, int]:
        """상단/하단 영역의 텍스트별 출현 횟수를 수집."""
        counts: dict[str, int] = {}
        for elements in pages_elements.values():
            for elem in elements:
                in_zone = (
                    elem.bbox.is_within_top_ratio(page_height, self.HEADER_RATIO)
                    if zone == "header"
                    else elem.bbox.is_within_bottom_ratio(page_height, self.FOOTER_RATIO)
                )
                if in_zone:
                    normalized = elem.text.strip().lower()
                    counts[normalized] = counts.get(normalized, 0) + 1
        return counts

    def _find_repeated_texts(
        self, text_counts: dict[str, int], total_pages: int
    ) -> set[str]:
        """반복 빈도 임계값을 초과하는 텍스트 집합."""
        threshold = total_pages * self.REPEAT_THRESHOLD
        return {text for text, count in text_counts.items() if count >= threshold}

    def _detect_page_numbers(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        page_height: float,
    ) -> set[str]:
        """하단 영역에서 숫자만으로 구성된 페이지번호 패턴 감지."""
        numbers: set[str] = set()
        for elements in pages_elements.values():
            for elem in elements:
                if elem.bbox.is_within_bottom_ratio(page_height, self.FOOTER_RATIO):
                    stripped = elem.text.strip()
                    if stripped.isdigit() or stripped.replace("-", "").replace("/", "").isdigit():
                        numbers.add(stripped.lower())
        return numbers

    def _filter_elements(
        self,
        pages_elements: dict[int, list[DocumentElement]],
        noise_texts: set[str],
        page_height: float,
    ) -> dict[int, list[DocumentElement]]:
        """노이즈 텍스트에 해당하는 요소를 제거."""
        result: dict[int, list[DocumentElement]] = {}
        for page_no, elements in pages_elements.items():
            filtered = []
            for elem in elements:
                normalized = elem.text.strip().lower()
                is_noise_zone = (
                    elem.bbox.is_within_top_ratio(page_height, self.HEADER_RATIO)
                    or elem.bbox.is_within_bottom_ratio(page_height, self.FOOTER_RATIO)
                )
                if is_noise_zone and normalized in noise_texts:
                    continue
                filtered.append(elem)
            result[page_no] = filtered
        return result
```

### 4.3 ColumnDetector

```python
# infrastructure/parser/layout/column_detector.py

from enum import Enum

class LayoutType(Enum):
    SINGLE = "single"
    DOUBLE = "double"
    MIXED = "mixed"

class ColumnDetector:
    """페이지 레이아웃(1단/2단/혼합) 감지."""

    COLUMN_GAP_RATIO: float = 0.05   # 페이지 너비의 5% 이상 간격
    FULL_WIDTH_RATIO: float = 0.70   # 페이지 너비의 70% 이상 = full-width 블록

    def detect(
        self,
        elements: list[DocumentElement],
        page_width: float,
    ) -> LayoutType:
        """요소들의 x좌표 분포로 레이아웃 유형 감지.

        Args:
            elements: 한 페이지의 DocumentElement 리스트
            page_width: 페이지 너비 (pt)

        Returns:
            LayoutType enum
        """
        if not elements:
            return LayoutType.SINGLE

        midpoint = page_width / 2
        gap_threshold = page_width * self.COLUMN_GAP_RATIO

        left_count = 0
        right_count = 0
        full_width_count = 0

        for elem in elements:
            if elem.bbox.width >= page_width * self.FULL_WIDTH_RATIO:
                full_width_count += 1
            elif elem.bbox.center_x < midpoint - gap_threshold:
                left_count += 1
            elif elem.bbox.center_x > midpoint + gap_threshold:
                right_count += 1

        total_non_full = left_count + right_count
        if total_non_full == 0:
            return LayoutType.SINGLE

        # 양쪽 모두 30% 이상 요소가 있으면 2단
        left_ratio = left_count / total_non_full
        right_ratio = right_count / total_non_full
        threshold = 0.30

        if left_ratio >= threshold and right_ratio >= threshold:
            if full_width_count > 0:
                return LayoutType.MIXED
            return LayoutType.DOUBLE

        return LayoutType.SINGLE

    def split_columns(
        self,
        elements: list[DocumentElement],
        page_width: float,
    ) -> tuple[list[DocumentElement], list[DocumentElement], list[DocumentElement]]:
        """요소를 좌측/우측/전체너비로 분리.

        Returns:
            (left_elements, right_elements, full_width_elements)
        """
        midpoint = page_width / 2
        left, right, full = [], [], []

        for elem in elements:
            if elem.bbox.width >= page_width * self.FULL_WIDTH_RATIO:
                full.append(elem)
            elif elem.bbox.center_x < midpoint:
                left.append(elem)
            else:
                right.append(elem)

        return left, right, full
```

### 4.4 ReadingOrderReconstructor

```python
# infrastructure/parser/layout/reading_order.py

from dataclasses import replace

class ReadingOrderReconstructor:
    """좌표 기반 읽기 순서 재구성."""

    Y_TOLERANCE: float = 5.0  # 같은 줄로 간주하는 y좌표 허용 오차 (pt)

    def reconstruct(
        self,
        elements: list[DocumentElement],
        layout_type: LayoutType,
        page_width: float,
    ) -> list[DocumentElement]:
        """읽기 순서에 따라 요소를 정렬하고 reading_order를 부여.

        Single: y → x 정렬
        Double: 좌측 컬럼 (y→x) → 우측 컬럼 (y→x), full-width는 y 기준 삽입
        Mixed: zone별 처리 (full-width 블록이 zone 분리자)

        Returns:
            reading_order가 부여된 DocumentElement 리스트
        """
        if not elements:
            return []

        if layout_type == LayoutType.SINGLE:
            ordered = self._sort_single(elements)
        elif layout_type == LayoutType.DOUBLE:
            ordered = self._sort_double(elements, page_width)
        else:  # MIXED
            ordered = self._sort_mixed(elements, page_width)

        # reading_order 부여
        return [
            replace(elem, reading_order=idx)
            for idx, elem in enumerate(ordered)
        ]

    def _sort_single(self, elements: list[DocumentElement]) -> list[DocumentElement]:
        """단일 컬럼: y좌표 → x좌표 정렬."""
        return sorted(elements, key=lambda e: (e.bbox.y0, e.bbox.x0))

    def _sort_double(
        self, elements: list[DocumentElement], page_width: float
    ) -> list[DocumentElement]:
        """2단 컬럼: 좌측 전체 → 우측 전체 순서."""
        detector = ColumnDetector()
        left, right, full = detector.split_columns(elements, page_width)

        left_sorted = sorted(left, key=lambda e: (e.bbox.y0, e.bbox.x0))
        right_sorted = sorted(right, key=lambda e: (e.bbox.y0, e.bbox.x0))
        full_sorted = sorted(full, key=lambda e: e.bbox.y0)

        # full-width 블록의 y 위치에 따라 좌/우 컬럼 사이에 삽입
        return self._interleave_full_width(left_sorted, right_sorted, full_sorted)

    def _sort_mixed(
        self, elements: list[DocumentElement], page_width: float
    ) -> list[DocumentElement]:
        """혼합 레이아웃: full-width 블록 기준 zone 분리 후 zone별 처리."""
        detector = ColumnDetector()
        left, right, full = detector.split_columns(elements, page_width)

        # full-width 블록의 y좌표로 zone 경계 설정
        full_sorted = sorted(full, key=lambda e: e.bbox.y0)
        boundaries = [e.bbox.y0 for e in full_sorted]

        result: list[DocumentElement] = []
        remaining_left = sorted(left, key=lambda e: e.bbox.y0)
        remaining_right = sorted(right, key=lambda e: e.bbox.y0)

        prev_y = 0.0
        for i, boundary_y in enumerate(boundaries):
            # 이 zone의 좌측/우측 요소 수집
            zone_left = [e for e in remaining_left if prev_y <= e.bbox.y0 < boundary_y]
            zone_right = [e for e in remaining_right if prev_y <= e.bbox.y0 < boundary_y]

            # zone 내에서 좌→우 순서
            result.extend(sorted(zone_left, key=lambda e: (e.bbox.y0, e.bbox.x0)))
            result.extend(sorted(zone_right, key=lambda e: (e.bbox.y0, e.bbox.x0)))

            # full-width 블록 삽입
            result.append(full_sorted[i])
            prev_y = boundary_y

        # 마지막 zone 잔여 요소
        zone_left = [e for e in remaining_left if e.bbox.y0 >= prev_y]
        zone_right = [e for e in remaining_right if e.bbox.y0 >= prev_y]
        result.extend(sorted(zone_left, key=lambda e: (e.bbox.y0, e.bbox.x0)))
        result.extend(sorted(zone_right, key=lambda e: (e.bbox.y0, e.bbox.x0)))

        return result

    def _interleave_full_width(
        self,
        left: list[DocumentElement],
        right: list[DocumentElement],
        full: list[DocumentElement],
    ) -> list[DocumentElement]:
        """full-width 블록을 좌/우 컬럼 사이에 y위치 기준으로 삽입."""
        result: list[DocumentElement] = []
        all_items = left + right
        all_items_sorted = sorted(all_items, key=lambda e: e.bbox.y0)

        full_idx = 0
        for item in all_items_sorted:
            while full_idx < len(full) and full[full_idx].bbox.y0 <= item.bbox.y0:
                result.append(full[full_idx])
                full_idx += 1
            result.append(item)

        # 남은 full-width 블록
        while full_idx < len(full):
            result.append(full[full_idx])
            full_idx += 1

        return result
```

### 4.5 TableHandler

```python
# infrastructure/parser/layout/table_handler.py

@dataclass
class TableResult:
    """표 처리 결과."""
    markdown: str
    semantic_sentences: list[str]
    metadata: dict

class TableHandler:
    """표를 markdown + 의미 문장 + 메타데이터로 변환."""

    def process_table_element(
        self,
        table_element: DocumentElement,
        section_title: str,
    ) -> TableResult:
        """표 DocumentElement를 3가지 형태로 변환.

        Args:
            table_element: block_type="table"인 DocumentElement (markdown 텍스트 포함)
            section_title: 표가 속한 섹션 제목

        Returns:
            TableResult (markdown, semantic_sentences, metadata)
        """
        md_text = table_element.text
        rows = self._parse_markdown_table(md_text)

        if not rows or len(rows) < 2:
            return TableResult(
                markdown=md_text,
                semantic_sentences=[],
                metadata={"block_type": "table", "section_title": section_title},
            )

        headers = rows[0]
        data_rows = rows[1:]

        # 의미 문장 생성
        sentences = self._generate_semantic_sentences(
            headers, data_rows, section_title
        )

        return TableResult(
            markdown=md_text,
            semantic_sentences=sentences,
            metadata={
                "block_type": "table",
                "section_title": section_title,
                "columns": headers,
                "row_count": len(data_rows),
                "has_numeric_data": self._has_numeric_data(data_rows),
            },
        )

    def _parse_markdown_table(self, md_text: str) -> list[list[str]]:
        """Markdown 표를 2차원 리스트로 파싱."""
        rows = []
        for line in md_text.strip().split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if "---" in line:
                continue  # 구분선 스킵
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(cells)
        return rows

    def _generate_semantic_sentences(
        self,
        headers: list[str],
        data_rows: list[list[str]],
        section_title: str,
    ) -> list[str]:
        """행 단위 의미 문장 생성.

        예: "대출 금리 기준 표에서 A등급의 금리는 3.5%이고 한도는 1억원이다."
        """
        sentences = []
        prefix = f"{section_title}에서 " if section_title else ""

        for row in data_rows:
            if len(row) != len(headers):
                continue
            parts = []
            for header, value in zip(headers, row):
                if value and value.strip():
                    parts.append(f"{header}은(는) {value}")
            if parts:
                sentence = prefix + ", ".join(parts) + "."
                sentences.append(sentence)

        return sentences

    def _has_numeric_data(self, data_rows: list[list[str]]) -> bool:
        """표에 숫자 데이터가 포함되어 있는지 판단."""
        for row in data_rows:
            for cell in row:
                cleaned = cell.replace(",", "").replace("%", "").replace("원", "").strip()
                try:
                    float(cleaned)
                    return True
                except ValueError:
                    continue
        return False
```

### 4.6 SectionBuilder

```python
# infrastructure/parser/layout/section_builder.py

class SectionBuilder:
    """요소들에서 heading을 감지하고 섹션 트리를 구성."""

    HEADING_SIZE_RATIO: float = 1.2  # 본문 평균 대비 1.2배 이상이면 heading

    def build(
        self,
        elements: list[DocumentElement],
    ) -> list[SectionNode]:
        """정렬된 요소 리스트에서 섹션 트리를 구성.

        Args:
            elements: reading_order로 정렬된 DocumentElement 리스트

        Returns:
            최상위 SectionNode 리스트 (각각이 서브트리)
        """
        if not elements:
            return []

        avg_font_size = self._calculate_avg_font_size(elements)
        heading_threshold = avg_font_size * self.HEADING_SIZE_RATIO

        # heading 감지 및 레벨 부여
        classified = self._classify_headings(elements, heading_threshold)

        # 섹션 트리 구성
        return self._build_tree(classified)

    def assign_section_titles(
        self,
        elements: list[DocumentElement],
    ) -> list[DocumentElement]:
        """각 요소에 section_title을 부여한 새 리스트 반환."""
        sections = self.build(elements)
        title_map: dict[int, str] = {}

        for section in sections:
            for flat in section.flatten():
                for elem in flat.elements:
                    title_map[id(elem)] = flat.title

        return [
            replace(elem, section_title=title_map.get(id(elem), ""))
            for elem in elements
        ]

    def _calculate_avg_font_size(self, elements: list[DocumentElement]) -> float:
        """paragraph 타입 요소의 평균 font_size 계산."""
        sizes = [e.font_size for e in elements if e.font_size > 0]
        return sum(sizes) / len(sizes) if sizes else 10.0

    def _classify_headings(
        self,
        elements: list[DocumentElement],
        heading_threshold: float,
    ) -> list[tuple[DocumentElement, int]]:
        """요소에 heading 레벨 부여.

        Returns:
            (element, heading_level) 튜플 리스트.
            heading_level 0 = 본문, 1 = 최상위, 2 = 하위, ...
        """
        result = []
        font_sizes = sorted(
            set(e.font_size for e in elements if e.font_size >= heading_threshold),
            reverse=True,
        )
        size_to_level = {size: idx + 1 for idx, size in enumerate(font_sizes)}

        for elem in elements:
            if elem.font_size >= heading_threshold and (elem.is_bold or elem.font_size > heading_threshold):
                level = size_to_level.get(elem.font_size, 0)
                result.append((replace(elem, block_type="heading"), level))
            else:
                result.append((elem, 0))

        return result

    def _build_tree(
        self,
        classified: list[tuple[DocumentElement, int]],
    ) -> list[SectionNode]:
        """classified 리스트에서 섹션 트리를 재귀적으로 구성."""
        if not classified:
            return []

        root_sections: list[SectionNode] = []
        current_section: SectionNode | None = None
        current_elements: list[DocumentElement] = []

        for elem, level in classified:
            if level > 0:
                # 이전 섹션 마무리
                if current_section:
                    current_section.elements = current_elements
                    root_sections.append(current_section)
                elif current_elements:
                    # heading 전 본문이 있으면 "(서두)" 섹션으로
                    root_sections.append(SectionNode(
                        title="",
                        level=0,
                        elements=current_elements,
                        children=[],
                        page_range=(
                            current_elements[0].page_no,
                            current_elements[-1].page_no,
                        ),
                    ))

                current_section = SectionNode(
                    title=elem.text,
                    level=level,
                    elements=[],
                    children=[],
                    page_range=(elem.page_no, elem.page_no),
                )
                current_elements = [elem]
            else:
                current_elements.append(elem)

        # 마지막 섹션 마무리
        if current_section:
            current_section.elements = current_elements
            if current_elements:
                current_section.page_range = (
                    current_section.page_range[0],
                    current_elements[-1].page_no,
                )
            root_sections.append(current_section)
        elif current_elements:
            root_sections.append(SectionNode(
                title="",
                level=0,
                elements=current_elements,
                children=[],
                page_range=(
                    current_elements[0].page_no,
                    current_elements[-1].page_no,
                ),
            ))

        return root_sections
```

### 4.7 QualityScorer

```python
# infrastructure/parser/layout/quality_scorer.py

class QualityScorer:
    """파싱 결과 품질을 0.0~1.0으로 점수화."""

    def score_page(
        self,
        elements: list[DocumentElement],
        page_height: float,
    ) -> ParseQualityScore:
        """한 페이지의 파싱 품질을 산출."""
        if not elements:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=0.0,
                issues=("empty_page",),
            )

        issues: list[str] = []
        scores: list[float] = []

        # 1. 텍스트 추출량
        text_length = sum(len(e.text) for e in elements)
        if text_length < 50:
            issues.append("low_text_extraction")
            scores.append(0.2)
        elif text_length < 200:
            scores.append(0.6)
        else:
            scores.append(1.0)

        # 2. 평균 단어 길이 (글자 단위 쪼개짐 감지)
        all_text = " ".join(e.text for e in elements)
        words = all_text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        if avg_word_len < 1.5:
            issues.append("fragmented_text")
            scores.append(0.3)
        else:
            scores.append(1.0)

        # 3. y좌표 순서 일관성
        y_coords = [e.bbox.y0 for e in elements]
        order_score = self._calculate_order_consistency(y_coords)
        if order_score < 0.7:
            issues.append("reading_order_broken")
        scores.append(order_score)

        # 4. 표 감지 여부 (표가 있는데 block_type=table이 없으면 감점)
        has_pipe = any("|" in e.text for e in elements)
        has_table_type = any(e.block_type == "table" for e in elements)
        if has_pipe and not has_table_type:
            issues.append("table_not_detected")
            scores.append(0.7)
        else:
            scores.append(1.0)

        final_score = sum(scores) / len(scores)

        return ParseQualityScore(
            page=elements[0].page_no,
            score=round(final_score, 3),
            text_char_count=text_length,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=round(order_score, 3),
            issues=tuple(issues),
        )

    def score_documents(
        self,
        documents: list,  # List[Document]
    ) -> ParseQualityScore:
        """Document 리스트 전체의 종합 품질 점수."""
        if not documents:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0,
                issues=("no_documents",),
            )

        total_chars = sum(len(d.page_content) for d in documents)
        all_text = " ".join(d.page_content for d in documents)
        words = all_text.split()
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)

        issues: list[str] = []
        scores: list[float] = []

        # 텍스트량
        if total_chars < 100:
            issues.append("low_text_extraction")
            scores.append(0.2)
        else:
            scores.append(1.0)

        # 단어 길이
        if avg_word_len < 1.5:
            issues.append("fragmented_text")
            scores.append(0.3)
        else:
            scores.append(1.0)

        final_score = sum(scores) / len(scores)

        return ParseQualityScore(
            page=0,
            score=round(final_score, 3),
            text_char_count=total_chars,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=1.0,
            issues=tuple(issues),
        )

    def _calculate_order_consistency(self, y_coords: list[float]) -> float:
        """y좌표 순서의 일관성 점수 (0.0~1.0)."""
        if len(y_coords) <= 1:
            return 1.0
        in_order = sum(
            1 for i in range(len(y_coords) - 1)
            if y_coords[i] <= y_coords[i + 1] + 5.0  # 5pt tolerance
        )
        return in_order / (len(y_coords) - 1)
```

### 4.8 LayoutAnalyzer (오케스트레이터)

```python
# infrastructure/parser/layout/layout_analyzer.py

class LayoutAnalyzer:
    """7단계 레이아웃 분석 파이프라인 오케스트레이터.

    1. ElementExtractor → 2. NoiseRemover → 3. ColumnDetector
    → 4. ReadingOrder → 5. TableHandler → 6. SectionBuilder → 7. QualityScorer
    """

    def __init__(
        self,
        element_extractor: ElementExtractor | None = None,
        noise_remover: NoiseRemover | None = None,
        column_detector: ColumnDetector | None = None,
        reading_order: ReadingOrderReconstructor | None = None,
        table_handler: TableHandler | None = None,
        section_builder: SectionBuilder | None = None,
        quality_scorer: QualityScorer | None = None,
    ) -> None:
        self._extractor = element_extractor or ElementExtractor()
        self._noise_remover = noise_remover or NoiseRemover()
        self._column_detector = column_detector or ColumnDetector()
        self._reading_order = reading_order or ReadingOrderReconstructor()
        self._table_handler = table_handler or TableHandler()
        self._section_builder = section_builder or SectionBuilder()
        self._quality_scorer = quality_scorer or QualityScorer()

    def analyze(
        self,
        pdf_doc: fitz.Document,
        filename: str,
        user_id: str,
    ) -> tuple[list[Document], ParseQualityScore]:
        """PDF 전체를 분석하여 Document 리스트 + 품질 점수 반환.

        Returns:
            (documents, aggregate_quality_score)
        """
        document_id = generate_document_id(filename)
        total_pages = pdf_doc.page_count

        all_documents: list[Document] = []
        page_scores: list[ParseQualityScore] = []

        # 1. 전체 페이지 요소 추출
        pages_elements: dict[int, list[DocumentElement]] = {}
        for page_num in range(total_pages):
            page = pdf_doc[page_num]
            text_elements = self._extractor.extract(page, page_num + 1)
            table_elements = self._extractor.extract_tables(page, page_num + 1)
            pages_elements[page_num + 1] = text_elements + table_elements

        # 2. 노이즈 제거 (전체 페이지 필요 — 반복 빈도 판단)
        page_height = pdf_doc[0].rect.height if total_pages > 0 else 842.0
        page_width = pdf_doc[0].rect.width if total_pages > 0 else 595.0
        pages_elements = self._noise_remover.remove(pages_elements, page_height)

        # 3-7. 페이지별 분석
        for page_no, elements in pages_elements.items():
            if not elements:
                continue

            # 3. 컬럼 감지
            layout_type = self._column_detector.detect(elements, page_width)

            # 4. 읽기 순서 재구성
            ordered = self._reading_order.reconstruct(elements, layout_type, page_width)

            # 5. 표 처리 — 표 요소의 의미 문장 생성
            enriched = self._enrich_tables(ordered)

            # 6. 섹션 구조화
            with_sections = self._section_builder.assign_section_titles(enriched)

            # 7. 품질 점수
            quality = self._quality_scorer.score_page(with_sections, page_height)
            page_scores.append(quality)

            # Document 생성
            doc = self._elements_to_document(
                elements=with_sections,
                page_no=page_no,
                total_pages=total_pages,
                filename=filename,
                user_id=user_id,
                document_id=document_id,
                quality=quality,
                layout_type=layout_type,
            )
            all_documents.append(doc)

        # 종합 품질 점수
        aggregate = self._aggregate_quality(page_scores)
        return all_documents, aggregate

    def _enrich_tables(
        self, elements: list[DocumentElement]
    ) -> list[DocumentElement]:
        """표 요소에 의미 문장을 추가한 enriched 리스트 반환."""
        result = []
        for elem in elements:
            if elem.block_type == "table":
                table_result = self._table_handler.process_table_element(elem, "")
                # 의미 문장을 별도 paragraph 요소로 추가
                for sentence in table_result.semantic_sentences:
                    result.append(DocumentElement(
                        page_no=elem.page_no,
                        text=sentence,
                        bbox=elem.bbox,
                        block_type="paragraph",
                        section_title=elem.section_title,
                        reading_order=elem.reading_order,
                        confidence=0.9,
                    ))
            result.append(elem)
        return result

    def _elements_to_document(
        self,
        elements: list[DocumentElement],
        page_no: int,
        total_pages: int,
        filename: str,
        user_id: str,
        document_id: str,
        quality: ParseQualityScore,
        layout_type: LayoutType,
    ) -> Document:
        """DocumentElement 리스트를 LangChain Document으로 변환."""
        text_parts = []
        for elem in elements:
            if elem.block_type == "table":
                text_parts.append(f"\n{elem.text}\n")
            else:
                text_parts.append(elem.text)

        page_content = "\n".join(text_parts)
        section_title = next(
            (e.section_title for e in elements if e.section_title), ""
        )
        has_table = any(e.block_type == "table" for e in elements)

        metadata = DocumentMetadata(
            filename=filename,
            user_id=user_id,
            page=page_no,
            total_pages=total_pages,
            parser="pymupdf_layout",
            document_id=document_id,
        )

        meta_dict = metadata.to_dict()
        meta_dict["section_title"] = section_title
        meta_dict["has_table"] = has_table
        meta_dict["quality_score"] = quality.score
        meta_dict["quality_issues"] = list(quality.issues)
        meta_dict["layout_type"] = layout_type.value
        meta_dict["block_types"] = list(set(e.block_type for e in elements))

        return Document(page_content=page_content, metadata=meta_dict)

    def _aggregate_quality(
        self, page_scores: list[ParseQualityScore]
    ) -> ParseQualityScore:
        """페이지별 점수를 종합."""
        if not page_scores:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0,
                issues=("no_pages",),
            )

        avg_score = sum(s.score for s in page_scores) / len(page_scores)
        total_chars = sum(s.text_char_count for s in page_scores)
        avg_word_len = sum(s.avg_word_length for s in page_scores) / len(page_scores)
        avg_order = sum(s.order_consistency for s in page_scores) / len(page_scores)
        all_issues = set()
        for s in page_scores:
            all_issues.update(s.issues)

        return ParseQualityScore(
            page=0,
            score=round(avg_score, 3),
            text_char_count=total_chars,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=round(avg_order, 3),
            issues=tuple(sorted(all_issues)),
        )
```

### 4.9 FallbackParser

```python
# infrastructure/parser/fallback_parser.py

class FallbackParser:
    """품질 점수 기반 파서 자동 전환 오케스트레이터.

    파서 순서: LayoutAnalyzer(PyMuPDF) → DoclingParser → LlamaParserAdapter
    """

    def __init__(
        self,
        layout_analyzer: LayoutAnalyzer,
        secondary_parser: PDFParserInterface | None = None,  # Docling
        tertiary_parser: PDFParserInterface | None = None,   # LlamaParse
        quality_scorer: QualityScorer | None = None,
        logger: LoggerInterface | None = None,
    ) -> None:
        self._layout_analyzer = layout_analyzer
        self._secondary = secondary_parser
        self._tertiary = tertiary_parser
        self._quality_scorer = quality_scorer or QualityScorer()
        self._logger = logger
        self._fallback_parsers = [p for p in [secondary_parser, tertiary_parser] if p]

    def parse_with_fallback(
        self,
        pdf_doc: fitz.Document,
        file_bytes: bytes,
        filename: str,
        user_id: str,
    ) -> tuple[list[Document], ParseQualityScore, str]:
        """품질이 충족될 때까지 파서를 순차 시도.

        Returns:
            (documents, quality_score, parser_used)
        """
        # 1차: LayoutAnalyzer (PyMuPDF 기반)
        documents, quality = self._layout_analyzer.analyze(
            pdf_doc, filename, user_id
        )

        if self._logger:
            self._logger.info(
                "Primary parser attempt",
                parser="pymupdf_layout",
                quality_score=quality.score,
                issues=list(quality.issues),
            )

        if not quality.fallback_required:
            return documents, quality, "pymupdf_layout"

        # 2차 이후: fallback 파서
        for parser in self._fallback_parsers:
            try:
                fallback_docs = parser.parse_bytes(file_bytes, filename, user_id)
                fallback_quality = self._quality_scorer.score_documents(fallback_docs)

                if self._logger:
                    self._logger.info(
                        "Fallback parser attempt",
                        parser=parser.get_parser_name(),
                        quality_score=fallback_quality.score,
                    )

                if not fallback_quality.fallback_required:
                    return fallback_docs, fallback_quality, parser.get_parser_name()

                # 현재 fallback이 primary보다 나으면 갱신
                if fallback_quality.score > quality.score:
                    documents, quality = fallback_docs, fallback_quality

            except Exception as e:
                if self._logger:
                    self._logger.warning(
                        "Fallback parser failed",
                        parser=parser.get_parser_name(),
                        error=str(e),
                    )
                continue

        # 모든 파서 시도 후에도 품질 미달 — 최선 결과 반환
        if self._logger:
            self._logger.warning(
                "All parsers below quality threshold",
                filename=filename,
                best_score=quality.score,
            )

        return documents, quality, "best_effort"
```

### 4.10 SectionAwareChunkingStrategy

```python
# infrastructure/chunking/strategies/section_aware_strategy.py

class SectionAwareChunkingStrategy(ChunkingStrategy):
    """섹션 구조를 인식하는 청킹 전략.

    분할 우선순위:
    1. section_title 경계
    2. paragraph 단위 (\\n\\n)
    3. table 단독 chunk (분할 불가)
    4. token limit 초과 시 토큰 기반 하위 분할
    5. 짧은 chunk 병합 (min_chunk_size 미만)
    """

    def __init__(
        self,
        config: ChunkingConfig,
        min_chunk_size: int = 100,
    ) -> None:
        self._config = config
        self._min_chunk_size = min_chunk_size
        self._chunker = BaseTokenChunker(config)

    def chunk(self, documents: list[Document]) -> list[Document]:
        """Document 리스트를 섹션 인식 청킹."""
        if not documents:
            return []

        # 1. section_title 기준 그룹화
        section_groups = self._group_by_section(documents)

        # 2. 그룹별 청킹
        chunks: list[Document] = []
        for section_title, docs in section_groups:
            chunks.extend(self._chunk_section(docs, section_title))

        # 3. 짧은 chunk 병합
        return self._merge_short_chunks(chunks)

    def _group_by_section(
        self, documents: list[Document]
    ) -> list[tuple[str, list[Document]]]:
        """section_title이 같은 연속 Document들을 그룹화."""
        groups: list[tuple[str, list[Document]]] = []
        current_title = ""
        current_docs: list[Document] = []

        for doc in documents:
            title = doc.metadata.get("section_title", "")
            if title != current_title and current_docs:
                groups.append((current_title, current_docs))
                current_docs = []
            current_title = title
            current_docs.append(doc)

        if current_docs:
            groups.append((current_title, current_docs))

        return groups

    def _chunk_section(
        self,
        docs: list[Document],
        section_title: str,
    ) -> list[Document]:
        """한 섹션의 Document들을 청킹."""
        result = []
        for doc in docs:
            block_type = doc.metadata.get("block_type", "paragraph")

            if block_type == "table" or doc.metadata.get("has_table"):
                # 표는 단독 chunk — 분할하지 않음
                result.append(doc)
            elif self._chunker.count_tokens(doc.page_content) > self._config.chunk_size:
                # 토큰 초과 시 문단 기준 → 토큰 기준 순차 분할
                result.extend(self._split_large_document(doc))
            else:
                result.append(doc)

        return result

    def _split_large_document(self, doc: Document) -> list[Document]:
        """큰 문서를 문단 → 토큰 순서로 분할."""
        paragraphs = [p.strip() for p in doc.page_content.split("\n\n") if p.strip()]

        if not paragraphs:
            # 문단 분리 불가 → 토큰 기반 분할
            return self._split_by_tokens(doc)

        chunks: list[Document] = []
        current_text = ""

        for para in paragraphs:
            candidate = (current_text + "\n\n" + para).strip() if current_text else para
            if self._chunker.count_tokens(candidate) > self._config.chunk_size:
                if current_text:
                    chunks.append(self._create_chunk(doc, current_text, len(chunks)))
                # 단일 문단이 토큰 초과 시 토큰 분할
                if self._chunker.count_tokens(para) > self._config.chunk_size:
                    for sub in self._chunker.split_by_tokens(para):
                        chunks.append(self._create_chunk(doc, sub, len(chunks)))
                    current_text = ""
                else:
                    current_text = para
            else:
                current_text = candidate

        if current_text:
            chunks.append(self._create_chunk(doc, current_text, len(chunks)))

        return chunks

    def _split_by_tokens(self, doc: Document) -> list[Document]:
        """토큰 기반 분할."""
        token_chunks = self._chunker.split_by_tokens(doc.page_content)
        return [
            self._create_chunk(doc, text, idx)
            for idx, text in enumerate(token_chunks)
        ]

    def _create_chunk(
        self, original: Document, text: str, chunk_index: int
    ) -> Document:
        meta = self._chunker.merge_metadata(
            original.metadata,
            {
                "chunk_type": "section_aware",
                "chunk_index": chunk_index,
            },
        )
        return Document(page_content=text, metadata=meta)

    def _merge_short_chunks(self, chunks: list[Document]) -> list[Document]:
        """min_chunk_size 미만 chunk를 인접 chunk와 병합."""
        if not chunks:
            return []

        merged: list[Document] = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            current_tokens = self._chunker.count_tokens(current.page_content)
            if current_tokens < self._min_chunk_size:
                # 같은 섹션이면 병합
                current_section = current.metadata.get("section_title", "")
                next_section = next_chunk.metadata.get("section_title", "")
                if current_section == next_section:
                    merged_text = current.page_content + "\n\n" + next_chunk.page_content
                    current = Document(
                        page_content=merged_text,
                        metadata=current.metadata,
                    )
                    continue

            merged.append(current)
            current = next_chunk

        merged.append(current)
        return merged

    def get_strategy_name(self) -> str:
        return "section_aware"

    def get_chunk_size(self) -> int:
        return self._config.chunk_size
```

---

## 5. 기존 코드 변경 사항

### 5.1 ParserFactory 확장

```python
# infrastructure/parser/parser_factory.py — 변경

class ParserType(Enum):
    PYMUPDF = "pymupdf"
    PYMUPDF4LLM = "pymupdf4llm"
    LLAMAPARSER = "llamaparser"
    DOCLING = "docling"              # ★ 추가
    LAYOUT = "layout"                # ★ 추가 (LayoutAnalyzer 기반)
    FALLBACK = "fallback"            # ★ 추가 (FallbackParser)
```

### 5.2 ChunkingStrategyFactory 확장

```python
# infrastructure/chunking/chunking_factory.py — 변경

class StrategyType(Enum):
    FULL_TOKEN = "full_token"
    PARENT_CHILD = "parent_child"
    SEMANTIC = "semantic"
    SECTION_AWARE = "section_aware"  # ★ 추가
```

### 5.3 PipelineState 필드 추가

```python
# domain/pipeline/state/pipeline_state.py — 추가 필드 (Optional)

    quality_score: float             # 기본 0.0
    layout_metadata: dict            # 기본 {}
```

### 5.4 parse_node 확장 (내부만)

```python
# infrastructure/pipeline/nodes/parse_node.py — 변경

async def parse_node(state, parser):
    # 기존 로직 유지
    # parser가 FallbackParser이면 parse_with_fallback 호출
    # 결과에 quality_score, layout_metadata 추가
```

### 5.5 document_processing_graph — create_initial_state 확장

```python
# 추가 초기값
"quality_score": 0.0,
"layout_metadata": {},
```

---

## 6. Error Handling

### 6.1 각 모듈별 실패 전략

| Module | 실패 시 동작 | 이유 |
|--------|------------|------|
| ElementExtractor | 빈 리스트 반환 | 페이지 파싱 불가 — 다음 페이지 계속 |
| NoiseRemover | 원본 그대로 반환 | 노이즈 제거 실패해도 텍스트는 유지 |
| ColumnDetector | SINGLE 반환 | 감지 실패 시 1단 가정 (안전) |
| ReadingOrder | 입력 순서 유지 | 정렬 실패해도 텍스트 내용은 동일 |
| TableHandler | markdown만 반환 (의미 문장 미생성) | 표 구조 파싱 실패 시 원본 보존 |
| SectionBuilder | 전체를 하나의 섹션으로 | heading 감지 실패 시 평면 구조 |
| QualityScorer | score=0.0 반환 | fallback 트리거 |
| FallbackParser | 최선 결과 반환 + 경고 로그 | 모든 파서 실패해도 결과 있음 |

### 6.2 로깅 규칙

- 각 모듈은 `get_logger(__name__)` 사용 (CLAUDE.md 규칙 준수)
- 실패 시 `logger.error(message, exception=e, ...)` — 스택 트레이스 필수
- fallback 발생 시 `logger.warning(...)` — 운영 모니터링용

---

## 7. Security Considerations

- [x] 파일 입력은 기존 업로드 라우터에서 검증 완료 (파일 크기, MIME 타입)
- [x] PyMuPDF는 메모리 기반 파싱 — 파일시스템 경로 주입 불가
- [x] LlamaParse API key는 환경변수 관리 (하드코딩 없음)
- [ ] Docling 모델 다운로드 경로 제한 필요 (Phase 3)
- [x] 사용자 입력이 직접 코드 실행에 사용되지 않음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | 각 layout 모듈 (7개) | pytest |
| Unit Test | SectionAwareChunkingStrategy | pytest |
| Unit Test | FallbackParser | pytest (mock) |
| Unit Test | Domain VO (BoundingBox, DocumentElement, ParseQualityScore, SectionNode) | pytest |
| Integration Test | LayoutAnalyzer 전체 파이프라인 | pytest + 샘플 PDF |
| Integration Test | document_processing_graph + fallback | pytest |

### 8.2 Test Cases (Key)

#### Domain VO

- [x] BoundingBox: x1 < x0 시 ValueError
- [x] BoundingBox: `is_within_top_ratio(842, 0.1)` = True for y1 <= 84.2
- [x] DocumentElement: page_no < 1 시 ValueError
- [x] ParseQualityScore: score 범위 검증 (0.0~1.0)
- [x] ParseQualityScore: `fallback_required` = True when score < 0.7
- [x] SectionNode: `flatten()` 재귀 동작

#### ElementExtractor

- [ ] 정상 텍스트 블록 → DocumentElement 변환
- [ ] 빈 텍스트 블록 스킵
- [ ] 이미지 블록(type=1) 무시
- [ ] font_size, is_bold 정확 추출
- [ ] find_tables() → block_type="table" 추출

#### NoiseRemover

- [ ] 3페이지 이상에서 동일 헤더 반복 → 제거
- [ ] 하단 페이지번호(숫자만) 제거
- [ ] 본문 텍스트 오탐 없음 (상단 10% 밖은 보존)
- [ ] 2페이지 이하 문서에서는 제거하지 않음

#### ColumnDetector

- [ ] 1단 문서 → SINGLE
- [ ] 2단 문서 → DOUBLE
- [ ] 혼합 레이아웃 → MIXED
- [ ] 빈 요소 → SINGLE (fallback)

#### ReadingOrder

- [ ] SINGLE: y → x 정렬
- [ ] DOUBLE: 좌측 컬럼 → 우측 컬럼 순서
- [ ] MIXED: full-width 블록 기준 zone 분리

#### TableHandler

- [ ] Markdown 표 파싱 (헤더 + 데이터 행)
- [ ] 의미 문장 생성: "대출 금리 기준 표에서 A등급의 금리는 3.5%이다."
- [ ] 빈 표 / 1행 표 → 빈 의미 문장 리스트

#### SectionBuilder

- [ ] font_size 기반 heading 감지
- [ ] heading 없는 문서 → 단일 섹션
- [ ] 멀티 레벨 heading → 트리 구성
- [ ] `assign_section_titles()` → 각 요소에 title 부여

#### QualityScorer

- [ ] 정상 문서 → score >= 0.8
- [ ] 빈 페이지 → score = 0.0
- [ ] 글자 쪼개짐 (avg_word_len < 1.5) → fragmented_text issue
- [ ] y좌표 역순 → reading_order_broken issue

#### FallbackParser

- [ ] primary 품질 충족 → secondary 미호출
- [ ] primary 품질 미달 → secondary 호출
- [ ] 모든 파서 실패 → 최선 결과 반환 + warning 로그
- [ ] secondary 예외 → tertiary로 계속

#### SectionAwareChunkingStrategy

- [ ] 표 단독 chunk (분할 안 함)
- [ ] 섹션 경계에서 chunk 분리
- [ ] 토큰 초과 문단 → 토큰 분할
- [ ] 짧은 chunk 병합 (같은 섹션 내)
- [ ] 빈 입력 → 빈 리스트

---

## 9. Clean Architecture

### 9.1 Layer Structure (이 프로젝트)

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | VO (BoundingBox, DocumentElement, ParseQualityScore, SectionNode), Interface (PDFParserInterface, ChunkingStrategy, LoggerInterface) | `src/domain/parser/`, `src/domain/chunking/` |
| **Application** | (변경 없음) UseCase, LangGraph graph | `src/application/` |
| **Infrastructure** | layout 모듈 7개, FallbackParser, SectionAwareStrategy, 기존 파서 | `src/infrastructure/parser/layout/`, `src/infrastructure/chunking/strategies/` |
| **Interfaces** | (변경 없음) FastAPI router | `src/api/routes/` |

### 9.2 Dependency Rules 준수

```
domain/parser/document_element.py    → 외부 의존 없음 (dataclass, typing만)
domain/parser/parse_quality.py       → 외부 의존 없음
domain/parser/section_tree.py        → document_element.py만 (domain 내부)

infrastructure/parser/layout/*       → domain VO + fitz (PyMuPDF)
infrastructure/parser/fallback_parser.py → domain interface + layout 모듈
infrastructure/chunking/strategies/section_aware_strategy.py → domain interface + BaseTokenChunker
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| BoundingBox, DocumentElement | Domain (VO) | `src/domain/parser/document_element.py` |
| ParseQualityScore | Domain (VO) | `src/domain/parser/parse_quality.py` |
| SectionNode | Domain (VO) | `src/domain/parser/section_tree.py` |
| ElementExtractor | Infrastructure | `src/infrastructure/parser/layout/element_extractor.py` |
| NoiseRemover | Infrastructure | `src/infrastructure/parser/layout/noise_remover.py` |
| ColumnDetector | Infrastructure | `src/infrastructure/parser/layout/column_detector.py` |
| ReadingOrderReconstructor | Infrastructure | `src/infrastructure/parser/layout/reading_order.py` |
| TableHandler | Infrastructure | `src/infrastructure/parser/layout/table_handler.py` |
| SectionBuilder | Infrastructure | `src/infrastructure/parser/layout/section_builder.py` |
| QualityScorer | Infrastructure | `src/infrastructure/parser/layout/quality_scorer.py` |
| LayoutAnalyzer | Infrastructure | `src/infrastructure/parser/layout/layout_analyzer.py` |
| FallbackParser | Infrastructure | `src/infrastructure/parser/fallback_parser.py` |
| SectionAwareChunkingStrategy | Infrastructure | `src/infrastructure/chunking/strategies/section_aware_strategy.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (Python — CLAUDE.md 준수)

| Target | Rule | Example |
|--------|------|---------|
| Class | PascalCase | `ElementExtractor`, `NoiseRemover` |
| Function/Method | snake_case | `extract()`, `remove()`, `score_page()` |
| Constants | UPPER_SNAKE_CASE | `HEADER_RATIO`, `FALLBACK_THRESHOLD` |
| Module files | snake_case | `element_extractor.py`, `noise_remover.py` |
| Domain VO | @dataclass(frozen=True) | `BoundingBox`, `DocumentElement` |
| Private method | _prefix | `_extract_text_block()`, `_calculate_order_consistency()` |

### 10.2 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이내 (CLAUDE.md 규칙) |
| if 중첩 | 2단계 이내 |
| 타입 | 명시적 type hint 모든 함수 시그니처 |
| 로깅 | `get_logger(__name__)`, print() 금지 |
| Config 값 | 클래스 상수 또는 생성자 주입 (하드코딩 금지) |

---

## 11. Implementation Guide

### 11.1 File Structure (신규 생성)

```
src/
├── domain/parser/
│   ├── document_element.py     # ★ Phase 1
│   ├── parse_quality.py        # ★ Phase 1
│   └── section_tree.py         # ★ Phase 2
│
├── infrastructure/parser/layout/
│   ├── __init__.py             # ★ Phase 1
│   ├── element_extractor.py    # ★ Phase 1
│   ├── noise_remover.py        # ★ Phase 1
│   ├── column_detector.py      # ★ Phase 2
│   ├── reading_order.py        # ★ Phase 2
│   ├── table_handler.py        # ★ Phase 2
│   ├── section_builder.py      # ★ Phase 2
│   ├── quality_scorer.py       # ★ Phase 3
│   └── layout_analyzer.py      # ★ Phase 3
│
├── infrastructure/parser/
│   ├── fallback_parser.py      # ★ Phase 3
│   └── docling_parser.py       # ★ Phase 3
│
├── infrastructure/chunking/strategies/
│   └── section_aware_strategy.py  # ★ Phase 3
│
tests/
├── domain/parser/
│   ├── test_document_element.py   # ★ Phase 1
│   ├── test_parse_quality.py      # ★ Phase 1
│   └── test_section_tree.py       # ★ Phase 2
│
├── infrastructure/parser/layout/
│   ├── test_element_extractor.py  # ★ Phase 1
│   ├── test_noise_remover.py      # ★ Phase 1
│   ├── test_column_detector.py    # ★ Phase 2
│   ├── test_reading_order.py      # ★ Phase 2
│   ├── test_table_handler.py      # ★ Phase 2
│   ├── test_section_builder.py    # ★ Phase 2
│   ├── test_quality_scorer.py     # ★ Phase 3
│   └── test_layout_analyzer.py    # ★ Phase 3 (integration)
│
├── infrastructure/parser/
│   └── test_fallback_parser.py    # ★ Phase 3
│
└── infrastructure/chunking/strategies/
    └── test_section_aware_strategy.py  # ★ Phase 3
```

### 11.2 Implementation Order (TDD — Red → Green → Refactor)

#### Phase 1: 기반 구축 (Week 1)

1. [x] `domain/parser/document_element.py` — BoundingBox + DocumentElement VO
2. [x] `tests/domain/parser/test_document_element.py` — VO 검증 테스트
3. [x] `domain/parser/parse_quality.py` — ParseQualityScore VO
4. [x] `tests/domain/parser/test_parse_quality.py` — VO 검증 테스트
5. [x] `infrastructure/parser/layout/element_extractor.py` — 좌표 기반 추출
6. [x] `tests/infrastructure/parser/layout/test_element_extractor.py`
7. [x] `infrastructure/parser/layout/noise_remover.py` — 헤더/푸터 제거
8. [x] `tests/infrastructure/parser/layout/test_noise_remover.py`
9. [ ] `infrastructure/parser/pymupdf4llm_parser.py` — page_chunks 개선 (이미 완료 확인)

#### Phase 2: 구조 분석 + 표 처리 (Week 2)

10. [x] `domain/parser/section_tree.py` — SectionNode VO
11. [x] `tests/domain/parser/test_section_tree.py`
12. [x] `infrastructure/parser/layout/column_detector.py`
13. [x] `tests/infrastructure/parser/layout/test_column_detector.py`
14. [x] `infrastructure/parser/layout/reading_order.py`
15. [x] `tests/infrastructure/parser/layout/test_reading_order.py`
16. [x] `infrastructure/parser/layout/table_handler.py`
17. [x] `tests/infrastructure/parser/layout/test_table_handler.py`
18. [x] `infrastructure/parser/layout/section_builder.py`
19. [x] `tests/infrastructure/parser/layout/test_section_builder.py`

#### Phase 3: 품질 + Fallback + 청킹 (Week 3)

20. [x] `infrastructure/parser/layout/quality_scorer.py`
21. [x] `tests/infrastructure/parser/layout/test_quality_scorer.py`
22. [x] `infrastructure/parser/layout/layout_analyzer.py` — 오케스트레이터
23. [x] `tests/infrastructure/parser/layout/test_layout_analyzer.py`
24. [ ] `infrastructure/parser/docling_parser.py`
25. [x] `infrastructure/parser/fallback_parser.py`
26. [x] `tests/infrastructure/parser/test_fallback_parser.py`
27. [x] `infrastructure/chunking/strategies/section_aware_strategy.py`
28. [x] `tests/infrastructure/chunking/strategies/test_section_aware_strategy.py`
29. [x] Pipeline 통합: PipelineState 필드 추가 + ParserFactory/ChunkingFactory 확장
30. [ ] `tests/integration/test_document_processing_with_layout.py`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-13 | Initial draft — Plan 기반 상세 설계 | 배상규 |
