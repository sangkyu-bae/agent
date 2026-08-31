# multimodal-extractor Design Document

> **Summary**: PDF에서 그림·차트·이미지형 표·스캔 페이지를 추출하고, 관리자가 선택한 비전 모델(레지스트리 확장형)로 구조화 해석을 생성해 인프로세스 포트로 반환하는 모듈의 상세 설계 — Option C(실용 균형)
>
> **Project**: idt (sangplusbot 백엔드) + idt_front
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-21
> **Status**: Draft (v0.2 — Act-1 구현 동기화)
> **Planning Doc**: [multimodal-extractor.plan.md](../../01-plan/features/multimodal-extractor.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 파이프라인이 문서의 시각 정보(그림·차트·스캔 표)를 버려 RAG 근거에 구멍이 난다 |
| **WHO** | P3 관리자(모델·가드 설정), P2 KB 운영자(미리보기로 품질 확인), 간접 수혜 P1/P4(답변 근거) |
| **RISK** | 비전 호출 비용/지연 폭증 + 벤더별 이미지 입력 형식 차이로 어댑터가 누수 → 상한·필터·동시성 가드를 설정값으로 강제, 포트 계약은 AST 테스트로 고정 |
| **SUCCESS** | 실 PDF 1건에서 OpenAI·Anthropic·로컬(OpenAI 호환) 3종 어댑터 모두 `MultimodalElement[]` 반환(실 LLM 1회 이상), 건별 실패 시 나머지 정상 반환, 미리보기 API로 확인 가능, 회귀 FAILED 목록 diff 0 |
| **SCOPE** | Phase 1: 도메인 계약+PDF 추출기+비전 어댑터 3종+설정 테이블+관리자 API·화면+미리보기 API / Phase 2(후속): 저장 모듈 연동, DOCX·PPTX·단독 이미지 / 확장 포인트만: 엑셀 차트, Gemini |

---

## 1. Overview

### 1.1 Design Goals

1. **추출·해석·반환까지만** 책임지는 독립 모듈. 저장 모듈은 `MultimodalExtractionUseCase.run()`을 주입받아 호출한다 (FR-16).
2. **어댑터 1개 추가 = 파일 1개 + 등록 1줄**: 비전 어댑터는 `provider` 키, 추출기는 확장자 키 레지스트리 (FR-17).
3. **비용·실패 가드가 구조에 내장**: 필터·상한은 순수 Policy, 동시성·타임아웃·재시도는 UseCase, 실패는 건별 `status` (FR-03/04/09).
4. **LLM 출력 신뢰 경계**: LLM이 채우는 `DescriptionDraft`와 서버가 계산하는 `MultimodalElement`를 타입으로 분리 (FR-08).
5. **기존 계약 무변경**: `PDFParserInterface`, Parent/Child 청크 구조, 적재 그래프, `LLMFactory` 시그니처 모두 additive only.

### 1.2 Design Principles

- Thin DDD: domain은 순수 Python(`fitz`·LangChain import 금지), infrastructure가 어댑터, application이 흐름.
- 설정은 소비 지점 단일 출처 — 운영값 전부 `multimodal_setting` 행에서 읽고, `config.py` 신규 키 0개.
- degraded vs 예외: "쓸 수 있는 결과가 존재하는가"가 기준. 건별 실패=degraded, 설정 오류=예외.
- strict structured output 호환: Draft 스키마에 자유 키 dict 금지, 재귀 검사 테스트로 정적 차단.
- 탈착 가능: 그래프 편입(Phase 2)은 팩토리 None 반환=노드 미존재 패턴으로, 본 설계는 이를 막지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 포트 1개, 어댑터 1개(if-분기), 추출은 UseCase 내부 함수 | 포트 6개(분류기·프롬프트·파서 전략·이벤트까지) | 포트 2개 + 레지스트리 2개, BaseVisionAdapter 상속 |
| **New Files** | ~16 | ~40 | ~28 |
| **Modified Files** | ~8 | ~10 | ~9 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (provider 추가마다 if 증가) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 추출기 확장(Office) 시 리팩토링 | 과도한 추상화(CLAUDE.md 금지) | 균형 |
| **Recommendation** | 핫픽스 | 장기 플랫폼 | **기본 선택** |

**Selected**: **Option C** — **Rationale**: 사용자가 요구한 "모델별 확장"은 어댑터 경계만 깨끗하면 충족된다. 분류기·프롬프트 소스 교체 수요는 Phase 1에 없으므로 B의 추가 포트는 YAGNI. A는 Office 추출기·Gemini 추가 시 구조를 다시 짜야 해 Plan의 확장 키 예약(FR-17)과 맞지 않는다. (체크포인트 3에서 사용자 선택)

### 2.1 Component Diagram

```
┌──────────────────────────── interfaces / api ────────────────────────────┐
│ admin_multimodal_router  (GET/PUT settings, POST test)   [admin]         │
│ preview_router           (POST /preview/multimodal)      [user]          │
│ llm_model_router         (+supports_vision 필드)                          │
└────────────┬──────────────────────────────┬──────────────────────────────┘
             │                              │
┌────────────▼──────────────── application ─▼──────────────────────────────┐
│ MultimodalSettingsUseCase   MultimodalExtractionUseCase                  │
│  get / update / test         run(file_bytes, filename, analysis?) ──┐     │
│                               1. ExtractorRegistry[ext].extract()   │     │
│                               2. NoiseFilterPolicy / LimitPolicy    │     │
│                               3. Semaphore(concurrency) ×           │     │
│                                  VisionAdapterRegistry[provider]    │     │
│                                  .describe() with timeout+retry     │     │
│                               4. assemble ExtractionResult          │     │
└──────┬─────────────────────────────┬────────────────────────┬────────────┘
       │ (port)                      │ (port)                 │ (port)
┌──────▼──────── domain/multimodal ──▼────────────────────────▼────────────┐
│ MultimodalSettingRepository  ImageExtractorPort   VisionDescriberPort    │
│ VO: MultimodalSettings, ImageCandidate, MultimodalElement, ChartReading  │
│ Schema(LLM 전용): DescriptionDraft     Policy: NoiseFilter, Limit         │
│ Errors: MultimodalNotConfiguredError, UnsupportedFormatError, ...        │
└──────▲─────────────────────────────▲────────────────────────▲────────────┘
       │                             │                        │
┌──────┴───────── infrastructure/multimodal ──┴────────────────┴───────────┐
│ repository.py (MySQL)   extractors/pdf_pymupdf_extractor.py (fitz)      │
│                         vision/base_vision_adapter.py                   │
│                            ├ LLMFactory.create(llm_model) 재사용         │
│                            ├ 출력 모드 전략: strict → json → text 파싱    │
│                            └ 추상: build_image_block(bytes, mime)        │
│                         vision/openai_vision_adapter.py   (image_url)   │
│                         vision/anthropic_vision_adapter.py(source.b64)  │
│                         vision/openai_compatible_adapter.py(image_url,  │
│                                                      strict 기본 off)   │
│                         prompts.py (유형 4종 × 언어 × 상세도)             │
└─────────────────────────────────────────────────────────────────────────┘
                          ▲ LlmModel (supports_vision) ← llm_model 레지스트리
```

### 2.2 Data Flow

```
[run()]
file_bytes ─► ExtractorRegistry.resolve(ext) ─► ImageCandidate[]
         (page, bbox, bytes, mime, width, height, area_ratio, sha256, hint_type)
   │
   ├─ analysis(AnalysisResult, optional) ─► page_features → page_scan 후보 추가
   │                                       (has_extractable_text=False 페이지만)
   ▼
NoiseFilterPolicy.apply(candidates, settings)   ─► kept[], dropped[](reason)
LimitPolicy.apply(kept, max_images_per_doc)     ─► to_call[], skipped[](reason=limit)
   ▼
for each to_call (Semaphore=concurrency):
   adapter = VisionAdapterRegistry.resolve(llm_model.provider)
   draft = await wait_for(adapter.describe(image, element_type, options), timeout_sec)
           retry 1회 (transient만: timeout·408·429·5xx, backoff 2s)
   element = MultimodalElement.from_draft(candidate, draft, model_id, elapsed_ms, status)
   on failure → element(status=failed, reason)
   ▼
ExtractionResult(elements=[succeeded + failed + skipped], counts, model, timings, dropped[])
   (dropped는 요소 목록에 미포함, 바이트 없는 DroppedCandidate 요약으로 별도 필드 — 미리보기 debug=true 시 노출)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `MultimodalExtractionUseCase` | `ExtractorRegistry`, `VisionAdapterRegistry`, `MultimodalSettingRepository`, `LlmModelRepositoryInterface`, `LoggerInterface` | 흐름 제어, 설정 해석, 모델 해석 |
| `BaseVisionAdapter` | `LLMFactoryInterface`, `LlmModel`, `UsageCallback`(기존) | 클라이언트 생성·토큰 관측 재사용 |
| `PdfPyMuPdfExtractor` | `fitz` | 이미지 객체·표 영역·페이지 렌더 |
| `NoiseFilterPolicy`/`LimitPolicy` | `MultimodalSettings` VO만 | 순수 함수 |
| `admin_multimodal_router` | `require_role("admin")`, `MultimodalSettingsUseCase` | 관리자 API |
| `preview_router` | `get_current_user`, `MultimodalExtractionUseCase` | 미리보기 |
| 프론트 `AdminMultimodalPage` | `useMultimodalSettings`, `useLlmModels`(필터 supports_vision) | 설정 화면 |

---

## 3. Data Model

### 3.1 Entity / Value Object Definition (domain/multimodal)

```python
# value_objects.py — 전부 frozen dataclass, 외부 import 없음
class ElementType(StrEnum):            # wire 계약 — 값 변경 금지
    FIGURE = "figure"; CHART = "chart"; TABLE_IMAGE = "table_image"; PAGE_SCAN = "page_scan"

class ElementStatus(StrEnum):
    SUCCEEDED = "succeeded"; FAILED = "failed"; SKIPPED = "skipped"

@dataclass(frozen=True)
class BBox: x0: float; y0: float; x1: float; y1: float

@dataclass(frozen=True)
class ImageCandidate:
    page: int; bbox: BBox; image_bytes: bytes; mime: str          # "image/png" | "image/jpeg"
    width: int; height: int; area_ratio: float; sha256: str
    hint_type: ElementType                                          # 추출기 휴리스틱(표 영역→TABLE_IMAGE, 전체 렌더→PAGE_SCAN, 그 외 FIGURE)

@dataclass(frozen=True)
class ChartReading:
    chart_type: str | None; x_axis: str | None; y_axis: str | None
    series: tuple[str, ...]; data_points: tuple["DataPoint", ...]; trend: str | None

@dataclass(frozen=True)
class DataPoint: label: str; value: str                            # 수치는 문자열 보존(단위·통화 포함)

@dataclass(frozen=True)
class MultimodalElement:                                            # 서버 계산 필드 + Draft 복사 필드
    element_id: str; page: int; bbox: BBox; element_type: ElementType   # element_type: LLM이 재분류 가능(draft.detected_type) — 단 hint와 다르면 로그
    status: ElementStatus; reason: str | None
    description: str | None; keywords: tuple[str, ...]
    markdown_table: str | None; chart: ChartReading | None; page_text: str | None
    image_bytes: bytes | None; mime: str; width: int; height: int; sha256: str
    model_id: str | None; elapsed_ms: int | None; degraded_output_mode: bool   # strict 폴백 사용 시 True

@dataclass(frozen=True)
class ExtractionResult:
    elements: tuple[MultimodalElement, ...]
    total_candidates: int; dropped_by_filter: int; skipped_by_limit: int
    succeeded: int; failed: int
    vision_model_id: str; provider: str; model_name: str
    timings_ms: tuple[tuple[str, int], ...]                           # ("extract", 812), ("describe", 15430)
    dropped: tuple[DroppedCandidate, ...] = ()                        # v0.2: debug 응답용 필터 제외 요약

@dataclass(frozen=True)
class DroppedCandidate:                                             # v0.2: policies → value_objects 로 이동
    page: int; reason: str; width: int; height: int

@dataclass(frozen=True)
class MultimodalSettings:                                           # __post_init__ 범위 검증
    id: str; enabled: bool; vision_model_id: str | None
    max_images_per_doc: int        # 1..500, 기본 50
    min_image_px: int              # 0..4096, 기본 100  (가로·세로 모두 이상)
    min_area_ratio: float          # 0.0..1.0, 기본 0.02
    concurrency: int               # 1..16, 기본 4
    timeout_sec: int               # 5..600, 기본 60
    output_language: str           # "ko" | "en"
    detail_level: str              # "brief" | "detailed"
    updated_at: datetime

# schemas.py — LLM 출력 전용 (pydantic, strict 호환: dict/Any 금지, 전 필드 명시)
class DraftDataPoint(BaseModel): label: str; value: str
class DraftChart(BaseModel):
    chart_type: str | None; x_axis: str | None; y_axis: str | None
    series: list[str]; data_points: list[DraftDataPoint]; trend: str | None
class DescriptionDraft(BaseModel):
    detected_type: Literal["figure","chart","table_image","page_scan"]
    description: str
    keywords: list[str]
    markdown_table: str | None
    chart: DraftChart | None
    page_text: str | None
# 금지 필드(테스트로 고정): status, elapsed_ms, model_id, page, bbox, sha256, degraded_*
```

**타입 분리 테스트(FR-08)**: `set(DescriptionDraft.model_fields) ∩ SERVER_COMPUTED_FIELDS == ∅`, 그리고 `MultimodalElement` 필드 집합 == Draft 복사 필드 ∪ 서버 필드 (동등 비교).

### 3.2 Entity Relationships

```
[llm_model] 1 ◄── soft ref (vision_model_id, FK 없음) ── 1 [multimodal_setting]  (단일 행)
[llm_model].supports_vision = 1 인 행만 선택 후보

ExtractionResult 1 ── N MultimodalElement   (메모리 전용 — 본 모듈은 저장하지 않음)
```

### 3.3 Database Schema

```sql
-- V064__add_supports_vision_to_llm_model.sql
-- multimodal-extractor Design §3.3: 비전(이미지 입력) 지원 여부. 비전 모델 선택 드롭다운은
-- is_active=1 AND supports_vision=1 만 노출. additive(기본 0)라 기존 CRUD·시드 무변경.
-- ⚠️ COMMENT 안에 콤마 금지 (tests/db/test_migration_ddl_comments.py)
ALTER TABLE llm_model
  ADD COLUMN supports_vision TINYINT(1) NOT NULL DEFAULT 0
  COMMENT '이미지 입력(비전) 지원 여부 — 1이면 멀티모달 추출 모델로 선택 가능'
  AFTER base_url;

UPDATE llm_model SET supports_vision = 1
 WHERE provider = 'openai'    AND model_name IN ('gpt-4o', 'gpt-4o-mini')
    OR provider = 'anthropic' AND model_name LIKE 'claude-%';

-- V065__create_multimodal_setting.sql
-- 전역 단일 행(id 고정). vision_model_id 는 llm_model.id 소프트 참조(FK 없음 — chunking_profile.summary_llm_model_id 선례).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피, V037 선례). 열거값은 VARCHAR(애플리케이션 검증).
CREATE TABLE multimodal_setting (
    id                 VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    enabled            TINYINT(1)   NOT NULL DEFAULT 0    COMMENT '멀티모달 추출 활성 여부',
    vision_model_id    VARCHAR(36)  NULL                  COMMENT 'llm_model.id 소프트 참조 — NULL이면 미설정',
    max_images_per_doc INT          NOT NULL DEFAULT 50   COMMENT '문서당 비전 호출 상한 — 초과분은 skipped',
    min_image_px       INT          NOT NULL DEFAULT 100  COMMENT '가로·세로 최소 픽셀 — 미만은 필터 제외',
    min_area_ratio     DECIMAL(5,4) NOT NULL DEFAULT 0.0200 COMMENT '페이지 면적 대비 최소 비율 — 미만은 필터 제외',
    concurrency        INT          NOT NULL DEFAULT 4    COMMENT '동시 비전 호출 수',
    timeout_sec        INT          NOT NULL DEFAULT 60   COMMENT '건당 비전 호출 타임아웃(초)',
    output_language    VARCHAR(8)   NOT NULL DEFAULT 'ko' COMMENT '설명 출력 언어 ko 또는 en',
    detail_level       VARCHAR(16)  NOT NULL DEFAULT 'detailed' COMMENT '설명 상세도 brief 또는 detailed',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='멀티모달 추출 전역 설정 — 단일 행';

INSERT INTO multimodal_setting (id) VALUES ('b0000000-0000-4000-8000-000000000001');
```

ORM: `src/infrastructure/multimodal/models.py` `MultimodalSettingModel` (모든 컬럼 `comment=` 동일 반영), `LlmModelModel`에 `supports_vision = Column(Boolean, nullable=False, default=False, comment=...)` 추가.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/multimodal/settings` | 전역 설정 조회(+선택 모델 요약) | admin |
| PUT | `/api/v1/admin/multimodal/settings` | 전체 교체(관리자 화면 PUT 관례) | admin |
| POST | `/api/v1/admin/multimodal/test` | 선택 모델로 1장 해석(연결 확인) | admin |
| POST | `/api/v1/preview/multimodal` | PDF → ExtractionResult 미리보기(썸네일) | user |
| GET/POST/PATCH | `/api/v1/llm-models…` | 기존 + `supports_vision` optional 필드 | 기존 유지 |

### 4.2 Detailed Specification

#### `GET /api/v1/admin/multimodal/settings` → 200

```json
{
  "id": "b0000000-0000-4000-8000-000000000001",
  "enabled": true,
  "vision_model_id": "…uuid…",
  "vision_model": { "id": "…", "provider": "openai", "model_name": "gpt-4o", "display_name": "GPT-4o", "is_active": true, "supports_vision": true },
  "max_images_per_doc": 50, "min_image_px": 100, "min_area_ratio": 0.02,
  "concurrency": 4, "timeout_sec": 60,
  "output_language": "ko", "detail_level": "detailed",
  "updated_at": "2026-08-21T09:00:00Z"
}
```
`vision_model`은 소프트 참조 해석 결과(모델 삭제/비활성 시 `null` + `warnings: ["selected model inactive"]`).

#### `PUT /api/v1/admin/multimodal/settings`

Request: 위 응답에서 `id`, `vision_model`, `updated_at` 제외한 전 필드 필수.
검증: pydantic 범위(§3.1 VO와 동일 숫자) → UseCase가 `vision_model_id` 존재·`is_active`·`supports_vision` 확인(`chunking_profile._validate_summary_model` 선례).
Response 200: GET과 동일. Errors: 400 `VALIDATION_ERROR`, 404 `VISION_MODEL_NOT_FOUND`, 409 `VISION_MODEL_NOT_CAPABLE`(supports_vision=0 또는 비활성).

#### `POST /api/v1/admin/multimodal/test` (multipart, 선택 `image` ≤ 5MB; 없으면 내장 샘플 차트 PNG)

Response 200:
```json
{ "ok": true, "provider": "openai", "model_name": "gpt-4o", "elapsed_ms": 2140,
  "degraded_output_mode": false,
  "draft": { "detected_type": "chart", "description": "…", "keywords": ["…"], "chart": {…}, "markdown_table": null, "page_text": null } }
```
응답에는 `error: string | null` 이 포함된다. **호출 실패는 예외가 아니라 결과**: 200 `{ ok: false, error: "RuntimeError: …", draft: null }` (v0.2 — 연결 테스트는 "실패도 정보"이므로 502 대신 결과로 돌려 화면이 동일 카드로 렌더).
Errors: 409 `MULTIMODAL_NOT_CONFIGURED`(모델 미선택/비활성/키 없음), 415 `UNSUPPORTED_MEDIA`(png/jpeg/webp 외), 413 `PAYLOAD_TOO_LARGE`(5MB 초과), 500 `UNSUPPORTED_VISION_PROVIDER`.

#### `POST /api/v1/preview/multimodal` (multipart `file`=PDF ≤ 30MB, query `debug: bool=false`)

Response 200 (`ExtractionResult` 직렬화 — `image_bytes`는 제외하고 `thumbnail_b64`(긴 변 ≤ 256px PNG)로 대체):
```json
{
  "vision_model_id": "…", "provider": "openai", "model_name": "gpt-4o",
  "total_candidates": 23, "dropped_by_filter": 9, "skipped_by_limit": 0, "succeeded": 13, "failed": 1,
  "timings_ms": { "extract": 812, "describe": 15430 },
  "elements": [
    { "element_id": "…", "page": 12, "bbox": {"x0":72,"y0":100,"x1":520,"y1":390},
      "element_type": "chart", "status": "succeeded", "reason": null,
      "description": "2024년 분기별 여신 한도 추이…", "keywords": ["여신 한도","분기"],
      "chart": { "chart_type": "bar", "x_axis": "분기", "y_axis": "억원", "series": ["한도"],
                 "data_points": [{"label":"1Q","value":"120"}], "trend": "증가" },
      "markdown_table": null, "page_text": null,
      "mime": "image/png", "width": 896, "height": 580, "sha256": "…",
      "model_id": "…", "elapsed_ms": 1980, "degraded_output_mode": false,
      "thumbnail_b64": "iVBOR…" },
    { "element_id": "…", "page": 3, "element_type": "figure", "status": "failed", "reason": "timeout after 60s (1 retry)", "thumbnail_b64": "…", "…": "null 필드들" },
    { "element_id": "…", "page": 40, "element_type": "figure", "status": "skipped", "reason": "limit:max_images_per_doc=50", "thumbnail_b64": "…" }
  ],
  "dropped": [ { "page": 1, "reason": "min_image_px", "width": 48, "height": 48 } ]   // debug=true 일 때만
}
```
Errors: 409 `MULTIMODAL_NOT_CONFIGURED` / `MULTIMODAL_DISABLED`, 415 `UNSUPPORTED_FORMAT`(확장자 미등록), 413 크기 초과.

#### 인프로세스 포트 (저장 모듈용, FR-16)

```python
class MultimodalExtractionUseCase:
    async def run(self, file_bytes: bytes, filename: str, request_id: str,
                  analysis: AnalysisResult | None = None) -> ExtractionResult: ...
    # raises: MultimodalDisabledError, MultimodalNotConfiguredError, UnsupportedFormatError
    # never raises on per-image vision failure
```
`enabled=False`이면 `MultimodalDisabledError` — 저장 모듈은 이를 잡아 "노드 미존재"로 취급(탈착형 이음매).

---

## 5. UI/UX Design

### 5.1 Screen Layout — `/admin/multimodal` (docs-quality 그룹, 2차 탭은 레이아웃 소유)

```
┌ 멀티모달 추출 ─────────────────────────────────────────────┐
│ [설정]  [미리보기]                                  (탭)  │
├───────────────────────────────────────────────────────────┤
│ 설정 탭                                                    │
│  활성화 [toggle]                                           │
│  비전 모델 [select: supports_vision && is_active 모델]     │
│     ↳ 선택 모델이 비활성/삭제됨 경고 배너 (warnings)        │
│  ── 비용 가드 ──                                            │
│  문서당 최대 이미지 [number 1..500]  최소 픽셀 [0..4096]     │
│  최소 면적 비율 [0..1 step .005]  동시 호출 [1..16]  타임아웃(초) [5..600] │
│  ── 출력 ──                                                 │
│  언어 (ko|en) [radio]   상세도 (brief|detailed) [radio]      │
│  [연결 테스트 (LoadingButton)] → 결과 카드(모델·지연·설명 요약·degraded 배지) │
│  [저장 (LoadingButton, dirty일 때만 활성)]                   │
├───────────────────────────────────────────────────────────┤
│ 미리보기 탭                                                 │
│  PDF 드롭존 [file]  [debug 토글]  [실행 (LoadingButton)]    │
│  요약 바: 후보 N · 필터 제외 N · 상한 skip N · 성공 N · 실패 N · 모델 · 소요 │
│  요소 카드 그리드: 썸네일 | p.N | 유형 배지 | 상태 배지 | 설명 | (chart 표/표 마크다운 접기) | 실패 사유 │
└───────────────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
/admin/llm-models 에서 모델 등록(supports_vision 체크)
 → /admin/multimodal 설정 탭: 모델 선택·가드 입력 → 연결 테스트 → 저장
 → 미리보기 탭: 샘플 PDF 업로드 → 요소 카드 확인 → 필요 시 가드 조정 후 재실행
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminMultimodalPage` | `idt_front/src/pages/AdminMultimodalPage/index.tsx` | 탭 컨테이너 |
| `MultimodalSettingsForm` | `pages/AdminMultimodalPage/MultimodalSettingsForm.tsx` | 설정 폼·검증·저장·연결 테스트 |
| `MultimodalPreviewPanel` | `pages/AdminMultimodalPage/MultimodalPreviewPanel.tsx` | 업로드·실행·요약 바·카드 그리드 |
| `MultimodalElementCard` | `pages/AdminMultimodalPage/MultimodalElementCard.tsx` | 요소 1건 표시 |
| 타입 | `src/types/multimodal.ts` (+ `ELEMENT_TYPES`, `ELEMENT_STATUSES` as const 여기) | wire 계약 |
| 서비스 | `src/services/multimodalService.ts` | 4 엔드포인트 |
| 훅 | `src/hooks/useMultimodalSettings.ts`, `useMultimodalPreview.ts` | TanStack Query/Mutation |
| 상수 | `src/constants/api.ts`(+3: settings/test/preview), `src/constants/adminNav.ts`(+1 item, docs-quality) | 단일 소스 |
| 검증 유틸 | `src/utils/multimodalValidators.ts` (v0.2 — 컴포넌트 파일 런타임 export 금지 규칙) | 숫자 범위 검증 |
| 기존 수정 | `pages/AdminLlmModelsPage/index.tsx`, `types/llmModel.ts` | `supports_vision` 체크박스·배지 |

### 5.4 Page UI Checklist

#### `/admin/multimodal` 설정 탭
- [ ] Toggle: 활성화(`enabled`)
- [ ] Select: 비전 모델 — 옵션은 `is_active && supports_vision` 모델만, 라벨 `display_name (provider/model_name)`, 빈 상태 안내 "비전 지원 모델을 먼저 등록하세요" + `/admin/llm-models` 링크
- [ ] Banner: 선택 모델 비활성/삭제 경고(`warnings` 존재 시)
- [ ] Number: 문서당 최대 이미지(1..500), 최소 픽셀(0..4096), 동시 호출(1..16), 타임아웃 초(5..600)
- [ ] Number(step 0.005): 최소 면적 비율(0..1)
- [ ] Radio: 언어 `ko|en`, 상세도 `brief|detailed`
- [ ] LoadingButton: 연결 테스트(isPending), 결과 카드(provider·model_name·elapsed_ms·description 첫 200자·`degraded_output_mode` 배지·실패 시 오류 코드)
- [ ] LoadingButton: 저장(dirty 아닐 때 disabled, isPending), 성공 토스트, 409/404 오류 메시지 표시
- [ ] 인라인 검증 메시지: 범위 밖 입력 시 저장 비활성

#### `/admin/multimodal` 미리보기 탭
- [ ] File input/드롭존: `.pdf`만, 30MB 초과 시 클라이언트 차단 메시지
- [ ] Toggle: debug(필터 제외 목록 포함)
- [ ] LoadingButton: 실행(isPending + 진행 안내 "비전 호출 중…")
- [ ] Summary bar: total_candidates / dropped_by_filter / skipped_by_limit / succeeded / failed / model / timings
- [ ] Card grid: 썸네일(img, alt=유형), `p.{page}`, 유형 배지 4종 색상, 상태 배지 3종, description, keywords 칩
- [ ] Card(chart): data_points 표(label/value) + trend, Card(table_image): markdown_table 코드블록 접기, Card(page_scan): page_text 접기
- [ ] Card(failed/skipped): reason 텍스트
- [ ] debug 섹션: dropped 목록 테이블(page/reason/width/height)
- [ ] 409 MULTIMODAL_NOT_CONFIGURED 시 "설정 탭에서 모델을 먼저 선택" 안내

#### `/admin/llm-models` (기존 페이지 추가분)
- [ ] Checkbox: 생성/수정 폼 `supports_vision`
- [ ] Badge: 목록 행 "Vision" 배지(`supports_vision=true`)

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Cause | Handling |
|------|------|-------|----------|
| `MULTIMODAL_DISABLED` | 409 | `enabled=false` | 미리보기: 안내. 인프로세스: `MultimodalDisabledError` → 호출자가 스킵 |
| `MULTIMODAL_NOT_CONFIGURED` | 409 | `vision_model_id` NULL / 모델 없음 / 비활성 / supports_vision=0 / API 키 env 없음 | 예외 전파(FR-10). 설정 탭 유도 |
| `VISION_MODEL_NOT_FOUND` | 404 | PUT에 존재하지 않는 id | 폼 오류 |
| `VISION_MODEL_NOT_CAPABLE` | 409 | PUT에 비활성/비전 미지원 모델 | 폼 오류 |
| `UNSUPPORTED_FORMAT` | 415 | 확장자 미등록(`UnsupportedFormatError`) **또는 손상 PDF(`ExtractionError`, fitz.open 실패)** | 메시지에 지원 목록 |
| `UNSUPPORTED_VISION_PROVIDER` | 500 | 등록되지 않은 provider(설정 데이터 불일치) | 스택 로그 + 관리자 안내 |
| (연결 테스트) `ok=false` | 200 | 비전 호출 1회 실패 — 결과로 반환(v0.2, 502 `VISION_CALL_FAILED` 폐기) | 결과 카드에 error 표시 |
| `UNSUPPORTED_MEDIA` | 415 | 연결 테스트 이미지 MIME 미지원 | 메시지 |
| `PAYLOAD_TOO_LARGE` | 413 | preview 30MB / test 5MB 초과 | 메시지 |
| `VALIDATION_ERROR` | 400 | 범위 밖 값 | fieldErrors |
| (건별) `status=failed` | 200 | timeout / 429 재시도 소진 / 스키마 파싱 실패 / provider 4xx | 결과 요소에 reason, 전체는 성공 |

### 6.2 Error Response Format

기존 프로젝트 공통 형식 유지: `{"detail": {"code": "...", "message": "...", "details": {...}}}` (기존 라우터 관례 확인 후 동일 적용 — Do 단계에서 `chunking_profile_router`의 오류 응답과 맞춘다).

### 6.3 degraded / 예외 경계 표 (위키 degradation-vs-failure-boundary)

| 상황 | 판정 | 근거 |
|------|------|------|
| 이미지 1건 타임아웃·429·파싱 실패 | degraded(건별 failed) | 나머지 결과는 쓸 수 있다 |
| strict 미지원 → json/text 폴백 성공 | succeeded + `degraded_output_mode=true` | 결과는 있으나 품질 표기 |
| 모델 미설정·비활성·API 키 없음 | 예외 | 쓸 수 있는 결과가 0건이 될 설정 오류 — 숨기면 "결과 0건" 지속 |
| PDF 파싱 불가(손상) | 예외 `UnsupportedFormatError`/`ExtractionError` | 입력 자체 무효 |
| 상한 초과 | skipped(결과 포함) | 조용한 절단 금지 |

---

## 7. Security Considerations

- [ ] 관리자 API 전부 `require_role("admin")`; 미리보기는 `get_current_user`
- [ ] API 키는 `llm_model.api_key_env` 간접 참조만, 응답·로그 미노출
- [ ] 이미지 바이트·base64는 로그 금지(길이만 기록), 미리보기 응답은 썸네일만
- [ ] 업로드 크기 제한(PDF 30MB, 테스트 이미지 5MB), MIME 스니핑(`fitz.open` 실패 시 415)
- [ ] 프롬프트 인젝션: 이미지 내 텍스트를 명령으로 따르지 않도록 시스템 프롬프트 고정 문구 + Draft 스키마 강제(자유 텍스트는 `description`만)
- [ ] 로컬 모델 `base_url`은 기존 LLM 레지스트리 정책 그대로(신규 노출 없음)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | VO 검증, NoiseFilterPolicy, LimitPolicy, Draft/Element 필드 분리, strict 스키마 재귀 검사 | pytest | Do |
| Unit (infra) | PdfPyMuPdfExtractor(합성 PDF), 어댑터 3종(fake LLM + 메시지 포맷 단언), 출력 모드 폴백 | pytest | Do |
| Unit (app) | UseCase 동시성·타임아웃·재시도·건별 degraded·설정 오류 예외 | pytest + fake 어댑터 | Do |
| Contract (AST) | domain 외부 import 0, UseCase→Protocol 미선언 메서드 호출 0, Draft 금지 필드 0 | pytest(ast) | Do |
| L1 API | 4 엔드포인트 상태·스키마·권한 | pytest TestClient | Do |
| DB | V064/V065 COMMENT 검사 | 기존 `test_migration_ddl_comments.py` | Do |
| Smoke (실 LLM) | 어댑터 3종 × 샘플 이미지 1장 (`RUN_LLM_SMOKE=1`일 때만) | pytest marker | Do(DoD) |
| L2 UI | 설정 폼·미리보기 패널 | Vitest + RTL + MSW | Do |
| Frontend | `adminNav.test.ts`, 서비스·훅 테스트 | Vitest | Do |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test | Status | Response |
|---|----------|--------|------|:-:|----------|
| 1 | /admin/multimodal/settings | GET | 관리자 조회 | 200 | 전 필드 + `vision_model` 해석 |
| 2 | /admin/multimodal/settings | GET | 일반 사용자 | 403 | — |
| 3 | /admin/multimodal/settings | GET | 미인증 | 401 | — |
| 4 | /admin/multimodal/settings | PUT | 유효 전체 교체 | 200 | 저장값 반영, `updated_at` 갱신 |
| 5 | /admin/multimodal/settings | PUT | `concurrency=0` | 400 | VALIDATION_ERROR |
| 6 | /admin/multimodal/settings | PUT | supports_vision=0 모델 | 409 | VISION_MODEL_NOT_CAPABLE |
| 7 | /admin/multimodal/settings | PUT | 없는 모델 id | 404 | VISION_MODEL_NOT_FOUND |
| 8 | /admin/multimodal/test | POST | fake 어댑터 성공 | 200 | `ok=true`, draft 존재 |
| 9 | /admin/multimodal/test | POST | 모델 미선택 | 409 | MULTIMODAL_NOT_CONFIGURED |
| 10 | /preview/multimodal | POST | 합성 PDF(그림 1·표 1·48px 아이콘 2) + 실 추출기 + fake 어댑터 | 200 | succeeded=2, dropped_by_filter=2, thumbnail_b64 존재, image_bytes 키 없음 (`test_preview_multimodal_integration.py`) |
| 11 | /preview/multimodal | POST | fake 어댑터 1건 타임아웃 | 200 | failed=1, 나머지 succeeded |
| 12 | /preview/multimodal | POST | `.docx` | 415 | UNSUPPORTED_FORMAT |
| 13 | /preview/multimodal | POST | enabled=false | 409 | MULTIMODAL_DISABLED |
| 14 | /llm-models | POST/GET | `supports_vision` 생략 → false, 지정 → 반영 | 201/200 | 필드 존재 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected | Verification |
|---|------|--------|----------|--------------|
| 1 | /admin/multimodal | 로드 | §5.4 설정 요소 전부 표시, 모델 select에 vision 모델만 | MSW 데이터 렌더 |
| 2 | 설정 탭 | 범위 밖 입력 | 인라인 오류 + 저장 disabled | — |
| 3 | 설정 탭 | 저장 클릭 | PUT 호출 1회, 토스트 | 이중 클릭 시 isPending으로 1회만(버튼 disabled 검증이 아니라 호출 횟수 단언) |
| 4 | 설정 탭 | 연결 테스트 | POST /test 호출, 결과 카드 | degraded 배지 조건부 |
| 5 | 미리보기 탭 | PDF 업로드·실행 | 요약 바·카드 그리드 | 상태 배지 3종 렌더 |
| 6 | 미리보기 탭 | 409 응답 | 설정 탭 유도 메시지 | — |
| 7 | /admin/llm-models | 생성 폼 체크박스 | 요청 바디에 `supports_vision` | MSW 캡처 |
| 8 | 사이드바 | 문서·품질 그룹 | "멀티모달 추출" 항목 존재 | `adminNav.test.ts` 관계 기반 단언 |

### 8.4 L3: E2E Scenario

| # | Scenario | Steps | Success |
|---|----------|-------|---------|
| 1 | 관리자 설정→미리보기 | 모델 등록(vision 체크) → 설정 저장 → 연결 테스트 → 샘플 PDF 미리보기 | 요소 카드 ≥1 succeeded (실 서버·실 LLM 필요 — E2E 이월 체크리스트에 등재) |

### 8.5 Seed / Fixture Requirements

| Entity | Count | Fields |
|--------|:-:|--------|
| `llm_model` | ≥2 | 1건 `supports_vision=1, is_active=1` / 1건 `supports_vision=0` |
| `multimodal_setting` | 1 | V065 시드 행 |
| 합성 PDF fixture | 1 | `tests/fixtures/multimodal/sample.pdf` — 페이지1: 큰 그림 1 + 48px 아이콘 2(동일 바이트 → 해시 중복), 페이지2: 표 영역 1, 페이지3: 텍스트 없는 스캔형 |
| 샘플 차트 PNG | 1 | `src/infrastructure/multimodal/assets/sample_chart.png` (연결 테스트 기본 이미지) |

---

## 9. Clean Architecture

### 9.1 Layer Structure / 9.2 Dependency Rules

기존 Thin DDD 규칙(`idt/CLAUDE.md §2`) 그대로. domain → infrastructure 참조 금지, router에 비즈니스 로직 금지, Repository 내부 commit 금지, 세션은 UseCase 단위 단일.

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/multimodal` | stdlib, pydantic(schemas.py만) | fitz, langchain, sqlalchemy, infrastructure, application |
| `application/multimodal` | domain, `src.domain.pdf_analyzer.schemas`(AnalysisResult), `src.domain.llm_model` | fitz, langchain 구체 클래스, sqlalchemy |
| `infrastructure/multimodal` | domain, `src.infrastructure.llm.llm_factory`, fitz, langchain | application, api |
| `api/routes` | application(UseCase), interfaces/schemas | infrastructure 직접(DI는 main.py 경유) |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| VO·Schema·Port·Policy·Errors | Domain | `src/domain/multimodal/{value_objects,schemas,interfaces,policies,errors}.py` |
| `MultimodalExtractionUseCase`, `MultimodalSettingsUseCase`, `ExtractorRegistry`, `VisionAdapterRegistry` | Application | `src/application/multimodal/{use_case,settings_use_case,registries}.py` |
| `PdfPyMuPdfExtractor` | Infrastructure | `src/infrastructure/multimodal/extractors/pdf_pymupdf_extractor.py` |
| `BaseVisionAdapter` + 3 어댑터 | Infrastructure | `src/infrastructure/multimodal/vision/` |
| 프롬프트 4종 | Infrastructure | `src/infrastructure/multimodal/prompts.py` |
| ORM·Repository | Infrastructure | `src/infrastructure/multimodal/{models,repository}.py` |
| 요청/응답 스키마 | Interfaces | `src/interfaces/schemas/multimodal.py` |
| 라우터 | Interfaces/API | `src/api/routes/admin_multimodal_router.py`, `preview_router.py`(+1) |
| DI | API | `src/api/multimodal_di.py` (v0.2 — main.py 비대화 방지로 분리, main.py는 `wire_multimodal()` 1회 호출): `get_multimodal_extraction_use_case`, `get_multimodal_settings_use_case`, **`get_multimodal_thumbnailer`**(§9.3 routes→infrastructure 금지를 지키기 위한 DI seam), 레지스트리 앱 수명 싱글턴 |

### 9.5 핵심 내부 계약

```python
# domain/multimodal/interfaces.py
class ImageExtractorPort(Protocol):
    supported_extensions: frozenset[str]                       # {"pdf"}
    def extract(self, file_bytes: bytes, filename: str,
                analysis: "AnalysisResult | None") -> list[ImageCandidate]: ...

class VisionDescriberPort(Protocol):
    provider: str                                              # LlmModel.provider 와 동일 문자열
    async def describe(self, image: ImageCandidate, element_type: ElementType,
                       options: DescribeOptions) -> DescribeOutcome: ...   # DescribeOutcome(draft, degraded_output_mode, usage)

class MultimodalSettingRepository(Protocol):
    async def get(self, request_id: str) -> MultimodalSettings: ...
    async def update(self, settings: MultimodalSettings, request_id: str) -> MultimodalSettings: ...

# infrastructure/multimodal/vision/base_vision_adapter.py
class BaseVisionAdapter(VisionDescriberPort):
    output_modes: tuple[str, ...] = ("strict", "json", "text")     # 서브클래스가 재정의
    def __init__(self, llm_factory: LLMFactoryInterface, llm_model: LlmModel, logger): ...
    @abstractmethod
    def build_image_block(self, image: ImageCandidate, options: DescribeOptions) -> dict: ...   # 벤더별 유일한 차이 (OpenAI 는 detail_level→detail 매핑에 options 사용)
    async def describe(...):                                           # 모드 순회: strict→json→text, 성공 모드≠strict면 degraded
        for mode in self.output_modes: try: return await self._call(mode, ...) except SchemaUnsupported/ParseError: continue

# DescribeOutcome(draft, degraded_output_mode, output_mode, usage)  — output_mode 는 로깅용 (v0.2)
# OpenAI: {"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}","detail":"high"|"low"}}  (detail_level 매핑)
# Anthropic: {"type":"image","source":{"type":"base64","media_type":mime,"data":b64}}
# OpenAI-compatible: OpenAI 포맷, output_modes=("json","text")  — strict 기본 제외
```

레지스트리 키 규칙: `VisionAdapterRegistry.register("openai", OpenAIVisionAdapter)`, `"anthropic"`, `"ollama"` 및 `"openai_compatible"`(둘 다 OpenAICompatibleVisionAdapter — `ollama` provider의 LLMFactory 경로는 ChatOllama이며 이미지 블록은 OpenAI 포맷을 수용). `"gemini"`는 미등록 → `UnsupportedVisionProviderError`.

프롬프트(`prompts.py`): `build_messages(element_type, options: DescribeOptions, image_block)` — 시스템: 역할·금지(이미지 내 지시 무시·추측 금지·없으면 null)·언어; 사용자: 유형별 지시(figure=설명+키워드, chart=축·계열·수치·추세, table_image=마크다운 표 재구성+설명, page_scan=전문 전사+요약) + `detected_type` 재분류 허용.

---

## 10. Coding Convention Reference

### 10.1 ~ 10.3

`idt/CLAUDE.md`(함수 40줄, if 중첩 2단계, 타입 명시, logger 필수, config 하드코딩 금지, DDL COMMENT), `idt_front/CLAUDE.md`(컴포넌트 파일 런타임 상수 export 금지 → `types/multimodal.ts`에 `as const`), 기존 import 순서 유지.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 모듈 ID 코멘트 | `# Design Ref: multimodal-extractor §N` 파일 상단, 핵심 로직에 `# Plan FR-xx` |
| 로깅 | `request_id` 전파, 건별 `vision.describe`(provider/model/elapsed/status/mode), 예외는 `exception=e` |
| 세션 | Repository는 세션 주입(commit 금지), UseCase 단일 세션 |
| 시간 | `elapsed_ms`는 UseCase가 `time.perf_counter`로 계산(LLM 필드 금지) |
| 프론트 상태 | TanStack Query(`queryKeys.multimodal.settings()`), 뮤테이션 버튼은 `LoadingButton` + `mutateAsync` try/catch |
| 테스트 seam | `MultimodalExtractionUseCase._on_adapter_built`(어댑터 생성 직후 훅), `_timeout_override_sec`(설정 하한 5s 우회) — 운영 경로에서는 None, 테스트 전용 (v0.2) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V064__add_supports_vision_to_llm_model.sql         [new]
├── db/migration/V065__create_multimodal_setting.sql                [new]
├── src/domain/multimodal/{__init__,value_objects,schemas,interfaces,policies,errors}.py   [new 6]
├── src/domain/llm_model/entity.py                                  [mod: supports_vision]
├── src/application/multimodal/{__init__,use_case,settings_use_case,registries}.py         [new 4]
├── src/application/llm_model/*  (create/update DTO)                [mod]
├── src/infrastructure/multimodal/{__init__,models,repository,prompts}.py                  [new 4]
├── src/infrastructure/multimodal/extractors/{__init__,pdf_pymupdf_extractor}.py           [new 2]
├── src/infrastructure/multimodal/vision/{__init__,base_vision_adapter,openai_vision_adapter,anthropic_vision_adapter,openai_compatible_vision_adapter}.py  [new 5]
├── src/infrastructure/multimodal/assets/sample_chart.png           [new]
├── src/infrastructure/llm_model/{models,llm_model_repository,seed}.py                     [mod 3]
├── src/interfaces/schemas/multimodal.py                            [new]
├── src/interfaces/schemas/llm_model.py (또는 기존 위치)              [mod: supports_vision]
├── src/api/routes/admin_multimodal_router.py                       [new]
├── src/api/routes/preview_router.py                                [mod: +1 route]
├── src/api/main.py                                                 [mod: DI + router include(와일드카드보다 선등록)]
├── tests/domain/multimodal/*, tests/application/multimodal/*, tests/infrastructure/multimodal/*, tests/api/test_admin_multimodal_router.py, tests/fixtures/multimodal/sample.pdf
idt_front/
├── src/types/multimodal.ts, src/services/multimodalService.ts, src/hooks/{useMultimodalSettings,useMultimodalPreview}.ts   [new]
├── src/pages/AdminMultimodalPage/{index,MultimodalSettingsForm,MultimodalPreviewPanel,MultimodalElementCard}.tsx + tests  [new]
├── src/constants/{api,adminNav}.ts, src/types/llmModel.ts, src/pages/AdminLlmModelsPage/index.tsx, src/mocks/handlers(+)    [mod]
```

### 11.2 Implementation Order (TDD: 각 항목 테스트 → 실패 → 구현 → 통과)

1. [ ] V064/V065 + ORM + COMMENT 테스트 통과
2. [ ] domain: VO·errors → Draft 스키마(strict 재귀 검사·금지 필드 테스트) → Policies
3. [ ] infra: Repository(설정) → PdfPyMuPdfExtractor(합성 PDF fixture)
4. [ ] infra: BaseVisionAdapter(출력 모드 폴백, fake LLM) → 3 어댑터(이미지 블록 포맷 단언)
5. [ ] application: registries → SettingsUseCase(검증 409/404) → ExtractionUseCase(동시성·타임아웃·재시도·degraded)
6. [ ] llm_model `supports_vision` 관통(엔티티·DTO·ORM·repo·seed·router 스키마)
7. [ ] API: admin_multimodal_router + preview route + main.py DI + L1 테스트
8. [ ] AST 계약 테스트 3종
9. [ ] 프론트: types/constants/service/hooks(+MSW) → AdminLlmModelsPage 필드 → AdminMultimodalPage 3 컴포넌트 → adminNav
10. [ ] 실 LLM 스모크 3종(`RUN_LLM_SMOKE=1`) 기록, `/verify-architecture` `/verify-logging` `/verify-tdd`, 회귀 FAILED diff

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Est. Turns |
|--------|-----------|-------------|:-:|
| 스키마·도메인 | `module-1` | V064/V065, ORM, domain VO·Draft·Policy·errors + 테스트 (순서 1~2) | 25-30 |
| 추출기·설정 저장소 | `module-2` | PdfPyMuPdfExtractor, 합성 PDF fixture, 설정 Repository (순서 3) | 20-25 |
| 비전 어댑터 | `module-3` | BaseVisionAdapter + OpenAI/Anthropic/OpenAI-compatible, prompts, 샘플 PNG (순서 4) | 30-35 |
| 유스케이스·레지스트리 | `module-4` | registries, SettingsUseCase, ExtractionUseCase, AST 계약 테스트 (순서 5, 8) | 30-35 |
| API·DI·llm_model 관통 | `module-5` | supports_vision 관통, admin 라우터, preview route, main.py, L1 (순서 6~7) | 30-35 |
| 프론트엔드 | `module-6` | 타입·서비스·훅·MSW, LlmModels 필드, AdminMultimodalPage, adminNav (순서 9) | 40-50 |
| 검증·스모크 | `module-7` | 실 LLM 스모크 3종, verify 스킬 3종, 회귀 diff (순서 10) | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-:|
| 1 | Plan + Design | 전체 (완료) | — |
| 2 | Do | `--scope module-1,module-2` | 45-55 |
| 3 | Do | `--scope module-3,module-4` | 60-70 |
| 4 | Do | `--scope module-5` | 30-35 |
| 5 | Do | `--scope module-6` | 40-50 |
| 6 | Do + Check | `--scope module-7` → `/pdca analyze` | 40-50 |

### 11.4 FR 역추적 표 (위키 intermediate-artifact-verification)

| FR | Design 섹션 | 검증 테스트 |
|----|-------------|-------------|
| FR-01 | §3.1 ImageCandidate, §9.4 extractor | extractor 단위(합성 PDF) |
| FR-02 | §2.2 page_scan 후보, §9.5 extract(analysis) | extractor 단위(텍스트 없는 페이지) |
| FR-03 | §3.1 NoiseFilterPolicy | policy 단위(px/면적/해시) |
| FR-04 | §3.1 LimitPolicy, §6.3 | policy 단위 + L1 #10 |
| FR-05 | §9.5 VisionDescriberPort, 어댑터 3종 | 어댑터 포맷 단언 + 스모크 |
| FR-06 | §9.5 prompts | prompts 단위(언어·상세도 치환) |
| FR-07 | §3.1 DescriptionDraft/ChartReading | strict 재귀 검사 |
| FR-08 | §3.1 타입 분리 테스트 | 필드 집합 테스트 |
| FR-09 | §2.2 Semaphore/timeout/retry, §6.3 | UseCase 단위(fake 지연·429) |
| FR-10 | §6.1 MULTIMODAL_NOT_CONFIGURED | UseCase 단위 + L1 #9 |
| FR-11 | §3.3 V064, §4.1 | L1 #14 + COMMENT 검사 |
| FR-12 | §3.3 V065 | COMMENT 검사 + repo 단위 |
| FR-13 | §4.2 PUT | L1 #4~7 |
| FR-14 | §4.2 test | L1 #8~9 |
| FR-15 | §4.2 preview | L1 #10~13 |
| FR-16 | §4.2 인프로세스 포트 | UseCase 단위(run 시그니처·예외) |
| FR-17 | §9.5 레지스트리 키 | registries 단위(미등록 오류) |
| FR-18 | §5.1~5.4 | L2 #1~6, #8 |
| FR-19 | §5.4 llm-models | L2 #7 |
| FR-20 | §2.3 UsageCallback, §10.4 로깅 | 어댑터 단위(콜백 전달) + verify-logging |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-21 | 초안 — Option C 선택(체크포인트 3), FR-01~20 역추적 | 배상규 |
| 0.2 | 2026-08-21 | Act-1 구현 동기화 — `ExtractionResult.dropped`/`DroppedCandidate`, `/test` 실패=200 ok=false(502 폐기), 415 `UNSUPPORTED_MEDIA`, 413, 손상 PDF→415, thumbnailer DI, `multimodal_di.py`, §9.5 시그니처(options), transient 재시도 범위, §8.2 #10 통합 테스트 명세, `DescribeOutcome.output_mode` | 배상규 |
