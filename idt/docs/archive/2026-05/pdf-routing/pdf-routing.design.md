# pdf-routing Design Document

> **Summary**: PDFDocumentType 기반 파서 자동 선택 + DocumentCategory 기반 청킹 전략 연결 — 2단계 라우팅 모듈 상세 설계
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-13
> **Status**: Draft
> **Planning Doc**: [pdf-routing.plan.md](../../01-plan/features/pdf-routing.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. pdf-analyzer의 `AnalysisResult`를 입력받아 **최적 파서를 자동 선택**하는 라우팅 계층 구현
2. 기존 `ParserFactory`, `PDFParserInterface`, `ingest_router`, `document_upload` 파이프라인 **변경 없음**
3. 새 파서 추가 시 **매핑 설정만 변경** — 라우팅 코어 수정 불필요 (OCP)
4. string 기반 매핑으로 **domain → infrastructure 의존 차단**

### 1.2 Design Principles

- **Separation of Concerns**: 분석(pdf-analyzer) / 라우팅(pdf-routing) / 파싱(parser) 각각 독립
- **Policy Pattern**: 라우팅 규칙을 domain policy로 분리하여 테스트·교체 용이
- **Configuration-Driven**: 매핑 테이블을 VO로 외부 주입 가능하게 하여 환경별 튜닝 지원
- **Graceful Fallback**: 분석 실패·저신뢰도 시 안전한 기본 파서로 자동 전환

---

## 2. Architecture

### 2.1 전체 데이터 흐름

```
[PDF bytes/path]
    │
    ▼
┌─────────────────────────────────────┐
│ RoutePDFUseCase.execute()           │  ← application layer (NEW)
│                                     │
│  ┌────────────────────────┐         │
│  │ 1. PDF 분석             │         │
│  │ PDFAnalyzerInterface    │         │  ← 기존 pdf-analyzer (변경 없음)
│  │ .analyze_bytes()        │         │
│  │ → AnalysisResult        │         │
│  │   {document_type,       │         │
│  │    confidence,           │         │
│  │    summary_metrics}      │         │
│  └──────────┬─────────────┘         │
│             │                       │
│             ▼                       │
│  ┌────────────────────────┐         │
│  │ 2. 파서 라우팅 (1단계)  │         │
│  │ ParserRouterInterface   │         │  ← NEW: 이번 feature
│  │ .route(analysis_result) │         │
│  │ → RoutingDecision       │         │
│  │   {parser_type,          │         │
│  │    reason,               │         │
│  │    is_fallback}          │         │
│  └──────────┬─────────────┘         │
│             │                       │
│             ▼                       │
│  ┌────────────────────────┐         │
│  │ 3. 청킹 라우팅 (2단계)  │         │  ← 기존 매핑 재활용
│  │ (optional, category 전달 │         │
│  │  시에만 동작)            │         │
│  └──────────┬─────────────┘         │
│             │                       │
│  → RoutePDFResponse                 │
└─────────────┬───────────────────────┘
              │
              ▼  (호출자가 결과 소비)
┌─────────────────────────────────────┐
│ ParserFactory.create(parser_type)   │  ← 기존 factory (변경 없음)
│ → PDFParserInterface 구현체          │
└─────────────────────────────────────┘
```

### 2.2 레이어 구조

```
src/
├── domain/pdf_routing/
│   ├── __init__.py
│   ├── schemas.py           # RoutingDecision, RoutingReason
│   ├── value_objects.py     # ParserRoutingConfig
│   ├── interfaces.py        # ParserRouterInterface (ABC)
│   └── policies.py          # ParserRoutingPolicy
│
├── application/pdf_routing/
│   ├── __init__.py
│   ├── schemas.py           # RoutePDFRequest, RoutePDFResponse
│   └── use_case.py          # RoutePDFUseCase
│
├── infrastructure/pdf_routing/
│   ├── __init__.py
│   └── default_parser_router.py  # DefaultParserRouter
│
tests/
├── domain/pdf_routing/
│   ├── __init__.py
│   ├── test_schemas.py
│   ├── test_value_objects.py
│   └── test_policies.py
│
├── application/pdf_routing/
│   ├── __init__.py
│   └── test_use_case.py
│
└── infrastructure/pdf_routing/
    ├── __init__.py
    └── test_default_parser_router.py
```

### 2.3 의존성 방향

```
domain/pdf_routing        ← 외부 의존 없음
    │                        (pdf_analyzer의 AnalysisResult, schemas만 참조)
    │
application/pdf_routing   ← domain/pdf_routing
    │                        domain/pdf_analyzer (AnalysisResult 타입만)
    │                        domain/logging (LoggerInterface)
    │
infrastructure/pdf_routing ← domain/pdf_routing
                              (ParserRouterInterface, ParserRoutingPolicy 사용)
```

> domain/pdf_routing은 infrastructure의 `ParserType` enum을 참조하지 않는다. routing_map의 key/value는 모두 string이며, ParserFactory와의 연결은 호출자(application) 책임이다.

---

## 3. Detailed Design

### 3.1 Domain Layer — `domain/pdf_routing/`

#### 3.1.1 `schemas.py` — RoutingDecision, RoutingReason

```python
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RoutingReason(str, Enum):
    DOCUMENT_TYPE_MATCH = "document_type_match"
    LOW_CONFIDENCE_FALLBACK = "low_confidence_fallback"
    NO_ANALYSIS_FALLBACK = "no_analysis_fallback"
    CONFIG_OVERRIDE = "config_override"


class RoutingDecision(BaseModel):
    parser_type: str
    document_type: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: RoutingReason
    is_fallback: bool

    model_config = {"frozen": True}
```

**설계 결정**:
- `parser_type`은 `str`로 선언 — domain이 infrastructure의 `ParserType` enum에 의존하지 않도록 함
- `document_type`도 `Optional[str]` — 분석 결과 없는 경우 `None`
- `frozen=True` — immutable value object

#### 3.1.2 `value_objects.py` — ParserRoutingConfig

```python
from dataclasses import dataclass, field
from typing import Dict


DEFAULT_ROUTING_MAP: Dict[str, str] = {
    "text_heavy": "pymupdf",
    "ocr_heavy": "llamaparser",
    "table_heavy": "pymupdf4llm",
    "multimodal": "llamaparser",
}

DEFAULT_FALLBACK_PARSER: str = "pymupdf"
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.5


@dataclass(frozen=True)
class ParserRoutingConfig:
    routing_map: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ROUTING_MAP)
    )
    fallback_parser: str = DEFAULT_FALLBACK_PARSER
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError(
                "confidence_threshold must be between 0.0 and 1.0"
            )
        if not self.fallback_parser or not self.fallback_parser.strip():
            raise ValueError("fallback_parser cannot be empty")
        if not isinstance(self.routing_map, dict):
            raise ValueError("routing_map must be a dict")
```

**설계 결정**:
- `routing_map`의 key = `PDFDocumentType.value` (string), value = `ParserType.value` (string)
- 기본값을 모듈 상수 `DEFAULT_ROUTING_MAP`으로 분리 — 테스트에서 참조 가능
- `confidence_threshold` 기본 0.5 — pdf-analyzer의 ClassificationPolicy가 반환하는 confidence와 비교
- 새 파서 추가 시: `routing_map`에 엔트리 추가만으로 확장 완료

#### 3.1.3 `interfaces.py` — ParserRouterInterface

```python
from abc import ABC, abstractmethod
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.schemas import RoutingDecision
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class ParserRouterInterface(ABC):

    @abstractmethod
    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        pass
```

**설계 결정**:
- `analysis_result`는 `Optional` — 분석 실패나 분석 없이 라우팅이 필요한 경우 대응
- `config`도 `Optional` — 기본 설정을 사용하되, 호출 시점에 오버라이드 가능
- 반환값 `RoutingDecision`은 immutable — 라우팅 결과를 로깅/감사에 활용

#### 3.1.4 `policies.py` — ParserRoutingPolicy

```python
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class ParserRoutingPolicy:

    @staticmethod
    def decide(
        analysis_result: Optional[AnalysisResult],
        config: ParserRoutingConfig,
    ) -> RoutingDecision:
        if analysis_result is None:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=None,
                confidence=0.0,
                reason=RoutingReason.NO_ANALYSIS_FALLBACK,
                is_fallback=True,
            )

        if analysis_result.confidence < config.confidence_threshold:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=analysis_result.document_type.value,
                confidence=analysis_result.confidence,
                reason=RoutingReason.LOW_CONFIDENCE_FALLBACK,
                is_fallback=True,
            )

        doc_type_value = analysis_result.document_type.value
        matched_parser = config.routing_map.get(
            doc_type_value, config.fallback_parser
        )
        is_fallback = doc_type_value not in config.routing_map

        return RoutingDecision(
            parser_type=matched_parser,
            document_type=doc_type_value,
            confidence=analysis_result.confidence,
            reason=(
                RoutingReason.DOCUMENT_TYPE_MATCH
                if not is_fallback
                else RoutingReason.LOW_CONFIDENCE_FALLBACK
            ),
            is_fallback=is_fallback,
        )
```

**라우팅 결정 로직 (우선순위)**:

```
1. analysis_result == None
   → fallback_parser, reason=NO_ANALYSIS_FALLBACK

2. analysis_result.confidence < confidence_threshold
   → fallback_parser, reason=LOW_CONFIDENCE_FALLBACK

3. document_type가 routing_map에 있음
   → routing_map[document_type], reason=DOCUMENT_TYPE_MATCH

4. document_type가 routing_map에 없음 (미등록 유형)
   → fallback_parser, reason=LOW_CONFIDENCE_FALLBACK, is_fallback=True
```

---

### 3.2 Application Layer — `application/pdf_routing/`

#### 3.2.1 `schemas.py` — RoutePDFRequest, RoutePDFResponse

```python
from typing import Optional

from pydantic import BaseModel, field_validator


class RoutePDFRequest(BaseModel):
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


class RoutePDFResponse(BaseModel):
    parser_type: str
    document_type: Optional[str] = None
    confidence: float
    reason: str
    is_fallback: bool
    analysis_summary: Optional[dict] = None
    request_id: str
```

**설계 결정**:
- `RoutePDFRequest`는 기존 `AnalyzePDFRequest`와 동일한 validator 패턴 — 일관성 유지
- `RoutePDFResponse.analysis_summary`는 optional dict — 호출자가 분석 메트릭을 함께 받을 수 있음
- `ParserRoutingConfig`는 Request에 포함하지 않음 — UseCase 생성자에서 DI로 주입

#### 3.2.2 `use_case.py` — RoutePDFUseCase

```python
import asyncio
from typing import Optional

from src.application.pdf_routing.schemas import RoutePDFRequest, RoutePDFResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.schemas import RoutingDecision
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class RoutePDFUseCase:

    def __init__(
        self,
        analyzer: PDFAnalyzerInterface,
        router: ParserRouterInterface,
        logger: LoggerInterface,
        routing_config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._analyzer = analyzer
        self._router = router
        self._logger = logger
        self._routing_config = routing_config

    async def execute(
        self,
        request: RoutePDFRequest,
    ) -> RoutePDFResponse:
        self._logger.info(
            "PDF routing started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
        )

        # 1. PDF 분석
        analysis_result = await self._analyze(request)

        # 2. 파서 라우팅
        decision = self._router.route(
            analysis_result=analysis_result,
            config=self._routing_config,
        )

        # 3. 로깅
        self._logger.info(
            "PDF routing completed",
            request_id=request.request_id,
            filename=request.filename,
            parser_type=decision.parser_type,
            document_type=decision.document_type,
            confidence=decision.confidence,
            reason=decision.reason.value,
            is_fallback=decision.is_fallback,
        )

        # 4. Response 구성
        analysis_summary = None
        if analysis_result is not None:
            analysis_summary = {
                "total_pages": analysis_result.total_pages,
                "sampled_pages": analysis_result.sampled_pages,
                "avg_text_chars": analysis_result.summary_metrics.avg_text_chars,
                "avg_table_count": analysis_result.summary_metrics.avg_table_count,
                "avg_image_area_ratio": analysis_result.summary_metrics.avg_image_area_ratio,
                "extractable_text_ratio": analysis_result.summary_metrics.extractable_text_ratio,
            }

        return RoutePDFResponse(
            parser_type=decision.parser_type,
            document_type=decision.document_type,
            confidence=decision.confidence,
            reason=decision.reason.value,
            is_fallback=decision.is_fallback,
            analysis_summary=analysis_summary,
            request_id=request.request_id,
        )

    async def _analyze(
        self,
        request: RoutePDFRequest,
    ) -> Optional[AnalysisResult]:
        analysis_config = None
        if request.sample_pages is not None:
            analysis_config = AnalysisConfig(sample_pages=request.sample_pages)

        try:
            if request.file_bytes is not None:
                return await asyncio.to_thread(
                    self._analyzer.analyze_bytes,
                    file_bytes=request.file_bytes,
                    config=analysis_config,
                )
            elif request.file_path is not None:
                return await asyncio.to_thread(
                    self._analyzer.analyze_path,
                    file_path=request.file_path,
                    config=analysis_config,
                )
            else:
                raise ValueError(
                    "Either file_bytes or file_path must be provided"
                )
        except Exception as exc:
            self._logger.error(
                "PDF analysis failed, using fallback routing",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            return None
```

**핵심 설계 포인트**:

1. **분석 실패 → fallback**: `_analyze()`에서 예외 발생 시 `None` 반환 → `ParserRoutingPolicy`가 fallback 처리
2. **분석은 sync 함수**: `PDFAnalyzerInterface.analyze_bytes()`는 동기 함수이므로 `asyncio.to_thread()` 래핑 (기존 `AnalyzePDFUseCase`와 동일 패턴)
3. **routing_config DI**: 생성자에서 주입하여 환경별(dev/staging/prod) 다른 매핑 사용 가능
4. **analysis_summary 전달**: 라우팅 결과와 함께 분석 메트릭을 반환하여 호출자가 모니터링에 활용

---

### 3.3 Infrastructure Layer — `infrastructure/pdf_routing/`

#### 3.3.1 `default_parser_router.py` — DefaultParserRouter

```python
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.policies import ParserRoutingPolicy
from src.domain.pdf_routing.schemas import RoutingDecision
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class DefaultParserRouter(ParserRouterInterface):

    def __init__(
        self,
        config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._config = config or ParserRoutingConfig()

    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        effective_config = config or self._config
        return ParserRoutingPolicy.decide(analysis_result, effective_config)
```

**설계 결정**:
- `DefaultParserRouter`는 얇은 어댑터 — 실제 로직은 `ParserRoutingPolicy`에 위임
- 생성자 config가 기본값, `route()` 호출 시 config가 오버라이드
- 추후 LLM 기반 라우터 추가 시 `LLMParserRouter(ParserRouterInterface)` 구현체만 추가

---

## 4. 기존 코드와의 연결 지점

### 4.1 기존 코드 참조 (변경 없음)

| 기존 코드 | 사용 방식 | 변경 여부 |
|----------|----------|----------|
| `src/domain/pdf_analyzer/schemas.py` → `AnalysisResult`, `PDFDocumentType` | Policy에서 타입 참조 | 변경 없음 |
| `src/domain/pdf_analyzer/interfaces.py` → `PDFAnalyzerInterface` | UseCase에서 분석 호출 | 변경 없음 |
| `src/domain/pdf_analyzer/value_objects.py` → `AnalysisConfig` | UseCase에서 config 생성 | 변경 없음 |
| `src/infrastructure/pdf_analyzer/pymupdf_analyzer.py` → `PyMuPDFAnalyzer` | DI로 UseCase에 주입 | 변경 없음 |
| `src/infrastructure/parser/parser_factory.py` → `ParserFactory` | 호출자가 routing 결과로 파서 생성 | 변경 없음 |
| `src/domain/pipeline/config/chunking_strategy_config.py` → `CATEGORY_CHUNKING_CONFIG` | 2단계 청킹 라우팅에서 재활용 | 변경 없음 |

### 4.2 호출자 사용 예시 (통합 시 참고)

```python
# 호출자 (ingest_router 또는 document_upload 통합 시)
route_result = await route_pdf_use_case.execute(request)

# 1단계 결과: 파서 선택
parser = ParserFactory.create_from_string(
    type_str=route_result.parser_type,
    api_key=llamaparse_api_key if route_result.parser_type == "llamaparser" else None,
)

# 2단계: 청킹 전략 (기존 파이프라인에서 이미 처리)
# document_upload의 classify_node → CATEGORY_CHUNKING_CONFIG 매핑은 기존 그대로 유지
```

---

## 5. Implementation Order

| Phase | Task | Files | TDD 순서 |
|-------|------|-------|----------|
| 1 | Domain 스키마 | `domain/pdf_routing/schemas.py` | test_schemas.py → schemas.py |
| 2 | Domain VO | `domain/pdf_routing/value_objects.py` | test_value_objects.py → value_objects.py |
| 3 | Domain 인터페이스 | `domain/pdf_routing/interfaces.py` | (ABC이므로 테스트 불필요) |
| 4 | Domain Policy | `domain/pdf_routing/policies.py` | test_policies.py → policies.py |
| 5 | Infrastructure Router | `infrastructure/pdf_routing/default_parser_router.py` | test_default_parser_router.py → default_parser_router.py |
| 6 | Application Schemas | `application/pdf_routing/schemas.py` | (validator 테스트 포함) |
| 7 | Application UseCase | `application/pdf_routing/use_case.py` | test_use_case.py → use_case.py |

> 각 Phase에서 **테스트 먼저** 작성 (Red) → 구현 (Green) → 리팩토링

---

## 6. Testing Strategy

### 6.1 Domain Tests — `tests/domain/pdf_routing/`

#### `test_schemas.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_routing_decision_creation` | 유효한 모든 필드 | 정상 생성 |
| `test_routing_decision_frozen` | 생성 후 필드 수정 시도 | ValidationError (frozen) |
| `test_routing_reason_values` | 각 RoutingReason enum | 올바른 string value |
| `test_routing_decision_confidence_bounds` | confidence=-0.1, 1.1 | ValidationError |

#### `test_value_objects.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_default_config` | `ParserRoutingConfig()` | DEFAULT_ROUTING_MAP, "pymupdf", 0.5 |
| `test_custom_config` | 커스텀 routing_map | 커스텀 값 반영 |
| `test_invalid_threshold_low` | confidence_threshold=-0.1 | ValueError |
| `test_invalid_threshold_high` | confidence_threshold=1.1 | ValueError |
| `test_empty_fallback_parser` | fallback_parser="" | ValueError |
| `test_custom_routing_map_with_new_parser` | `{"text_heavy": "docling"}` | 정상 생성 |

#### `test_policies.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_text_heavy_routes_to_pymupdf` | TEXT_HEAVY, confidence=0.8 | "pymupdf", DOCUMENT_TYPE_MATCH |
| `test_ocr_heavy_routes_to_llamaparser` | OCR_HEAVY, confidence=0.9 | "llamaparser", DOCUMENT_TYPE_MATCH |
| `test_table_heavy_routes_to_pymupdf4llm` | TABLE_HEAVY, confidence=0.7 | "pymupdf4llm", DOCUMENT_TYPE_MATCH |
| `test_multimodal_routes_to_llamaparser` | MULTIMODAL, confidence=0.6 | "llamaparser", DOCUMENT_TYPE_MATCH |
| `test_low_confidence_fallback` | TEXT_HEAVY, confidence=0.3 | "pymupdf", LOW_CONFIDENCE_FALLBACK |
| `test_no_analysis_fallback` | None | "pymupdf", NO_ANALYSIS_FALLBACK |
| `test_boundary_confidence_at_threshold` | confidence=0.5 (== threshold) | DOCUMENT_TYPE_MATCH (>= 이므로) |
| `test_boundary_confidence_below_threshold` | confidence=0.49 | LOW_CONFIDENCE_FALLBACK |
| `test_unknown_document_type_fallback` | routing_map에 없는 type | fallback_parser, is_fallback=True |
| `test_custom_config_override` | `{"text_heavy": "docling"}` | "docling" |
| `test_custom_fallback_parser` | fallback="pymupdf4llm" | "pymupdf4llm" on fallback |
| `test_custom_threshold` | threshold=0.8, confidence=0.6 | fallback |

### 6.2 Infrastructure Tests — `tests/infrastructure/pdf_routing/`

#### `test_default_parser_router.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_route_with_default_config` | TEXT_HEAVY, confidence=0.8 | "pymupdf" |
| `test_route_without_analysis` | None | "pymupdf", is_fallback=True |
| `test_route_with_constructor_config` | 커스텀 config in __init__ | 커스텀 매핑 적용 |
| `test_route_with_call_config_override` | 다른 config in route() 호출 | 호출 시 config 우선 |
| `test_route_config_precedence` | 생성자 config + 호출 config | 호출 config 우선 |

### 6.3 Application Tests — `tests/application/pdf_routing/`

#### `test_use_case.py`

| Test | Mock 설정 | Expected |
|------|----------|----------|
| `test_execute_success_text_heavy` | analyzer → TEXT_HEAVY(0.8), router → pymupdf | parser_type="pymupdf", is_fallback=False |
| `test_execute_success_ocr_heavy` | analyzer → OCR_HEAVY(0.9), router → llamaparser | parser_type="llamaparser" |
| `test_execute_analyzer_failure_fallback` | analyzer → raise Exception | parser_type="pymupdf", is_fallback=True |
| `test_execute_no_file_raises` | file_bytes=None, file_path=None | ValueError |
| `test_execute_logging_on_success` | 정상 흐름 | logger.info 2회 (start, completed) |
| `test_execute_logging_on_analyzer_error` | analyzer 예외 | logger.error 1회 + logger.info 2회 |
| `test_execute_with_file_path` | file_path="/tmp/test.pdf" | analyze_path 호출 |
| `test_execute_with_sample_pages` | sample_pages=3 | AnalysisConfig(sample_pages=3) 전달 |
| `test_execute_analysis_summary_included` | 정상 분석 | analysis_summary != None |
| `test_execute_analysis_summary_none_on_failure` | 분석 실패 | analysis_summary == None |

### 6.4 테스트 헬퍼

```python
# tests/domain/pdf_routing/conftest.py

def make_analysis_result(
    document_type: PDFDocumentType = PDFDocumentType.TEXT_HEAVY,
    confidence: float = 0.8,
    total_pages: int = 10,
    sampled_pages: int = 5,
) -> AnalysisResult:
    """AnalysisResult 테스트 팩토리."""
    page_features = [
        PageFeatures(
            page_number=i + 1,
            text_char_count=500,
            image_count=0,
            image_area_ratio=0.0,
            table_count=0,
            has_extractable_text=True,
        )
        for i in range(sampled_pages)
    ]
    summary = SummaryMetrics(
        avg_text_chars=500.0,
        avg_image_count=0.0,
        avg_image_area_ratio=0.0,
        avg_table_count=0.0,
        extractable_text_ratio=1.0,
    )
    return AnalysisResult(
        document_type=document_type,
        confidence=confidence,
        total_pages=total_pages,
        sampled_pages=sampled_pages,
        page_features=page_features,
        summary_metrics=summary,
    )
```

---

## 7. Error Handling

| Scenario | 처리 방식 | 결과 |
|----------|----------|------|
| `AnalyzePDFUseCase` 예외 (fitz 오류 등) | UseCase에서 catch → `None` 반환 → Policy fallback | pymupdf fallback |
| file_bytes와 file_path 모두 None | UseCase에서 `ValueError` raise | 호출자에게 전파 |
| routing_map에 없는 document_type | Policy에서 `config.routing_map.get()` → fallback | fallback_parser |
| `ParserRoutingConfig` 검증 실패 | `__post_init__`에서 `ValueError` | DI 시점에 실패 (앱 시작 시) |

---

## 8. Future Extension Points

| Extension | 설계 대응 |
|-----------|----------|
| **Docling 파서 추가** | `ParserRoutingConfig.routing_map`에 `"table_heavy": "docling"` 추가만으로 완료 |
| **LLM 기반 라우팅** | `LLMParserRouter(ParserRouterInterface)` 구현체 추가, DI로 교체 |
| **페이지별 라우팅** | `RoutingDecision`을 리스트로 확장하거나 `PageRoutingDecision` 별도 정의 |
| **A/B 테스트** | `ABTestParserRouter`에서 2개 라우터를 래핑, 비율 기반 분기 |
| **파이프라인 통합** | LangGraph에 `route_node` 추가, `PipelineState`에 `routing_decision` 필드 추가 |
| **라우팅 메트릭** | `RoutingDecision`의 reason/is_fallback 기반 Prometheus counter |
