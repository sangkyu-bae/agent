# advanced-ingest-pipeline Design Document

> **Summary**: 기존 5개 모듈(pdf-analyzer, pdf-routing, advanced-document-parser, table-retrieval-enhancer, morph-index)을 LangGraph 파이프라인으로 통합하는 고도화 PDF Ingest API 코드 수준 상세 설계
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-16
> **Status**: Draft
> **Planning Doc**: [advanced-ingest-pipeline.plan.md](../../01-plan/features/advanced-ingest-pipeline.plan.md)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 5개 모듈이 독립 실행 → 순차 호출 필요, 기존 ingest API는 ES(BM25) 미지원, 레이아웃 분석/테이블 전처리 미통합 |
| **Solution** | 9노드 LangGraph 파이프라인 + `AdvancedIngestUseCase` 오케스트레이터 + `POST /api/v1/ingest/pdf/advanced` |
| **Function/UX Effect** | PDF 1회 업로드 → 유형 분석 → 최적 파서 → 레이아웃 분석 → 표 변환 → 형태소 전처리 → Qdrant + ES 이중 색인 |
| **Core Value** | 기존 모듈 100% 재사용, 신규 코드는 오케스트레이션 + 노드 어댑터만, 금융 문서 특화 하이브리드 검색 지원 |

---

## 1. Overview

### 1.1 Design Goals

1. **기존 모듈 100% 재사용**: pdf-analyzer, pdf-routing, LayoutAnalyzer, TableFlatteningPreprocessor, MorphAnalyzerInterface — 인터페이스 수정 없이 조합
2. **기존 파이프라인 무영향**: `document_processing_graph.py` 변경 없음, 별도 `AdvancedPipelineState` 사용
3. **조건부 실행**: document_type 및 enable 플래그에 따라 노드 스킵/실행 분기
4. **품질 기반 fallback**: LayoutAnalyzer 품질 < 0.7 시 기본 파서로 재시도
5. **이중 저장 병렬화**: Qdrant + ES 저장을 `asyncio.gather`로 병렬 실행

### 1.2 Design Principles

- **Single Responsibility**: 각 노드는 하나의 기존 모듈을 호출하는 어댑터 역할
- **Open-Closed**: 새 전처리 단계 추가 시 노드만 추가, 기존 노드 수정 불필요
- **Dependency Inversion**: 모든 노드는 domain 인터페이스에 의존, infrastructure 구현체는 DI로 주입
- **Fail-Safe**: 각 노드 실패 시 `status="failed"` + errors 기록, 조건부 분기로 파이프라인 중단

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     API Layer (interfaces)                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ advanced_ingest_router.py                                           │    │
│  │   POST /api/v1/ingest/pdf/advanced                                  │    │
│  │     → AdvancedIngestUseCase.ingest()                                │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   Application Layer                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │ AdvancedIngestUseCase                                               │    │
│  │   1. 파이프라인 그래프 빌드                                           │    │
│  │   2. 초기 상태 생성                                                  │    │
│  │   3. 그래프 실행                                                     │    │
│  │   4. 결과 매핑                                                       │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                                       │
│                                                                              │
│  ┌─ advanced_processing_graph.py ──────────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  analyze ──▶ route ──▶ parse ──▶ layout_analyze ──▶ table_preprocess   │ │
│  │                                                           │            │ │
│  │  complete ◀── dual_store ◀── morph ◀── chunk ◀────────────┘            │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌── 기존 모듈 (수정 없음) ───────────────────────────────────────────────┐  │
│  │ PyMuPDFAnalyzer       DefaultParserRouter       LayoutAnalyzer        │  │
│  │ PDFParserInterface    TableFlatteningPreprocessor                      │  │
│  │ KiwiMorphAnalyzer     VectorStoreInterface       ESRepository         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
PDF bytes
  │
  ▼
[analyze_node] ─── PDFAnalyzerInterface.analyze_bytes() ──→ AnalysisResult
  │                                                          (document_type, confidence, metrics)
  ▼
[route_node] ──── ParserRouterInterface.route() ──→ RoutingDecision
  │                                                   (parser_type, is_fallback)
  ▼
[parse_node] ──── PDFParserInterface.parse_bytes() ──→ List[Document]
  │                                                     (parsed_documents)
  ▼
[layout_analyze_node] ─── LayoutAnalyzer.analyze() ──→ List[Document] + quality_score
  │                        (조건: SCANNED 제외, enable=true)
  ▼
[table_preprocess_node] ── TableFlatteningPreprocessor.process() ──→ enriched documents
  │                         (조건: 표 존재, enable=true)
  ▼
[chunk_node] ──── ChunkingStrategyFactory.create_strategy() ──→ List[Document]
  │                                                              (chunked_documents)
  ▼
[morph_node] ──── MorphAnalyzerInterface.analyze() ──→ morph_keywords per chunk
  │
  ▼
[dual_store_node] ──┬── EmbeddingInterface + VectorStoreInterface ──→ Qdrant
                    └── ElasticsearchRepositoryInterface.bulk_index() ──→ ES
  │
  ▼
[complete_node] ──→ AdvancedIngestResult
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `analyze_node` | `PDFAnalyzerInterface` | PDF 유형 분류 |
| `route_node` | `ParserRouterInterface`, `ParserRoutingConfig` | 최적 파서 선택 |
| `parse_node` | `Dict[str, PDFParserInterface]` (파서 레지스트리) | PDF 파싱 |
| `layout_analyze_node` | `LayoutAnalyzer` | 좌표 기반 레이아웃 분석 |
| `table_preprocess_node` | `TableFlatteningPreprocessor` | 표 → 의미 문장 변환 |
| `chunk_node` | `ChunkingStrategy` | 문서 청킹 |
| `morph_node` | `MorphAnalyzerInterface` | 형태소 분석 |
| `dual_store_node` | `EmbeddingInterface`, `VectorStoreInterface`, `ElasticsearchRepositoryInterface` | 이중 저장 |

---

## 3. File Structure

```
src/
├── domain/advanced_ingest/
│   ├── __init__.py
│   └── schemas.py                          # AdvancedIngestRequest, AdvancedIngestResult
│
├── application/advanced_ingest/
│   ├── __init__.py
│   └── use_case.py                         # AdvancedIngestUseCase
│
├── infrastructure/pipeline/
│   ├── state/
│   │   └── advanced_pipeline_state.py      # AdvancedPipelineState TypedDict
│   ├── graph/
│   │   └── advanced_processing_graph.py    # LangGraph 워크플로우
│   └── nodes/
│       ├── analyze_node.py                 # (신규)
│       ├── route_node.py                   # (신규)
│       ├── layout_analyze_node.py          # (신규)
│       ├── table_preprocess_node.py        # (신규)
│       ├── morph_node.py                   # (신규)
│       └── dual_store_node.py              # (신규)
│
└── api/routes/
    └── advanced_ingest_router.py           # (신규)

tests/
├── domain/advanced_ingest/
│   └── test_schemas.py
├── application/advanced_ingest/
│   └── test_use_case.py
└── infrastructure/pipeline/
    ├── state/
    │   └── test_advanced_pipeline_state.py
    ├── nodes/
    │   ├── test_analyze_node.py
    │   ├── test_route_node.py
    │   ├── test_layout_analyze_node.py
    │   ├── test_table_preprocess_node.py
    │   ├── test_morph_node.py
    │   └── test_dual_store_node.py
    └── graph/
        └── test_advanced_processing_graph.py
```

**총 신규 파일**: 프로덕션 11개 + 테스트 9개 = 20개

---

## 4. Domain Layer

### 4.1 `domain/advanced_ingest/schemas.py`

```python
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AdvancedIngestRequest(BaseModel):
    filename: str
    user_id: str
    request_id: str
    file_bytes: bytes
    collection_name: str = "documents"
    chunking_strategy: str = "parent_child"
    chunk_size: int = Field(default=500, ge=100, le=8000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    enable_layout_analysis: bool = True
    enable_table_flattening: bool = True
    sample_pages: int = Field(default=3, ge=1, le=10)

    @field_validator("filename")
    @classmethod
    def filename_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class AdvancedIngestResult(BaseModel):
    document_id: str
    filename: str
    user_id: str
    total_pages: int

    # Analysis
    document_type: Optional[str] = None
    analysis_confidence: float = 0.0
    routed_parser: str = ""

    # Preprocessing
    layout_quality_score: Optional[float] = None
    layout_applied: bool = False
    table_count: int = 0
    table_flattened: bool = False

    # Indexing
    chunk_count: int = 0
    chunking_strategy: str = ""
    qdrant_indexed: int = 0
    es_indexed: int = 0

    # Performance
    processing_time_ms: int = 0
    step_timings: Dict[str, int] = Field(default_factory=dict)

    # Meta
    collection_name: str = ""
    request_id: str = ""
    errors: List[str] = Field(default_factory=list)
```

---

## 5. Infrastructure Layer — Pipeline State

### 5.1 `infrastructure/pipeline/state/advanced_pipeline_state.py`

```python
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class AdvancedPipelineState(TypedDict):
    # === Input ===
    file_path: str
    file_bytes: Optional[bytes]
    filename: str
    user_id: str
    request_id: str
    collection_name: str

    # === Config ===
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    enable_layout_analysis: bool
    enable_table_flattening: bool
    sample_pages: int

    # === Analyze Node ===
    document_type: Optional[str]
    analysis_confidence: float
    analysis_metrics: Dict[str, Any]

    # === Route Node ===
    routed_parser_type: str
    routing_reason: str
    is_fallback: bool

    # === Parse Node ===
    parsed_documents: List[Any]
    total_pages: int
    document_id: str

    # === Layout Analyze Node ===
    layout_quality_score: Optional[float]
    layout_applied: bool

    # === Table Preprocess Node ===
    table_count: int
    table_flattened: bool
    preprocessed_documents: List[Any]

    # === Chunk Node ===
    chunked_documents: List[Any]
    chunk_count: int

    # === Morph Node ===
    morph_applied: bool
    morph_keywords_per_chunk: List[List[str]]

    # === Dual Store Node ===
    qdrant_stored_ids: List[str]
    qdrant_stored_count: int
    es_stored_count: int
    es_index_name: str

    # === Metadata ===
    processing_time_ms: int
    step_timings: Dict[str, int]
    errors: List[str]
    status: str
```

**초기 상태 팩토리 함수:**

```python
def create_advanced_initial_state(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    request_id: str,
    collection_name: str = "documents",
    chunking_strategy: str = "parent_child",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    enable_layout_analysis: bool = True,
    enable_table_flattening: bool = True,
    sample_pages: int = 3,
) -> AdvancedPipelineState:
    return {
        "file_path": "",
        "file_bytes": file_bytes,
        "filename": filename,
        "user_id": user_id,
        "request_id": request_id,
        "collection_name": collection_name,
        "chunking_strategy": chunking_strategy,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "enable_layout_analysis": enable_layout_analysis,
        "enable_table_flattening": enable_table_flattening,
        "sample_pages": sample_pages,
        "document_type": None,
        "analysis_confidence": 0.0,
        "analysis_metrics": {},
        "routed_parser_type": "",
        "routing_reason": "",
        "is_fallback": False,
        "parsed_documents": [],
        "total_pages": 0,
        "document_id": "",
        "layout_quality_score": None,
        "layout_applied": False,
        "table_count": 0,
        "table_flattened": False,
        "preprocessed_documents": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "morph_applied": False,
        "morph_keywords_per_chunk": [],
        "qdrant_stored_ids": [],
        "qdrant_stored_count": 0,
        "es_stored_count": 0,
        "es_index_name": "",
        "processing_time_ms": 0,
        "step_timings": {},
        "errors": [],
        "status": "pending",
    }
```

---

## 6. Infrastructure Layer — Pipeline Nodes

### 6.1 `analyze_node.py`

```python
import asyncio
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def analyze_node(
    state: AdvancedPipelineState,
    analyzer: PDFAnalyzerInterface,
) -> dict:
    try:
        config = AnalysisConfig(sample_pages=state["sample_pages"])
        result = await asyncio.to_thread(
            analyzer.analyze_bytes,
            file_bytes=state["file_bytes"],
            config=config,
        )
        return {
            "document_type": result.document_type.value,
            "analysis_confidence": result.confidence,
            "analysis_metrics": {
                "total_pages": result.total_pages,
                "sampled_pages": result.sampled_pages,
                "avg_text_chars": result.summary_metrics.avg_text_chars,
                "avg_table_count": result.summary_metrics.avg_table_count,
                "avg_image_area_ratio": result.summary_metrics.avg_image_area_ratio,
                "extractable_text_ratio": result.summary_metrics.extractable_text_ratio,
            },
            "total_pages": result.total_pages,
            "status": "analyzing",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Analyze failed: {str(e)}"],
        }
```

**핵심**: `asyncio.to_thread`로 동기 `analyze_bytes()` 래핑 (기존 PyMuPDFAnalyzer가 동기 메서드)

### 6.2 `route_node.py`

```python
from typing import Optional
from src.domain.pdf_analyzer.schemas import AnalysisResult, PDFDocumentType, SummaryMetrics, PageFeatures
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def route_node(
    state: AdvancedPipelineState,
    router: ParserRouterInterface,
    routing_config: Optional[ParserRoutingConfig] = None,
) -> dict:
    try:
        analysis_result = _reconstruct_analysis_result(state)
        decision = router.route(
            analysis_result=analysis_result,
            config=routing_config,
        )
        return {
            "routed_parser_type": decision.parser_type,
            "routing_reason": decision.reason.value,
            "is_fallback": decision.is_fallback,
            "status": "routing",
        }
    except Exception as e:
        return {
            "routed_parser_type": "pymupdf",
            "routing_reason": "route_error_fallback",
            "is_fallback": True,
            "status": "routing",
            "errors": state["errors"] + [f"Route failed, using fallback: {str(e)}"],
        }


def _reconstruct_analysis_result(state: AdvancedPipelineState) -> Optional[AnalysisResult]:
    """state에 저장된 분석 결과를 AnalysisResult 객체로 재구성."""
    if state["document_type"] is None:
        return None
    metrics = state.get("analysis_metrics", {})
    return AnalysisResult(
        document_type=PDFDocumentType(state["document_type"]),
        confidence=state["analysis_confidence"],
        total_pages=state.get("total_pages", 1),
        sampled_pages=metrics.get("sampled_pages", 1),
        page_features=[],
        summary_metrics=SummaryMetrics(
            avg_text_chars=metrics.get("avg_text_chars", 0.0),
            avg_image_count=metrics.get("avg_image_count", 0.0),
            avg_image_area_ratio=metrics.get("avg_image_area_ratio", 0.0),
            avg_table_count=metrics.get("avg_table_count", 0.0),
            extractable_text_ratio=metrics.get("extractable_text_ratio", 0.0),
        ),
    )
```

**핵심**: route 실패 시에도 파이프라인 중단하지 않고 `pymupdf` fallback

### 6.3 `parse_node.py` (기존 재사용 + 라우팅 연동)

기존 `parse_node.py`를 그대로 사용하되, `AdvancedPipelineState.routed_parser_type`으로 선택된 파서를 전달받는 래퍼 노드 구현:

```python
import asyncio
from typing import Dict
from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def advanced_parse_node(
    state: AdvancedPipelineState,
    parsers: Dict[str, PDFParserInterface],
) -> dict:
    parser_type = state.get("routed_parser_type", "pymupdf")
    parser = parsers.get(parser_type)
    if parser is None:
        parser = parsers.get("pymupdf")
        if parser is None:
            return {
                "status": "failed",
                "errors": state["errors"] + [f"No parser available for '{parser_type}'"],
            }

    try:
        documents = await asyncio.to_thread(
            parser.parse_bytes,
            file_bytes=state["file_bytes"],
            filename=state["filename"],
            user_id=state["user_id"],
        )
        if not documents:
            return {
                "status": "failed",
                "errors": state["errors"] + ["No documents parsed from PDF"],
            }

        document_id = ""
        if documents[0].metadata.get("document_id"):
            document_id = documents[0].metadata["document_id"]

        return {
            "parsed_documents": documents,
            "total_pages": len(documents),
            "document_id": document_id,
            "status": "parsing",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Parse failed: {str(e)}"],
        }
```

### 6.4 `layout_analyze_node.py`

```python
import asyncio
import fitz
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState

QUALITY_THRESHOLD = 0.7
SKIP_TYPES = {"ocr_heavy"}


async def layout_analyze_node(
    state: AdvancedPipelineState,
    layout_analyzer: LayoutAnalyzer,
) -> dict:
    if not state.get("enable_layout_analysis", True):
        return {"layout_applied": False, "layout_quality_score": None}

    doc_type = state.get("document_type", "")
    if doc_type in SKIP_TYPES:
        return {"layout_applied": False, "layout_quality_score": None}

    try:
        pdf_doc = fitz.open(stream=state["file_bytes"], filetype="pdf")
        documents, quality = await asyncio.to_thread(
            layout_analyzer.analyze,
            pdf_doc=pdf_doc,
            filename=state["filename"],
            user_id=state["user_id"],
        )
        pdf_doc.close()

        if quality.score < QUALITY_THRESHOLD:
            return {
                "layout_applied": False,
                "layout_quality_score": quality.score,
                "errors": state["errors"] + [
                    f"Layout quality {quality.score:.2f} < {QUALITY_THRESHOLD}, skipping"
                ],
            }

        return {
            "parsed_documents": documents,
            "layout_applied": True,
            "layout_quality_score": quality.score,
        }
    except Exception as e:
        return {
            "layout_applied": False,
            "layout_quality_score": None,
            "errors": state["errors"] + [f"Layout analysis failed: {str(e)}"],
        }
```

**핵심**: 
- `SKIP_TYPES`에 `ocr_heavy` 포함 — llamaparser 결과를 우선 사용
- 품질 < 0.7 시 기존 `parsed_documents` 유지 (덮어쓰지 않음)
- 성공 시 `parsed_documents`를 레이아웃 분석 결과로 교체

### 6.5 `table_preprocess_node.py`

```python
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def table_preprocess_node(
    state: AdvancedPipelineState,
    preprocessor: TableFlatteningPreprocessor,
) -> dict:
    if not state.get("enable_table_flattening", True):
        return {
            "preprocessed_documents": state.get("parsed_documents", []),
            "table_flattened": False,
            "table_count": 0,
        }

    documents = state.get("parsed_documents", [])
    if not documents:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No documents for table preprocessing"],
        }

    try:
        total_table_count = 0
        enriched_docs = []

        for doc in documents:
            section_title = doc.metadata.get("section_title", "")
            result = preprocessor.process(doc.page_content, section_title)
            total_table_count += result.table_count

            if result.table_count > 0:
                doc.page_content = result.child_text
                doc.metadata["original_text"] = result.parent_text
                doc.metadata["table_count"] = result.table_count
                if result.metadata:
                    doc.metadata["table_metadata"] = result.metadata

            enriched_docs.append(doc)

        return {
            "preprocessed_documents": enriched_docs,
            "table_flattened": total_table_count > 0,
            "table_count": total_table_count,
        }
    except Exception as e:
        return {
            "preprocessed_documents": documents,
            "table_flattened": False,
            "table_count": 0,
            "errors": state["errors"] + [f"Table preprocessing failed: {str(e)}"],
        }
```

**핵심**: 표 전처리 실패 시에도 원본 documents 전달 — 파이프라인 중단 없음

### 6.6 `chunk_node.py` (기존 확장)

```python
from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def advanced_chunk_node(state: AdvancedPipelineState) -> dict:
    documents = state.get("preprocessed_documents") or state.get("parsed_documents", [])
    if not documents:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No documents to chunk"],
        }

    try:
        strategy = ChunkingStrategyFactory.create_strategy(
            state["chunking_strategy"],
            chunk_size=state["chunk_size"],
            chunk_overlap=state["chunk_overlap"],
            table_flattening=False,  # 이미 table_preprocess_node에서 처리
        )
        chunked = strategy.chunk(documents)

        if not chunked:
            return {
                "status": "failed",
                "errors": state["errors"] + ["No chunks produced"],
            }

        document_id = state.get("document_id", "")
        for chunk in chunked:
            chunk.metadata["document_id"] = document_id

        return {
            "chunked_documents": chunked,
            "chunk_count": len(chunked),
            "status": "chunking",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Chunking failed: {str(e)}"],
        }
```

**핵심**: `table_flattening=False` — ParentChildStrategy 내부 표 전처리를 비활성화 (이미 별도 노드에서 처리 완료)

### 6.7 `morph_node.py`

```python
from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState

_KEYWORD_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})
_VERB_ADJ_TAGS = frozenset({"VV", "VA"})


async def morph_node(
    state: AdvancedPipelineState,
    morph_analyzer: MorphAnalyzerInterface,
) -> dict:
    chunks = state.get("chunked_documents", [])
    if not chunks:
        return {
            "morph_applied": False,
            "morph_keywords_per_chunk": [],
        }

    try:
        keywords_per_chunk: list[list[str]] = []
        for chunk in chunks:
            analysis = morph_analyzer.analyze(chunk.page_content)
            keywords = _extract_keywords(analysis)
            keywords_per_chunk.append(keywords)
            chunk.metadata["morph_keywords"] = keywords

        return {
            "morph_applied": True,
            "morph_keywords_per_chunk": keywords_per_chunk,
        }
    except Exception as e:
        return {
            "morph_applied": False,
            "morph_keywords_per_chunk": [],
            "errors": state["errors"] + [f"Morph analysis failed: {str(e)}"],
        }


def _extract_keywords(analysis) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for tok in analysis.tokens:
        if tok.pos not in _KEYWORD_TAGS:
            continue
        form = tok.surface + "다" if tok.pos in _VERB_ADJ_TAGS else tok.surface
        if form not in seen:
            seen.add(form)
            keywords.append(form)
    return keywords
```

**핵심**: `MorphAndDualIndexUseCase._extract_morph_keywords()` 로직 재사용 — 동일한 키워드 추출 규칙

### 6.8 `dual_store_node.py`

```python
import asyncio
import json
import uuid

from src.domain.elasticsearch.schemas import ESDocument
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.vector.entities import Document as VecDoc
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.infrastructure.elasticsearch.es_index_mappings import (
    DOCUMENTS_INDEX_MAPPINGS,
    DOCUMENTS_INDEX_SETTINGS,
)
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def dual_store_node(
    state: AdvancedPipelineState,
    embedding: EmbeddingInterface,
    vectorstore: VectorStoreInterface,
    es_repo: ElasticsearchRepositoryInterface,
) -> dict:
    chunks = state.get("chunked_documents", [])
    if not chunks:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No chunks to store"],
        }

    collection_name = state.get("collection_name", "documents")
    request_id = state.get("request_id", "")
    morph_keywords_per_chunk = state.get("morph_keywords_per_chunk", [])
    document_id = state.get("document_id", "")
    user_id = state.get("user_id", "")

    try:
        # 1. 임베딩 생성
        texts = [c.page_content for c in chunks]
        vectors = await embedding.embed_documents(texts)

        # 2. Qdrant 문서 빌드
        vec_docs: list[VecDoc] = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
            metadata = {k: str(v) for k, v in chunk.metadata.items()}
            metadata["user_id"] = user_id
            metadata["document_id"] = document_id
            metadata["collection_name"] = collection_name
            if i < len(morph_keywords_per_chunk):
                metadata["morph_keywords"] = json.dumps(
                    morph_keywords_per_chunk[i], ensure_ascii=False
                )
            vec_docs.append(VecDoc(id=None, content=chunk.page_content, vector=vector, metadata=metadata))

        # 3. ES 문서 빌드
        es_index = f"docs_{collection_name}"
        es_docs: list[ESDocument] = []
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
            body: dict = {
                "content": chunk.page_content,
                "chunk_id": chunk_id,
                "chunk_type": chunk.metadata.get("chunk_type", "full"),
                "chunk_index": chunk.metadata.get("chunk_index", i),
                "total_chunks": chunk.metadata.get("total_chunks", len(chunks)),
                "document_id": document_id,
                "user_id": user_id,
                "collection_name": collection_name,
            }
            if i < len(morph_keywords_per_chunk):
                body["morph_keywords"] = morph_keywords_per_chunk[i]
            if "parent_id" in chunk.metadata:
                body["parent_id"] = chunk.metadata["parent_id"]
            es_docs.append(ESDocument(id=chunk_id, body=body, index=es_index))

        # 4. ES 인덱스 보장
        await es_repo.ensure_index_exists(
            index=es_index,
            mappings=DOCUMENTS_INDEX_MAPPINGS,
            settings=DOCUMENTS_INDEX_SETTINGS,
        )

        # 5. 병렬 저장 (Qdrant + ES)
        qdrant_task = vectorstore.add_documents(vec_docs)
        es_task = es_repo.bulk_index(es_docs, request_id)
        qdrant_ids, es_count = await asyncio.gather(qdrant_task, es_task)

        qdrant_id_strings = [doc_id.value for doc_id in qdrant_ids]

        return {
            "qdrant_stored_ids": qdrant_id_strings,
            "qdrant_stored_count": len(qdrant_id_strings),
            "es_stored_count": es_count,
            "es_index_name": es_index,
            "status": "storing",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Dual store failed: {str(e)}"],
        }
```

**핵심**:
- `asyncio.gather`로 Qdrant + ES 병렬 저장
- `ensure_index_exists`로 ES 인덱스 자동 생성 (nori_analyzer 설정 포함)
- ES 인덱스명 규칙: `docs_{collection_name}`

---

## 7. Infrastructure Layer — LangGraph Workflow

### 7.1 `advanced_processing_graph.py`

```python
import time
from typing import Dict, Optional

from langgraph.graph import StateGraph, END

from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState
from src.infrastructure.pipeline.nodes.analyze_node import analyze_node
from src.infrastructure.pipeline.nodes.route_node import route_node
from src.infrastructure.pipeline.nodes.advanced_parse_node import advanced_parse_node
from src.infrastructure.pipeline.nodes.layout_analyze_node import layout_analyze_node
from src.infrastructure.pipeline.nodes.table_preprocess_node import table_preprocess_node
from src.infrastructure.pipeline.nodes.advanced_chunk_node import advanced_chunk_node
from src.infrastructure.pipeline.nodes.morph_node import morph_node
from src.infrastructure.pipeline.nodes.dual_store_node import dual_store_node


def create_advanced_processing_graph(
    analyzer: PDFAnalyzerInterface,
    router: ParserRouterInterface,
    parsers: Dict[str, PDFParserInterface],
    layout_analyzer: LayoutAnalyzer,
    table_preprocessor: TableFlatteningPreprocessor,
    morph_analyzer: MorphAnalyzerInterface,
    embedding: EmbeddingInterface,
    vectorstore: VectorStoreInterface,
    es_repo: ElasticsearchRepositoryInterface,
    routing_config: Optional[ParserRoutingConfig] = None,
) -> StateGraph:

    async def _timed(name, coro, state):
        start = time.time()
        result = coro
        elapsed = int((time.time() - start) * 1000)
        timings = dict(state.get("step_timings", {}))
        timings[name] = elapsed
        result["step_timings"] = timings
        result["processing_time_ms"] = state["processing_time_ms"] + elapsed
        return result

    async def analyze_step(state):
        r = await analyze_node(state, analyzer)
        return await _timed("analyze", r, state)

    async def route_step(state):
        r = await route_node(state, router, routing_config)
        return await _timed("route", r, state)

    async def parse_step(state):
        r = await advanced_parse_node(state, parsers)
        return await _timed("parse", r, state)

    async def layout_step(state):
        r = await layout_analyze_node(state, layout_analyzer)
        return await _timed("layout_analyze", r, state)

    async def table_step(state):
        r = await table_preprocess_node(state, table_preprocessor)
        return await _timed("table_preprocess", r, state)

    async def chunk_step(state):
        r = await advanced_chunk_node(state)
        return await _timed("chunk", r, state)

    async def morph_step(state):
        r = await morph_node(state, morph_analyzer)
        return await _timed("morph", r, state)

    async def store_step(state):
        r = await dual_store_node(state, embedding, vectorstore, es_repo)
        return await _timed("dual_store", r, state)

    async def complete_step(state):
        return {"status": "completed"}

    def should_continue(state) -> str:
        if state["status"] == "failed":
            return "end"
        return "continue"

    workflow = StateGraph(AdvancedPipelineState)

    workflow.add_node("analyze", analyze_step)
    workflow.add_node("route", route_step)
    workflow.add_node("parse", parse_step)
    workflow.add_node("layout_analyze", layout_step)
    workflow.add_node("table_preprocess", table_step)
    workflow.add_node("chunk", chunk_step)
    workflow.add_node("morph", morph_step)
    workflow.add_node("dual_store", store_step)
    workflow.add_node("complete", complete_step)

    workflow.set_entry_point("analyze")

    workflow.add_conditional_edges("analyze", should_continue, {"continue": "route", "end": END})
    workflow.add_conditional_edges("route", should_continue, {"continue": "parse", "end": END})
    workflow.add_conditional_edges("parse", should_continue, {"continue": "layout_analyze", "end": END})
    workflow.add_conditional_edges("layout_analyze", should_continue, {"continue": "table_preprocess", "end": END})
    workflow.add_conditional_edges("table_preprocess", should_continue, {"continue": "chunk", "end": END})
    workflow.add_conditional_edges("chunk", should_continue, {"continue": "morph", "end": END})
    workflow.add_conditional_edges("morph", should_continue, {"continue": "dual_store", "end": END})
    workflow.add_conditional_edges("dual_store", should_continue, {"continue": "complete", "end": END})
    workflow.add_edge("complete", END)

    return workflow.compile()
```

---

## 8. Application Layer — UseCase

### 8.1 `application/advanced_ingest/use_case.py`

```python
from typing import Dict, Optional

from src.domain.advanced_ingest.schemas import AdvancedIngestRequest, AdvancedIngestResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.pipeline.graph.advanced_processing_graph import create_advanced_processing_graph
from src.infrastructure.pipeline.state.advanced_pipeline_state import create_advanced_initial_state


class AdvancedIngestUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        router: ParserRouterInterface,
        parsers: Dict[str, PDFParserInterface],
        layout_analyzer: LayoutAnalyzer,
        table_preprocessor: TableFlatteningPreprocessor,
        morph_analyzer: MorphAnalyzerInterface,
        embedding: EmbeddingInterface,
        vectorstore: VectorStoreInterface,
        es_repo: ElasticsearchRepositoryInterface,
        logger: LoggerInterface,
        routing_config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._analyzer = analyzer
        self._router = router
        self._parsers = parsers
        self._layout_analyzer = layout_analyzer
        self._table_preprocessor = table_preprocessor
        self._morph_analyzer = morph_analyzer
        self._embedding = embedding
        self._vectorstore = vectorstore
        self._es_repo = es_repo
        self._logger = logger
        self._routing_config = routing_config

    async def ingest(self, request: AdvancedIngestRequest) -> AdvancedIngestResult:
        self._logger.info(
            "Advanced ingest started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
        )

        try:
            graph = create_advanced_processing_graph(
                analyzer=self._analyzer,
                router=self._router,
                parsers=self._parsers,
                layout_analyzer=self._layout_analyzer,
                table_preprocessor=self._table_preprocessor,
                morph_analyzer=self._morph_analyzer,
                embedding=self._embedding,
                vectorstore=self._vectorstore,
                es_repo=self._es_repo,
                routing_config=self._routing_config,
            )

            initial_state = create_advanced_initial_state(
                file_bytes=request.file_bytes,
                filename=request.filename,
                user_id=request.user_id,
                request_id=request.request_id,
                collection_name=request.collection_name,
                chunking_strategy=request.chunking_strategy,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap,
                enable_layout_analysis=request.enable_layout_analysis,
                enable_table_flattening=request.enable_table_flattening,
                sample_pages=request.sample_pages,
            )

            final_state = await graph.ainvoke(initial_state)

        except Exception as exc:
            self._logger.error(
                "Advanced ingest failed",
                exception=exc,
                request_id=request.request_id,
            )
            raise

        result = self._map_to_result(final_state, request)

        self._logger.info(
            "Advanced ingest completed",
            request_id=request.request_id,
            document_type=result.document_type,
            routed_parser=result.routed_parser,
            chunk_count=result.chunk_count,
            qdrant_indexed=result.qdrant_indexed,
            es_indexed=result.es_indexed,
            processing_time_ms=result.processing_time_ms,
        )
        return result

    def _map_to_result(self, state: dict, request: AdvancedIngestRequest) -> AdvancedIngestResult:
        return AdvancedIngestResult(
            document_id=state.get("document_id", ""),
            filename=request.filename,
            user_id=request.user_id,
            total_pages=state.get("total_pages", 0),
            document_type=state.get("document_type"),
            analysis_confidence=state.get("analysis_confidence", 0.0),
            routed_parser=state.get("routed_parser_type", ""),
            layout_quality_score=state.get("layout_quality_score"),
            layout_applied=state.get("layout_applied", False),
            table_count=state.get("table_count", 0),
            table_flattened=state.get("table_flattened", False),
            chunk_count=state.get("chunk_count", 0),
            chunking_strategy=request.chunking_strategy,
            qdrant_indexed=state.get("qdrant_stored_count", 0),
            es_indexed=state.get("es_stored_count", 0),
            processing_time_ms=state.get("processing_time_ms", 0),
            step_timings=state.get("step_timings", {}),
            collection_name=request.collection_name,
            request_id=request.request_id,
            errors=state.get("errors", []),
        )
```

---

## 9. API Layer

### 9.1 `api/routes/advanced_ingest_router.py`

```python
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field

from src.application.advanced_ingest.use_case import AdvancedIngestUseCase
from src.domain.advanced_ingest.schemas import AdvancedIngestRequest


router = APIRouter(prefix="/api/v1/ingest/pdf", tags=["advanced-ingest"])


class AdvancedIngestAPIResponse(BaseModel):
    document_id: str
    filename: str
    user_id: str
    total_pages: int
    document_type: Optional[str] = None
    analysis_confidence: float = 0.0
    routed_parser: str = ""
    layout_quality_score: Optional[float] = None
    layout_applied: bool = False
    table_count: int = 0
    table_flattened: bool = False
    chunk_count: int = 0
    chunking_strategy: str = ""
    qdrant_indexed: int = 0
    es_indexed: int = 0
    processing_time_ms: int = 0
    step_timings: Dict[str, int] = Field(default_factory=dict)
    collection_name: str = ""
    request_id: str = ""
    errors: List[str] = Field(default_factory=list)


def get_advanced_ingest_use_case() -> AdvancedIngestUseCase:
    raise NotImplementedError("Configure AdvancedIngestUseCase dependency")


@router.post("/advanced", response_model=AdvancedIngestAPIResponse)
async def advanced_ingest_pdf(
    file: UploadFile = File(..., description="PDF file to ingest"),
    user_id: str = Query(..., description="Owner user ID"),
    collection_name: str = Query("documents", description="Collection name for Qdrant + ES"),
    chunking_strategy: str = Query("parent_child", description="full_token | parent_child | semantic"),
    chunk_size: int = Query(500, ge=100, le=8000, description="Tokens per chunk"),
    chunk_overlap: int = Query(50, ge=0, le=500, description="Overlap between chunks"),
    enable_layout_analysis: bool = Query(True, description="Enable layout analysis"),
    enable_table_flattening: bool = Query(True, description="Enable table flattening"),
    sample_pages: int = Query(3, ge=1, le=10, description="Pages to sample for analysis"),
    use_case: AdvancedIngestUseCase = Depends(get_advanced_ingest_use_case),
) -> AdvancedIngestAPIResponse:
    file_bytes = await file.read()
    filename = file.filename or "unknown.pdf"
    request_id = str(uuid.uuid4())

    request = AdvancedIngestRequest(
        filename=filename,
        user_id=user_id,
        request_id=request_id,
        file_bytes=file_bytes,
        collection_name=collection_name,
        chunking_strategy=chunking_strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        enable_layout_analysis=enable_layout_analysis,
        enable_table_flattening=enable_table_flattening,
        sample_pages=sample_pages,
    )

    result = await use_case.ingest(request)

    return AdvancedIngestAPIResponse(
        document_id=result.document_id,
        filename=result.filename,
        user_id=result.user_id,
        total_pages=result.total_pages,
        document_type=result.document_type,
        analysis_confidence=result.analysis_confidence,
        routed_parser=result.routed_parser,
        layout_quality_score=result.layout_quality_score,
        layout_applied=result.layout_applied,
        table_count=result.table_count,
        table_flattened=result.table_flattened,
        chunk_count=result.chunk_count,
        chunking_strategy=result.chunking_strategy,
        qdrant_indexed=result.qdrant_indexed,
        es_indexed=result.es_indexed,
        processing_time_ms=result.processing_time_ms,
        step_timings=result.step_timings,
        collection_name=result.collection_name,
        request_id=result.request_id,
        errors=result.errors,
    )
```

---

## 10. DI Registration (`create_app()`)

`src/api/main.py`의 `create_app()`에 추가할 DI 코드:

```python
from src.application.advanced_ingest.use_case import AdvancedIngestUseCase
from src.api.routes.advanced_ingest_router import (
    router as advanced_ingest_router,
    get_advanced_ingest_use_case,
)
from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer
from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.chunking.table_flattening.rule_based_generator import RuleBasedTableContentGenerator
from src.infrastructure.pdf_routing.default_parser_router import DefaultParserRouter

# --- Advanced Ingest DI ---
layout_analyzer = LayoutAnalyzer()
table_preprocessor = TableFlatteningPreprocessor(RuleBasedTableContentGenerator())
parser_router = DefaultParserRouter()

advanced_ingest_uc = AdvancedIngestUseCase(
    analyzer=pdf_analyzer,           # 기존 PyMuPDFAnalyzer 인스턴스
    router=parser_router,
    parsers=parser_registry,         # 기존 Dict[str, PDFParserInterface]
    layout_analyzer=layout_analyzer,
    table_preprocessor=table_preprocessor,
    morph_analyzer=morph_analyzer,   # 기존 KiwiMorphAnalyzer 인스턴스
    embedding=embedding,             # 기존 EmbeddingInterface 인스턴스
    vectorstore=vectorstore,         # 기존 VectorStoreInterface 인스턴스
    es_repo=es_repo,                 # 기존 ElasticsearchRepository 인스턴스
    logger=logger,
)

app.dependency_overrides[get_advanced_ingest_use_case] = lambda: advanced_ingest_uc
app.include_router(advanced_ingest_router)
```

---

## 11. Error Handling

### 11.1 노드별 에러 전략

| Node | 에러 시 동작 | status 설정 |
|------|------------|------------|
| analyze | errors에 기록, 후속 route_node에서 fallback | 계속 진행 |
| route | pymupdf fallback, errors에 기록 | 계속 진행 |
| parse | `status="failed"`, 파이프라인 중단 | **중단** |
| layout_analyze | 스킵, layout_applied=false | 계속 진행 |
| table_preprocess | 원본 documents 그대로 전달 | 계속 진행 |
| chunk | `status="failed"`, 파이프라인 중단 | **중단** |
| morph | morph_applied=false, 키워드 없이 저장 | 계속 진행 |
| dual_store | `status="failed"`, 파이프라인 중단 | **중단** |

### 11.2 에러 응답 포맷

파이프라인 실패 시에도 부분 결과를 반환:

```json
{
  "document_id": "doc-abc-123",
  "filename": "report.pdf",
  "total_pages": 10,
  "document_type": "table_heavy",
  "routed_parser": "pymupdf4llm",
  "chunk_count": 0,
  "qdrant_indexed": 0,
  "es_indexed": 0,
  "processing_time_ms": 1500,
  "step_timings": {"analyze": 200, "route": 5, "parse": 1200},
  "errors": ["Chunking failed: Invalid token count"],
  "request_id": "req-xyz-789"
}
```

---

## 12. Test Plan

### 12.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | 각 노드 함수 | pytest + AsyncMock |
| Unit Test | AdvancedPipelineState 초기화 | pytest |
| Unit Test | AdvancedIngestRequest/Result 검증 | pytest |
| Integration Test | LangGraph 파이프라인 전체 흐름 | pytest + mock 모듈 |
| Integration Test | API 엔드포인트 | pytest + httpx AsyncClient |

### 12.2 Key Test Cases

- [ ] Happy path: TEXT_HEAVY PDF → pymupdf → layout → chunk → morph → dual_store
- [ ] TABLE_HEAVY PDF → pymupdf4llm → layout → table_flattening → parent_child chunk → morph → dual_store
- [ ] OCR_HEAVY PDF → llamaparser → layout 스킵 → chunk → morph → dual_store
- [ ] Layout 품질 < 0.7 → fallback (layout_applied=false)
- [ ] enable_layout_analysis=false → layout 스킵
- [ ] enable_table_flattening=false → 표 전처리 스킵
- [ ] 파서 실패 → status="failed", 파이프라인 중단
- [ ] Morph 실패 → 키워드 없이 저장 계속
- [ ] ES 저장 실패 → status="failed" 기록
- [ ] 기존 `/api/v1/ingest/pdf` 무영향 확인

---

## 13. Implementation Order

| # | File | Layer | Dependencies | Size |
|---|------|-------|-------------|------|
| 1 | `domain/advanced_ingest/__init__.py` | Domain | - | XS |
| 2 | `domain/advanced_ingest/schemas.py` | Domain | pydantic | S |
| 3 | `infrastructure/pipeline/state/advanced_pipeline_state.py` | Infra | typing_extensions | S |
| 4 | `infrastructure/pipeline/nodes/analyze_node.py` | Infra | PDFAnalyzerInterface | S |
| 5 | `infrastructure/pipeline/nodes/route_node.py` | Infra | ParserRouterInterface | S |
| 6 | `infrastructure/pipeline/nodes/advanced_parse_node.py` | Infra | PDFParserInterface | S |
| 7 | `infrastructure/pipeline/nodes/layout_analyze_node.py` | Infra | LayoutAnalyzer | M |
| 8 | `infrastructure/pipeline/nodes/table_preprocess_node.py` | Infra | TableFlatteningPreprocessor | S |
| 9 | `infrastructure/pipeline/nodes/advanced_chunk_node.py` | Infra | ChunkingStrategyFactory | S |
| 10 | `infrastructure/pipeline/nodes/morph_node.py` | Infra | MorphAnalyzerInterface | S |
| 11 | `infrastructure/pipeline/nodes/dual_store_node.py` | Infra | Embedding + Vector + ES | M |
| 12 | `infrastructure/pipeline/graph/advanced_processing_graph.py` | Infra | all nodes | M |
| 13 | `application/advanced_ingest/__init__.py` | App | - | XS |
| 14 | `application/advanced_ingest/use_case.py` | App | graph + state | M |
| 15 | `api/routes/advanced_ingest_router.py` | API | UseCase | S |
| 16 | `api/main.py` (DI 추가) | API | 모든 컴포넌트 | S |

---

## 14. Clean Architecture Compliance

### 14.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| AdvancedIngestRequest/Result | Domain | `src/domain/advanced_ingest/schemas.py` |
| AdvancedIngestUseCase | Application | `src/application/advanced_ingest/use_case.py` |
| AdvancedPipelineState | Infrastructure | `src/infrastructure/pipeline/state/` |
| 9 pipeline nodes | Infrastructure | `src/infrastructure/pipeline/nodes/` |
| LangGraph workflow | Infrastructure | `src/infrastructure/pipeline/graph/` |
| Router endpoint | Interfaces (API) | `src/api/routes/` |

### 14.2 Dependency Rules

```
API (router) → Application (UseCase) → Domain (schemas)
                     ↓
              Infrastructure (graph, nodes, adapters)
                     ↓
              Domain Interfaces (PDFAnalyzerInterface, etc.)
```

- Domain 스키마는 외부 의존 없음 (pydantic만)
- Application은 Domain 인터페이스에만 의존
- Infrastructure는 Domain 인터페이스를 구현
- API는 Application UseCase만 호출

### 14.3 Coding Conventions

| Item | Convention |
|------|-----------|
| 네이밍 | snake_case (함수/변수), PascalCase (클래스) |
| 타입 | 모든 함수 파라미터 + 반환값 타입 명시 |
| 로깅 | LOG-001: StructuredLogger, INFO(시작/완료), ERROR(exception=) |
| 에러 처리 | 스택트레이스 포함 (`exception=exc`) |
| 함수 길이 | 40줄 이내 |
| if 중첩 | 2단계 이내 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-16 | Initial draft | 배상규 |
