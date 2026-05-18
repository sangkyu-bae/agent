# pdf-routing Planning Document

> **Summary**: PDFDocumentType 분석 결과를 입력받아 최적 파서를 자동 선택하고, DocumentCategory 기반 청킹 전략까지 연결하는 2단계 라우팅 모듈
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | pdf-analyzer가 PDF 유형(text/ocr/table/multimodal)을 분류하지만, 분류 결과를 파서 선택에 연결하는 계층이 없어 사용자가 parser_type을 수동 지정하거나 고정 파서만 사용 |
| **Solution** | 2단계 라우팅 모듈을 독립 계층으로 생성: 1단계 PDFDocumentType → 파서 선택, 2단계 DocumentCategory → 청킹 전략 선택. 기존 파이프라인을 건드리지 않는 별도 모듈로 안정화 후 통합 |
| **Function/UX Effect** | PDF 업로드 시 문서 특성에 맞는 파서가 자동 선택되어 파싱 품질 향상. 사용자는 parser_type을 알 필요 없이 최적 결과를 받음 |
| **Core Value** | "수동 파서 선택" → "분석 기반 자동 라우팅" 전환. 파서 추가 시 라우팅 매핑만 수정하면 되는 확장 가능한 구조 |

---

## 1. Overview

### 1.1 Purpose

pdf-analyzer가 반환하는 `AnalysisResult`(PDFDocumentType + SummaryMetrics)를 입력받아:
1. **1단계**: PDFDocumentType → 최적 파서(PDFParserInterface 구현체)를 선택
2. **2단계**: DocumentCategory → 최적 청킹 전략(ChunkingStrategy)을 선택

두 단계를 독립 모듈로 구현하며, 기존 ingest_router / document_upload 파이프라인은 건드리지 않는다.
추후 안정화 시 기존 파이프라인에 통합한다.

### 1.2 Background

현재 파싱 인프라 상태:
- **pdf-analyzer** (완성): PDF → `AnalysisResult(document_type, confidence, summary_metrics)` 반환
- **ParserFactory**: `ParserType` enum 기반 파서 생성 (pymupdf / pymupdf4llm / llamaparser)
- **ingest_router**: 사용자가 `parser_type` 쿼리 파라미터로 수동 선택
- **document_upload**: LangGraph 파이프라인에서 고정 파서 사용 (DI로 주입된 단일 파서)
- **DocumentCategory**: LLM 기반 문서 카테고리 분류 → 카테고리별 청킹 설정 매핑 (이미 존재)

**핵심 Gap**: pdf-analyzer의 분류 결과를 소비하여 파서를 자동 선택하는 라우팅 계층이 없음.

### 1.3 Related Documents

| Document | Path |
|----------|------|
| pdf-analyzer Plan (archived) | `docs/archive/2026-05/pdf-analyzer/pdf-analyzer.plan.md` |
| PDFAnalyzerInterface | `src/domain/pdf_analyzer/interfaces.py` |
| ClassificationPolicy | `src/domain/pdf_analyzer/policies.py` |
| PDFDocumentType enum | `src/domain/pdf_analyzer/schemas.py` |
| AnalyzePDFUseCase | `src/application/pdf_analyzer/use_case.py` |
| ParserFactory | `src/infrastructure/parser/parser_factory.py` |
| PDFParserInterface | `src/domain/parser/interfaces.py` |
| DocumentCategory enum | `src/domain/pipeline/enums/document_category.py` |
| 카테고리별 청킹 설정 | `src/domain/pipeline/config/chunking_strategy_config.py` |
| LangGraph 파이프라인 | `src/infrastructure/pipeline/graph/document_processing_graph.py` |
| docling-pdf-parser Plan | `docs/01-plan/features/docling-pdf-parser.plan.md` |

---

## 2. Scope

### 2.1 In Scope

| # | Item | Description |
|---|------|-------------|
| 1 | **RoutingDecision schema** | 라우팅 결과 VO: 선택된 ParserType, 선택 사유, confidence, fallback 여부 |
| 2 | **ParserRoutingPolicy** | domain policy: PDFDocumentType × confidence → ParserType 매핑 규칙 |
| 3 | **ParserRoutingConfig** | domain VO: 유형별 파서 매핑 설정 (외부 주입 가능) |
| 4 | **ParserRouterInterface** | domain interface: `route(AnalysisResult) -> RoutingDecision` |
| 5 | **DefaultParserRouter** | infrastructure 구현: ParserRoutingPolicy 기반 라우팅 |
| 6 | **RoutePDFUseCase** | application UseCase: analyze → route → 파서 생성까지 오케스트레이션 |
| 7 | **ChunkingRoutingPolicy** | domain policy: DocumentCategory → ChunkingConfig 매핑 (기존 `CATEGORY_CHUNKING_CONFIG` 활용) |
| 8 | **테스트** | TDD: 각 레이어별 테스트 먼저 작성 |

### 2.2 Out of Scope

| # | Item | Reason |
|---|------|--------|
| 1 | 기존 파이프라인 수정 | 독립 모듈로 먼저 안정화, 통합은 별도 feature |
| 2 | 새 파서 구현 (Docling, Camelot 등) | 라우팅 인터페이스만 확장 가능하게 설계, 파서 자체는 별도 feature |
| 3 | API 엔드포인트 추가 | 라우팅은 내부 서비스 계층, API 노출은 통합 시 결정 |
| 4 | LLM 기반 라우팅 | 1차는 rule-based, LLM 라우팅은 추후 확장 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | `AnalysisResult` 입력 → 최적 `ParserType` 반환 | Must |
| FR-02 | PDFDocumentType별 기본 파서 매핑: TEXT_HEAVY→pymupdf, TABLE_HEAVY→pymupdf4llm, OCR_HEAVY→llamaparser, MULTIMODAL→llamaparser | Must |
| FR-03 | confidence < 임계값일 때 fallback 파서 선택 (기본: pymupdf) | Must |
| FR-04 | 매핑 설정을 ParserRoutingConfig로 외부 주입 가능 | Must |
| FR-05 | 새 파서 타입 추가 시 매핑만 수정하면 되는 확장 구조 (OCP) | Should |
| FR-06 | DocumentCategory 기반 청킹 전략 선택 (기존 `CATEGORY_CHUNKING_CONFIG` 재활용) | Should |
| FR-07 | 라우팅 결과에 선택 사유(reasoning) 포함 | Should |
| FR-08 | AnalysisResult 없이 호출 시 기본 파서(pymupdf) 반환 | Must |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | 라우팅 결정 시간 < 1ms (순수 매핑 로직, I/O 없음) |
| NFR-02 | domain 레이어에 외부 라이브러리 의존 없음 |
| NFR-03 | LOG-001 준수: 라우팅 결정 로깅 (선택된 파서, 사유, confidence) |
| NFR-04 | 기존 ParserFactory, PDFParserInterface와 호환 (새 인터페이스 강제 아님) |

---

## 4. Architecture

### 4.1 Layer Design (Thin DDD)

```
domain/pdf_routing/
├── schemas.py              # RoutingDecision, RoutingReason
├── value_objects.py         # ParserRoutingConfig (유형별 파서 매핑 설정)
├── interfaces.py            # ParserRouterInterface (ABC)
└── policies.py              # ParserRoutingPolicy (매핑 규칙)

application/pdf_routing/
├── use_case.py              # RoutePDFUseCase
└── schemas.py               # RoutePDFRequest, RoutePDFResponse

infrastructure/pdf_routing/
└── default_parser_router.py # DefaultParserRouter (policy 기반 구현)
```

### 4.2 Data Flow (2단계 라우팅)

```
[PDF bytes]
    │
    ▼
┌─────────────────────────┐
│ AnalyzePDFUseCase       │  ← 기존 pdf-analyzer (변경 없음)
│ → AnalysisResult        │
│   (document_type,       │
│    confidence,           │
│    summary_metrics)      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ RoutePDFUseCase         │  ← NEW: 이번 feature
│                         │
│ 1단계: ParserRouting    │
│   AnalysisResult        │
│   → ParserRoutingPolicy │
│   → RoutingDecision     │
│     (parser_type,       │
│      reasoning,          │
│      is_fallback)        │
│                         │
│ 2단계: ChunkingRouting  │
│   DocumentCategory      │
│   → ChunkingConfig      │
│     (chunk_size,         │
│      chunk_overlap)      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ ParserFactory.create()  │  ← 기존 factory (변경 없음)
│ → PDFParserInterface    │
└─────────────────────────┘
```

### 4.3 ParserRoutingPolicy (기본 매핑 규칙)

```python
# domain/pdf_routing/policies.py

DEFAULT_ROUTING_MAP = {
    PDFDocumentType.TEXT_HEAVY:  ParserType.PYMUPDF,       # 빠르고 정확
    PDFDocumentType.OCR_HEAVY:  ParserType.LLAMAPARSER,    # OCR 지원
    PDFDocumentType.TABLE_HEAVY: ParserType.PYMUPDF4LLM,   # 마크다운 표 보존
    PDFDocumentType.MULTIMODAL:  ParserType.LLAMAPARSER,   # AI 기반 멀티모달
}

FALLBACK_PARSER = ParserType.PYMUPDF  # confidence 낮을 때 안전한 기본값

# 라우팅 규칙:
# 1. confidence >= threshold → DEFAULT_ROUTING_MAP[document_type]
# 2. confidence < threshold → FALLBACK_PARSER
# 3. AnalysisResult 없음 → FALLBACK_PARSER
```

### 4.4 확장 포인트

새 파서 추가 시 변경 범위:

| 작업 | 변경 파일 | 영향 |
|------|----------|------|
| 파서 구현 추가 (예: Docling) | `infrastructure/parser/docling_parser.py` | 새 파일 |
| ParserType enum 추가 | `infrastructure/parser/parser_factory.py` | 기존 파일 수정 |
| 라우팅 매핑 추가 | `domain/pdf_routing/value_objects.py` (config) | 매핑만 추가 |
| ParserFactory에 생성 로직 | `infrastructure/parser/parser_factory.py` | 분기 추가 |

> ParserRouterInterface, ParserRoutingPolicy, RoutePDFUseCase는 변경 불필요 (OCP).

---

## 5. Detailed Design

### 5.1 Domain Layer

#### 5.1.1 RoutingDecision (Schema)

```python
class RoutingReason(str, Enum):
    DOCUMENT_TYPE_MATCH = "document_type_match"    # 유형에 맞는 최적 파서
    LOW_CONFIDENCE_FALLBACK = "low_confidence_fallback"  # confidence 부족
    NO_ANALYSIS_FALLBACK = "no_analysis_fallback"  # 분석 결과 없음
    CONFIG_OVERRIDE = "config_override"            # 설정으로 강제 지정

class RoutingDecision(BaseModel):
    parser_type: str          # ParserType.value (pymupdf, pymupdf4llm, llamaparser)
    document_type: Optional[str]  # PDFDocumentType.value (분석 결과 있을 때)
    confidence: float         # 분석 confidence (0.0 if no analysis)
    reason: RoutingReason     # 선택 사유
    is_fallback: bool         # fallback으로 선택되었는지
```

#### 5.1.2 ParserRoutingConfig (VO)

```python
@dataclass(frozen=True)
class ParserRoutingConfig:
    routing_map: Dict[str, str]   # PDFDocumentType.value → ParserType.value
    fallback_parser: str          # 기본 fallback (default: "pymupdf")
    confidence_threshold: float   # fallback 전환 임계값 (default: 0.5)
```

- `routing_map`은 string 기반으로 하여 domain이 infrastructure의 ParserType enum에 의존하지 않도록 함
- 기본값은 4.3의 DEFAULT_ROUTING_MAP을 string으로 변환

#### 5.1.3 ParserRouterInterface (ABC)

```python
class ParserRouterInterface(ABC):
    @abstractmethod
    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        pass
```

#### 5.1.4 ParserRoutingPolicy (Policy)

```python
class ParserRoutingPolicy:
    @staticmethod
    def decide(
        analysis_result: Optional[AnalysisResult],
        config: ParserRoutingConfig,
    ) -> RoutingDecision:
        # 1. 분석 결과 없으면 fallback
        if analysis_result is None:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=None,
                confidence=0.0,
                reason=RoutingReason.NO_ANALYSIS_FALLBACK,
                is_fallback=True,
            )

        # 2. confidence < threshold → fallback
        if analysis_result.confidence < config.confidence_threshold:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=analysis_result.document_type.value,
                confidence=analysis_result.confidence,
                reason=RoutingReason.LOW_CONFIDENCE_FALLBACK,
                is_fallback=True,
            )

        # 3. 유형별 매핑
        doc_type_value = analysis_result.document_type.value
        parser = config.routing_map.get(doc_type_value, config.fallback_parser)
        return RoutingDecision(
            parser_type=parser,
            document_type=doc_type_value,
            confidence=analysis_result.confidence,
            reason=RoutingReason.DOCUMENT_TYPE_MATCH,
            is_fallback=False,
        )
```

### 5.2 Application Layer

#### 5.2.1 RoutePDFUseCase

```python
class RoutePDFUseCase:
    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        router: ParserRouterInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self,
        request: RoutePDFRequest,
    ) -> RoutePDFResponse:
        # 1. pdf-analyzer로 PDF 유형 분석
        analysis_result = await self._analyze(request)
        # 2. 분석 결과로 파서 라우팅
        routing_decision = self._router.route(analysis_result)
        # 3. 로깅: 선택된 파서, 사유, confidence
        # 4. RoutePDFResponse 반환
```

#### 5.2.2 Request/Response

```python
class RoutePDFRequest(BaseModel):
    filename: str
    user_id: str
    request_id: str
    file_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    sample_pages: Optional[int] = None
    routing_config: Optional[ParserRoutingConfig] = None

class RoutePDFResponse(BaseModel):
    parser_type: str
    document_type: Optional[str]
    confidence: float
    reason: str
    is_fallback: bool
    request_id: str
```

### 5.3 Infrastructure Layer

#### 5.3.1 DefaultParserRouter

```python
class DefaultParserRouter(ParserRouterInterface):
    def __init__(
        self,
        config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._config = config or self._default_config()

    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        effective_config = config or self._config
        return ParserRoutingPolicy.decide(analysis_result, effective_config)

    @staticmethod
    def _default_config() -> ParserRoutingConfig:
        return ParserRoutingConfig(
            routing_map={
                "text_heavy": "pymupdf",
                "ocr_heavy": "llamaparser",
                "table_heavy": "pymupdf4llm",
                "multimodal": "llamaparser",
            },
            fallback_parser="pymupdf",
            confidence_threshold=0.5,
        )
```

---

## 6. Implementation Order

| Phase | Task | Files | Dependency |
|-------|------|-------|------------|
| 1 | Domain 스키마/VO 정의 | `domain/pdf_routing/schemas.py`, `value_objects.py` | None |
| 2 | Domain 인터페이스 + 라우팅 정책 | `domain/pdf_routing/interfaces.py`, `policies.py` | Phase 1 |
| 3 | Infrastructure 구현 (DefaultParserRouter) | `infrastructure/pdf_routing/default_parser_router.py` | Phase 2 |
| 4 | Application UseCase + schemas | `application/pdf_routing/use_case.py`, `schemas.py` | Phase 3 |
| 5 | 테스트 (TDD: 각 Phase에서 테스트 먼저) | `tests/domain/pdf_routing/`, `tests/application/pdf_routing/`, `tests/infrastructure/pdf_routing/` | All |

---

## 7. Testing Strategy

### 7.1 Domain Tests

| Test | Description |
|------|-------------|
| `test_routing_policy_text_heavy` | TEXT_HEAVY + confidence >= 0.5 → pymupdf |
| `test_routing_policy_ocr_heavy` | OCR_HEAVY + confidence >= 0.5 → llamaparser |
| `test_routing_policy_table_heavy` | TABLE_HEAVY + confidence >= 0.5 → pymupdf4llm |
| `test_routing_policy_multimodal` | MULTIMODAL + confidence >= 0.5 → llamaparser |
| `test_routing_policy_low_confidence_fallback` | confidence < 0.5 → fallback (pymupdf) |
| `test_routing_policy_no_analysis` | AnalysisResult=None → fallback (pymupdf) |
| `test_routing_policy_custom_config` | 커스텀 routing_map 적용 검증 |
| `test_routing_config_validation` | 잘못된 설정값 검증 |
| `test_routing_decision_is_fallback_flag` | is_fallback 플래그 정확성 |
| `test_routing_reason_enum` | 각 사유 enum 정확성 |

### 7.2 Infrastructure Tests

| Test | Description |
|------|-------------|
| `test_default_router_with_analysis` | 정상 분석 결과 → 올바른 파서 선택 |
| `test_default_router_without_analysis` | None 입력 → fallback |
| `test_default_router_custom_config` | 커스텀 config 오버라이드 |
| `test_default_router_unknown_type_fallback` | 매핑에 없는 유형 → fallback |

### 7.3 Application Tests

| Test | Description |
|------|-------------|
| `test_route_pdf_use_case_success` | 정상 분석 + 라우팅 흐름 |
| `test_route_pdf_use_case_logging` | LOG-001 준수: 라우팅 결정 로깅 |
| `test_route_pdf_use_case_analyzer_error` | 분석 실패 시 fallback 동작 |
| `test_route_pdf_use_case_no_file` | file_bytes/file_path 둘 다 없으면 에러 |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LlamaParse API 비용 증가 | OCR/MULTIMODAL 문서가 많으면 API 비용 상승 | confidence threshold 조정으로 불확실한 문서는 pymupdf fallback |
| 분류 오류로 부적합한 파서 선택 | 파싱 품질 저하 | RoutingDecision에 is_fallback/reason 기록, 로그 기반 모니터링 |
| 기존 파이프라인과의 통합 복잡도 | 통합 시 breaking change | 독립 모듈로 먼저 안정화, 통합은 adapter 패턴으로 |
| 새 파서 추가 시 ParserType enum 확장 필요 | ParserFactory 수정 필요 | string 기반 매핑으로 domain은 enum에 의존하지 않음 |

---

## 9. Future Extensions

| Extension | Description | Trigger |
|-----------|-------------|---------|
| 파이프라인 통합 | document_upload LangGraph에 analyze→route 노드 추가 | 라우팅 모듈 안정화 후 |
| ingest_router 통합 | parser_type 수동 선택 → 자동 라우팅 옵션 추가 | 라우팅 모듈 안정화 후 |
| Docling 파서 연동 | 라우팅 매핑에 Docling 추가 | docling-pdf-parser feature 완료 후 |
| LLM 기반 라우팅 | rule-based → LLM classifier로 교체 | 분류 정확도 개선 필요 시 |
| 라우팅 A/B 테스트 | 파서 성능 비교를 위한 실험 프레임워크 | 파서 3종 이상일 때 |
| 파서별 성능 메트릭 수집 | 파싱 시간, 품질 점수 기록 | 라우팅 최적화 필요 시 |
| 복합 라우팅 (페이지별) | 한 PDF 내에서 페이지별로 다른 파서 적용 | 멀티모달 문서 품질 이슈 시 |
