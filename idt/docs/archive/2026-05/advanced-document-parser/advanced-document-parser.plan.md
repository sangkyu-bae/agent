# advanced-document-parser Planning Document

> **Summary**: 좌표 기반 PDF 파싱 → 레이아웃 분석 → 구조화 → 품질 점수 → fallback → section-aware 청킹으로 이어지는 실무급 문서 처리 파이프라인 고도화
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 파서가 `page.get_text()`(PyMuPDF) 또는 `to_markdown()`(pymupdf4llm)으로 단순 텍스트만 추출 — 헤더/푸터 노이즈, 읽기 순서 깨짐, 표 구조 소실, 품질 검증 없음, fallback 없음으로 RAG 검색 품질이 문서 유형에 따라 불안정 |
| **Solution** | 좌표 기반 요소 추출 → 노이즈 제거(헤더/푸터) → 레이아웃 분석(1단/2단/표) → 읽기 순서 재구성 → 표 특화 처리(markdown + 의미 문장) → 섹션 구조화 → 품질 점수 계산 → fallback(PyMuPDF → Docling → LlamaParse) → section-aware 청킹으로 이어지는 단계별 방어 파이프라인 구축 |
| **Function/UX Effect** | 금융 규정/보고서의 금리 기준표, 한도표 등이 정확히 추출되어 RAG 답변 정확도 향상. 파싱 실패 시 자동 fallback으로 사용자가 "파싱 안 됨" 경험을 하지 않음. 검색 결과에 페이지·섹션·표 출처가 정확히 표시됨 |
| **Core Value** | "단순 텍스트 추출 → 청킹 → 벡터 저장"에서 "좌표 기반 구조 분석 → 품질 검증 → 적응적 처리"로 전환 — 면접에서 "PDF 파서를 왜 직접 만들었나요?"에 대한 명확한 답변 근거 확보 |

---

## 1. Overview

### 1.1 Purpose

참조 문서(docs/ex/pasor.md)에 기술된 실무급 PDF 처리 파이프라인을 프로젝트에 적용한다.
단순 라이브러리 호출이 아닌, 좌표 기반 요소 추출 → 레이아웃 분석 → 구조화 → 품질 검증 → fallback으로 이어지는 **단계별 방어 전략**을 구현한다.

### 1.2 Background — 현재 상태 vs 참조 문서 갭 분석

| # | 참조 문서 권고사항 | 현재 상태 | 갭 수준 |
|---|-------------------|----------|---------|
| 1 | 좌표 기반 원자 요소 추출 (bbox) | ❌ `page.get_text()` 단순 텍스트만 | **Major** |
| 2 | 헤더/푸터 제거 (좌표 + 반복 빈도) | ❌ 미구현 | **Major** — 매 페이지 노이즈 |
| 3 | 읽기 순서 재구성 (y/x 정렬) | ❌ 미구현 | **Major** — 순서 깨짐 가능 |
| 4 | 2단 컬럼 감지/처리 | ❌ 미구현 | Medium — 외부 보고서에서 발생 |
| 5 | 표 특화 처리 (markdown + 의미 문장 + metadata) | ⚠️ pymupdf4llm이 markdown 표 보존, 의미 문장화 없음 | **Major** — 금융 문서 핵심 |
| 6 | 각주 분리 | ❌ 미구현 | Minor |
| 7 | 참고문헌 별도 처리 | ❌ 미구현 | Minor |
| 8 | 문서 구조 트리 (섹션 계층) | ❌ 평면적 Document 리스트 | **Major** |
| 9 | 품질 점수 계산 | ❌ 미구현 | **Major** — fallback 판단 불가 |
| 10 | 파서 fallback 파이프라인 | ⚠️ 복수 파서 존재하나 자동 전환 없음 | **Major** |
| 11 | Section-aware 청킹 | ⚠️ SemanticStrategy가 \\n\\n 기준, 섹션 미인식 | Medium |

### 1.3 Related Plans (기존 Plan 통합)

이 Plan은 아래 기존 Plan을 **하위 작업으로 포함**한다:

| 기존 Plan | 이 Plan에서의 위치 |
|-----------|-------------------|
| `docling-pdf-parser.plan.md` | Phase 3: Fallback 파서 추가 |
| `pymupdf4llm-page-metadata.plan.md` | Phase 1: 페이지별 메타데이터 보존 (선행 조건) |

---

## 2. Scope

### 2.1 In Scope

| # | 항목 | 설명 | Phase |
|---|------|------|-------|
| 1 | **DocumentElement 도메인 모델** | bbox, block_type, section_title, reading_order, confidence 포함 | 1 |
| 2 | **좌표 기반 요소 추출** | PyMuPDF `get_text("dict")` 활용, 블록/라인/스팬 레벨 추출 | 1 |
| 3 | **헤더/푸터 제거** | 상하 10% 영역 + 페이지 간 반복 빈도 기반 필터링 | 1 |
| 4 | **표 특화 처리** | markdown 표 보존 + 행 단위 의미 문장 생성 + 표 전용 메타데이터 | 2 |
| 5 | **읽기 순서 재구성** | y/x 좌표 기반 정렬, full-width 블록 감지 | 2 |
| 6 | **2단 컬럼 감지** | 페이지 너비 기준 컬럼 분리 → 컬럼별 정렬 → 병합 | 2 |
| 7 | **섹션 구조화** | heading 감지 → section_title 부여 → 구조 트리 생성 | 2 |
| 8 | **품질 점수 계산** | 텍스트 추출량, 순서 일관성, 표 추출 성공 여부 등 복합 점수 | 3 |
| 9 | **Fallback 파이프라인** | 품질 점수 기준: PyMuPDF → Docling → LlamaParse 자동 전환 | 3 |
| 10 | **Section-aware 청킹** | 섹션 단위 → 문단 단위 → 표 단독 chunk → 토큰 초과 시 분할 | 3 |
| 11 | **pymupdf4llm 페이지별 개선** | `page_chunks=True` + section_title + has_table (기존 Plan) | 1 |

### 2.2 Out of Scope

| # | 항목 | 사유 |
|---|------|------|
| 1 | 이미지/그림 추출 | 텍스트/표 중심 MVP, 멀티모달은 후속 |
| 2 | OCR 전용 파서 개발 | Docling/LlamaParse의 OCR 기능으로 커버 |
| 3 | 프론트엔드 파싱 결과 UI | 별도 feature |
| 4 | 기존 인제스트 데이터 마이그레이션 | 신규 개발 중이라 불필요 |

---

## 3. Architecture

### 3.1 핵심 도메인 모델 (신규)

```
domain/parser/
├── interfaces.py              # PDFParserInterface (기존 유지)
├── value_objects.py           # ParserConfig, DocumentMetadata (기존 유지)
├── document_element.py        # ★ 신규: DocumentElement VO
├── parse_quality.py           # ★ 신규: ParseQualityScore VO
└── section_tree.py            # ★ 신규: SectionNode VO
```

```python
# document_element.py
@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

BlockType = Literal[
    "title", "paragraph", "table", "footer",
    "header", "footnote", "figure_caption", "reference"
]

@dataclass(frozen=True)
class DocumentElement:
    page_no: int
    text: str
    bbox: BoundingBox
    block_type: BlockType
    section_title: str = ""
    reading_order: int = 0
    font_size: float = 0.0
    confidence: float = 1.0
```

```python
# parse_quality.py
@dataclass(frozen=True)
class ParseQualityScore:
    page: int
    score: float                    # 0.0 ~ 1.0
    issues: list[str]               # ["two_column_detected", "table_detected", ...]
    text_char_count: int
    avg_word_length: float
    order_consistency: float        # 0.0 ~ 1.0 (y좌표 순서 일관성)
    fallback_required: bool

    @staticmethod
    def calculate(elements: list, page_height: float) -> "ParseQualityScore":
        ...
```

### 3.2 인프라 레이어 구조

```
infrastructure/parser/
├── pymupdf_parser.py           # 기존 (Phase 1에서 좌표 추출 추가)
├── pymupdf4llm_parser.py       # Phase 1에서 page_chunks 개선
├── llamaparser.py              # 기존 유지 (fallback용)
├── docling_parser.py           # Phase 3에서 추가 (기존 Plan)
├── parser_factory.py           # Phase 3에서 fallback 로직 추가
│
├── layout/                     # ★ 신규 패키지
│   ├── element_extractor.py    # PyMuPDF dict → DocumentElement 변환
│   ├── noise_remover.py        # 헤더/푸터/페이지번호 제거
│   ├── reading_order.py        # 읽기 순서 재구성
│   ├── column_detector.py      # 1단/2단 컬럼 감지
│   ├── table_handler.py        # 표 특화 처리 (markdown + 의미 문장)
│   ├── section_builder.py      # 섹션 구조 트리 생성
│   └── quality_scorer.py       # 품질 점수 계산
│
└── pipeline/
    ├── fallback_parser.py      # ★ 신규: 품질 기반 fallback 오케스트레이터
    └── ...
```

### 3.3 데이터 흐름 (고도화 후)

```
[PDF bytes]
    │
    ▼
1. ElementExtractor (좌표 기반 원자 요소 추출)
    │  PyMuPDF get_text("dict") → List[DocumentElement]
    │
    ▼
2. NoiseRemover (헤더/푸터/페이지번호 제거)
    │  상하 10% 영역 + 반복 빈도 필터링
    │
    ▼
3. ColumnDetector (레이아웃 분석)
    │  1단/2단/mixed 감지
    │
    ▼
4. ReadingOrderReconstructor (읽기 순서 재구성)
    │  컬럼별 y/x 정렬 → full-width 블록 기준 zone 분리
    │
    ▼
5. TableHandler (표 특화 처리)
    │  markdown 표 보존 + 행 단위 의미 문장 생성
    │
    ▼
6. SectionBuilder (섹션 구조화)
    │  heading 감지 → section_title 부여 → 트리 구성
    │
    ▼
7. QualityScorer (품질 점수 계산)
    │  텍스트량/순서일관성/표추출 → score 0.0~1.0
    │
    ├── score >= 0.7 → 결과 사용
    └── score < 0.7 → FallbackParser (Docling → LlamaParse)
         │
         ▼
8. SectionAwareChunker (섹션 기반 청킹)
    │  섹션 단위 → 문단 → 표 단독 → 토큰 초과 분할
    │
    ▼
9. VectorStore (Qdrant 저장)
    │  payload: page, section_title, block_type, has_table, quality_score
```

---

## 4. Phase 별 구현 계획

### Phase 1: 기반 구축 + 즉시 효과 (Week 1)

> 목표: 좌표 기반 추출 기반 마련 + 헤더/푸터 제거 + pymupdf4llm 페이지별 개선

| # | Task | 파일 | 예상 시간 | 선행 |
|---|------|------|-----------|------|
| 1-1 | DocumentElement, BoundingBox VO 정의 | `domain/parser/document_element.py` | 1h | - |
| 1-2 | ParseQualityScore VO 정의 | `domain/parser/parse_quality.py` | 1h | - |
| 1-3 | ElementExtractor 구현 (PyMuPDF dict → DocumentElement) | `infrastructure/parser/layout/element_extractor.py` | 3h | 1-1 |
| 1-4 | NoiseRemover 구현 (헤더/푸터 제거) | `infrastructure/parser/layout/noise_remover.py` | 3h | 1-3 |
| 1-5 | pymupdf4llm page_chunks=True 개선 (기존 Plan 실행) | `infrastructure/parser/pymupdf4llm_parser.py` | 2h | - |
| 1-6 | 각 모듈 TDD 테스트 | `tests/infrastructure/parser/layout/` | 3h | 1-3~1-5 |

**Phase 1 산출물**: 좌표 추출 + 노이즈 제거가 동작하는 기본 파이프라인

### Phase 2: 구조 분석 + 표 처리 (Week 2)

> 목표: 레이아웃 분석, 표 의미 문장화, 섹션 구조화 — POC 데모의 핵심

| # | Task | 파일 | 예상 시간 | 선행 |
|---|------|------|-----------|------|
| 2-1 | ColumnDetector 구현 (1단/2단/mixed) | `infrastructure/parser/layout/column_detector.py` | 3h | 1-3 |
| 2-2 | ReadingOrderReconstructor 구현 | `infrastructure/parser/layout/reading_order.py` | 3h | 2-1 |
| 2-3 | TableHandler 구현 (markdown + 의미 문장 + 메타데이터) | `infrastructure/parser/layout/table_handler.py` | 4h | 1-3 |
| 2-4 | SectionBuilder 구현 (heading 감지 + 트리) | `infrastructure/parser/layout/section_builder.py` | 3h | 2-2 |
| 2-5 | SectionNode VO 정의 | `domain/parser/section_tree.py` | 1h | - |
| 2-6 | 각 모듈 TDD 테스트 | `tests/infrastructure/parser/layout/` | 3h | 2-1~2-4 |

**Phase 2 산출물**: 표가 정확히 추출되고, 섹션 구조가 보존되는 파이프라인

### Phase 3: 품질 검증 + Fallback + Section-aware 청킹 (Week 3)

> 목표: 안정성 확보 + 운영 대비

| # | Task | 파일 | 예상 시간 | 선행 |
|---|------|------|-----------|------|
| 3-1 | QualityScorer 구현 | `infrastructure/parser/layout/quality_scorer.py` | 3h | Phase 2 |
| 3-2 | DoclingParser 추가 (기존 Plan 실행) | `infrastructure/parser/docling_parser.py` | 4h | - |
| 3-3 | FallbackParser 구현 (품질 기반 자동 전환) | `infrastructure/parser/pipeline/fallback_parser.py` | 3h | 3-1, 3-2 |
| 3-4 | SectionAwareChunkingStrategy 구현 | `infrastructure/chunking/strategies/section_aware_strategy.py` | 4h | Phase 2 |
| 3-5 | LangGraph document_processing_graph 업데이트 | `infrastructure/pipeline/graph/document_processing_graph.py` | 2h | 3-3, 3-4 |
| 3-6 | 전체 통합 테스트 + 실제 금융 문서 테스트 | `tests/integration/` | 3h | 전체 |

**Phase 3 산출물**: 품질 검증 → fallback → 섹션 기반 청킹이 완성된 운영급 파이프라인

---

## 5. 핵심 설계 상세

### 5.1 ElementExtractor — 좌표 기반 추출

```python
class ElementExtractor:
    """PyMuPDF get_text("dict") → List[DocumentElement] 변환."""

    def extract(self, page: fitz.Page, page_no: int) -> list[DocumentElement]:
        """페이지에서 좌표 기반 원자 요소를 추출한다."""
        data = page.get_text("dict")
        elements = []

        for block in data["blocks"]:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    text = "".join(span["text"] for span in line["spans"])
                    if not text.strip():
                        continue
                    bbox = BoundingBox(
                        x0=line["bbox"][0], y0=line["bbox"][1],
                        x1=line["bbox"][2], y1=line["bbox"][3],
                    )
                    font_size = line["spans"][0]["size"] if line["spans"] else 0
                    elements.append(DocumentElement(
                        page_no=page_no, text=text.strip(),
                        bbox=bbox, block_type="paragraph",
                        font_size=font_size,
                    ))
            elif block["type"] == 1:  # image block
                pass  # Out of Scope

        return elements
```

### 5.2 NoiseRemover — 헤더/푸터 제거

```python
class NoiseRemover:
    """좌표 + 반복 빈도 기반 헤더/푸터 제거."""

    HEADER_RATIO = 0.10  # 상단 10%
    FOOTER_RATIO = 0.90  # 하단 10%
    REPEAT_THRESHOLD = 0.6  # 전체 페이지의 60% 이상 반복 시 제거

    def remove(
        self, pages_elements: dict[int, list[DocumentElement]], page_height: float
    ) -> dict[int, list[DocumentElement]]:
        """여러 페이지의 elements에서 반복 헤더/푸터를 제거한다."""
        header_candidates = self._collect_zone_texts(
            pages_elements, page_height, zone="header"
        )
        footer_candidates = self._collect_zone_texts(
            pages_elements, page_height, zone="footer"
        )
        noise_texts = self._find_repeated(
            header_candidates | footer_candidates, len(pages_elements)
        )
        return self._filter_elements(pages_elements, noise_texts)
```

### 5.3 TableHandler — 표 특화 처리 (금융 문서 핵심)

```python
class TableHandler:
    """표를 markdown 보존 + 의미 문장 생성 + 메타데이터 부여."""

    def process_table(
        self, table_elements: list[DocumentElement], section_title: str
    ) -> TableResult:
        """표 영역을 3가지 형태로 변환한다.

        Returns:
            TableResult:
                markdown: str     — 원본 Markdown 표
                semantic: str     — 행 단위 의미 문장
                metadata: dict    — block_type, section_title, columns 등
        """
        # 1. Markdown 표 보존 (pymupdf4llm 활용 또는 직접 구성)
        markdown = self._build_markdown_table(table_elements)

        # 2. 행 단위 의미 문장 생성
        # "대출 금리 기준 표에서 A등급의 금리는 3.5%이고 한도는 1억이다."
        semantic = self._generate_semantic_text(table_elements, section_title)

        # 3. 메타데이터
        metadata = {
            "block_type": "table",
            "section_title": section_title,
            "columns": self._extract_column_names(table_elements),
            "row_count": len(table_elements) - 1,  # 헤더 제외
        }

        return TableResult(markdown=markdown, semantic=semantic, metadata=metadata)
```

### 5.4 QualityScorer — 품질 점수

```python
class QualityScorer:
    """파싱 결과 품질을 0.0~1.0으로 점수화."""

    FALLBACK_THRESHOLD = 0.7

    def score_page(self, elements: list[DocumentElement], page_height: float) -> ParseQualityScore:
        issues = []
        scores = []

        # 1. 텍스트 추출량 점수
        text_length = sum(len(e.text) for e in elements)
        if text_length < 50:
            issues.append("low_text_extraction")
            scores.append(0.2)
        else:
            scores.append(1.0)

        # 2. 평균 단어 길이 이상 여부 (글자 단위 쪼개짐 감지)
        words = " ".join(e.text for e in elements).split()
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

        final_score = sum(scores) / len(scores) if scores else 0.0

        return ParseQualityScore(
            page=elements[0].page_no if elements else 0,
            score=final_score,
            issues=issues,
            text_char_count=text_length,
            avg_word_length=avg_word_len,
            order_consistency=order_score,
            fallback_required=final_score < self.FALLBACK_THRESHOLD,
        )
```

### 5.5 FallbackParser — 자동 전환

```python
class FallbackParser:
    """품질 점수 기반 파서 자동 전환 오케스트레이터."""

    def __init__(
        self,
        primary: PDFParserInterface,          # PyMuPDF (+ layout pipeline)
        secondary: PDFParserInterface,        # Docling
        tertiary: PDFParserInterface | None,  # LlamaParse (optional, 유료)
        quality_scorer: QualityScorer,
        logger: LoggerInterface,
    ) -> None:
        self._parsers = [p for p in [primary, secondary, tertiary] if p]
        self._quality_scorer = quality_scorer
        self._logger = logger

    async def parse_with_fallback(
        self, file_bytes: bytes, filename: str, user_id: str
    ) -> tuple[list[Document], ParseQualityScore]:
        """품질이 충족될 때까지 파서를 순차 시도."""
        for parser in self._parsers:
            documents = parser.parse_bytes(file_bytes, filename, user_id)
            quality = self._quality_scorer.score_documents(documents)

            self._logger.info(
                "Parser attempt",
                parser=parser.get_parser_name(),
                quality_score=quality.score,
                issues=quality.issues,
            )

            if not quality.fallback_required:
                return documents, quality

        # 모든 파서 시도 후에도 품질 미달 시 마지막 결과 반환 + 경고
        self._logger.warning("All parsers below quality threshold", filename=filename)
        return documents, quality
```

### 5.6 SectionAwareChunkingStrategy — 섹션 기반 청킹

```python
class SectionAwareChunkingStrategy(ChunkingStrategy):
    """섹션 구조를 인식하는 청킹 전략.

    분할 우선순위:
    1. section 단위
    2. paragraph 단위
    3. table 단독 chunk
    4. token limit 초과 시 하위 분할
    """

    def chunk(self, documents: list[Document]) -> list[Document]:
        result = []
        for doc in documents:
            block_type = doc.metadata.get("block_type", "paragraph")

            if block_type == "table":
                # 표는 단독 chunk (분할하지 않음)
                result.append(doc)
            elif self._chunker.count_tokens(doc.page_content) > self._config.chunk_size:
                # 토큰 초과 시 문단 기준 분할
                result.extend(self._split_by_paragraphs(doc))
            else:
                result.append(doc)

        return self._merge_short_chunks(result)
```

---

## 6. LangGraph 파이프라인 업데이트

현재 파이프라인: `parse → classify → chunk → store`

고도화 후 파이프라인:
```
parse → layout_analyze → classify → chunk → store
  │
  └── (parse 노드 내부)
      extract_elements → remove_noise → detect_columns
      → reconstruct_order → handle_tables → build_sections
      → score_quality → fallback_if_needed
```

`parse_node`를 확장하여 내부적으로 layout 분석 파이프라인을 실행한다.
기존 `classify → chunk → store` 흐름은 변경하지 않는다 (인터페이스 유지).

---

## 7. Testing Strategy

### 7.1 단위 테스트 (TDD, 각 모듈별)

| 모듈 | 주요 테스트 |
|------|------------|
| ElementExtractor | PyMuPDF dict → DocumentElement 변환, bbox 정확성, 빈 블록 스킵 |
| NoiseRemover | 반복 헤더 감지, 페이지번호 정규화, 본문 오탐 방지 |
| ColumnDetector | 1단 문서 감지, 2단 문서 감지, mixed 레이아웃 |
| ReadingOrder | y/x 정렬 정확성, full-width 블록 처리 |
| TableHandler | markdown 표 생성, 의미 문장 생성, 금리 기준표 테스트 |
| SectionBuilder | heading 레벨 감지, 트리 구성, 빈 섹션 처리 |
| QualityScorer | 정상 문서 고점수, 깨진 문서 저점수, fallback 판단 |
| FallbackParser | 순차 시도, 품질 충족 시 중단, 전부 실패 시 경고 |
| SectionAwareChunker | 표 단독 chunk, 섹션 경계 보존, 짧은 chunk 병합 |

### 7.2 통합 테스트 (실제 PDF)

| 테스트 | 검증 |
|--------|------|
| 금융 규정 PDF (1단, 표 포함) | 표가 의미 문장으로 변환되는지, 섹션 구조 보존 |
| 외부 보고서 PDF (2단 컬럼) | 읽기 순서 정확성, 컬럼 감지 |
| 스캔본 PDF | fallback → Docling/LlamaParse 자동 전환 |
| 100페이지 대용량 PDF | 성능, 메모리, 품질 점수 일관성 |

---

## 8. Success Criteria

### 8.1 POC 기준 (3주 후)

- [ ] 금융 규정 문서의 표가 의미 문장으로 변환되어 RAG 검색에 정확히 걸림
- [ ] 헤더/푸터가 제거되어 검색 노이즈 감소
- [ ] 파싱 품질 점수가 로깅되어 모니터링 가능
- [ ] 품질 미달 시 fallback 파서로 자동 전환

### 8.2 운영 기준 (1개월 후)

- [ ] 100명 사용자가 다양한 문서 업로드 시 파싱 실패율 < 5%
- [ ] 평균 파싱 품질 점수 >= 0.8
- [ ] 표 포함 문서의 RAG 답변 정확도 > 85% (RAGAS 기준)

---

## 9. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 3주 안에 전체 구현 불가 | POC 지연 | Medium | Phase 우선순위 엄격 적용 — Phase 1+2만으로도 POC 데모 가능 |
| 좌표 기반 파싱이 문서마다 다르게 동작 | 품질 불안정 | High | QualityScorer + Fallback으로 방어 |
| Docling 모델 다운로드 + 메모리 | 서버 부담 | Medium | lazy init, CPU-only 모드, 메모리 모니터링 |
| 표 의미 문장 생성 품질 | RAG 답변 부정확 | Medium | 금융 도메인 특화 프롬프트 + 수동 검수 샘플 |
| 기존 파이프라인과 호환성 깨짐 | 다른 기능 장애 | Low | parse_node 인터페이스 유지, 내부만 확장 |

---

## 10. Dependencies

### 10.1 신규 패키지

```toml
# pyproject.toml
docling = ">=2.0.0"       # Phase 3: Fallback 파서
# pymupdf, pymupdf4llm은 기존 설치됨
```

### 10.2 기존 인터페이스 영향

| 인터페이스 | 변경 | 영향 |
|-----------|------|------|
| `PDFParserInterface` | 변경 없음 | 기존 파서 호환 |
| `ChunkingStrategy` | 변경 없음 | 기존 전략 호환 |
| `PipelineState` | 필드 추가 가능 (quality_score) | 하위 호환 |
| `document_processing_graph` | parse_node 내부 확장 | 외부 인터페이스 유지 |

---

## 11. Implementation Order Summary

```
Week 1 (Phase 1): 기반 구축
├── DocumentElement/ParseQualityScore VO
├── ElementExtractor (좌표 기반 추출)
├── NoiseRemover (헤더/푸터 제거)
├── pymupdf4llm page_chunks 개선
└── TDD 테스트

Week 2 (Phase 2): 구조 분석 + 표 처리
├── ColumnDetector (1단/2단 감지)
├── ReadingOrderReconstructor
├── TableHandler (markdown + 의미 문장) ★ POC 핵심
├── SectionBuilder
└── TDD 테스트

Week 3 (Phase 3): 안정성 + 운영 대비
├── QualityScorer (품질 점수)
├── DoclingParser 추가
├── FallbackParser (자동 전환)
├── SectionAwareChunkingStrategy
├── LangGraph 파이프라인 업데이트
└── 통합 테스트
```

---

## 12. Future Extensions

| Extension | Trigger |
|-----------|---------|
| RAGAS 평가 연동 (파서 개선 효과 측정) | 운영 안정화 후 |
| Reranker 연동 (검색 결과 재정렬) | RAG 품질 추가 개선 필요 시 |
| 멀티모달 (이미지 추출 + VLM) | 이미지 포함 문서 요구 시 |
| 파싱 결과 캐싱 (동일 문서 재파싱 방지) | 운영 비용 최적화 시 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-13 | Initial draft — 참조 문서 기반 통합 Plan | 배상규 |
