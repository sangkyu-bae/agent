# golden-sample-blueprint Design Document

> **Summary**: Golden Sample(PDF/PPTX) → `DocumentBlueprint` 추출·편집·저장, 새 워커 `presentation_generator`가 blueprint 슬롯만 LLM으로 채워 python-pptx로 PPTX(+MCP PDF) 생성.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1
> **Author**: 배상규 (with Claude)
> **Date**: 2026-08-22
> **Status**: Draft
> **Planning Doc**: [golden-sample-blueprint.plan.md](../../01-plan/features/golden-sample-blueprint.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 표준 양식(레이아웃·팔레트·폰트·페이지 구성·문체) 재현이 불가능하고 PPT 출력이 없어 생성 문서의 현업 재가공 비용이 크다 |
| **WHO** | P2(에이전트 소유자/관리자)가 blueprint 등록·편집·워커 연결; 최종 사용자는 대화로 PPT 수령 |
| **RISK** | 비전 분류 오류·폰트 복제 불가 → "구조·톤 재현"이 한계. 관리자 편집 단계·기대치 명시로 완화 |
| **SUCCESS** | 샘플 1부 → blueprint E2E; 생성 PPTX가 패턴 순서·팔레트·폰트 매핑 100% 적용; 네이티브 차트; 실 LLM 스모크; 기존 테스트 회귀 0 |
| **SCOPE** | Phase 1: 추출·편집·저장 + presentation_generator + PPTX 렌더 + PDF MCP 변환 / Phase 2: DOCX·다중 샘플·.potx·버전 관리 |

---

## 1. Overview

### 1.1 Design Goals

1. **형식은 코드가, 내용은 LLM이** — LLM 출력은 strict 구조화 데이터만. 렌더러는 HTML/마크업을 절대 받지 않는다.
2. **재사용 우선** — 비전 어댑터(`VisionDescriberPort` 구현체), `PdfPyMuPdfExtractor`, `DocumentConversionAdapter`, 워커 바인딩 패턴, admin 라우터 에러 포맷을 복제 없이 주입·재사용.
3. **탈착형** — `wire_blueprint(app, ...)` 1회 호출, 컴파일러 분기 1개. 미배선 시 워커는 안내 노옵(문서생성기 D9 동형).
4. **건별 degraded / 설정 오류 예외** 경계를 추출·생성 양쪽에 동일 적용.

### 1.2 Design Principles

- Thin DDD: domain 외부 의존 0(AST 계약 테스트), application은 흐름만, infrastructure에 PyMuPDF/python-pptx/LangChain.
- 좌표는 슬라이드 비율(0..1 float)로 저장, EMU 변환은 렌더러에서만.
- 새 설정 키 0: 비전 모델·동시성·타임아웃은 `multimodal_setting` 재사용, 변환 도구는 워커 tool_config, 폰트 디렉토리만 선택 env.
- `schema_version` 필드로 blueprint JSON 하위호환.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | **C: Pragmatic** |
|---|:-:|:-:|:-:|
| Approach | DocumentGenerator에 pptx 분기, blueprint를 multimodal 서브패키지로 | 도메인 3분할 + 전면 레지스트리 + 바인딩 공용화 리팩토링 | 신규 도메인 1개 + 포트 3개, 기존 어댑터/패턴 주입 재사용, 새 워커 분리 |
| New Files | ~18 | ~45 | ~30 |
| Modified Files | 9 | 14 | 8 |
| Complexity | Low | High | Medium |
| Maintainability | Medium (FR-20 위반) | High | High |
| Effort | Low | High | Medium |
| Risk | 기존 문서생성기 회귀 | 과도한 추상화 | Balanced |

**Selected: C** — Plan 결정(새 워커·기존 코드 무변경·탈착형)과 일치. DOCX 렌더러는 Phase 2에서 `SlideRendererPort` 뒤에 추가.

### 2.1 Component Diagram

```
┌──────────────── idt_front ────────────────┐
│ /admin/blueprints (AdminBlueprintsPage)    │   AgentBuilder: PresentationGeneratorConfigPanel
└──────┬─────────────────────────────────────┘              │ (blueprint_id 선택, output_format, max_slides)
       │ multipart / JSON                                   ▼
┌──────▼──────────────────── api ───────────────────────────────────────────┐
│ admin_blueprint_router  ──▶ BlueprintExtractionUseCase / BlueprintAdminUseCase
│ blueprint_di.wire_blueprint(app, get_session, llm_factory, logger,        │
│     vision_registry, pdf_extractor, conversion_adapter, attachment_store) │
└──────┬───────────────────────────────────────────────────────────────────┘
       │                            application/blueprint
┌──────▼──────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
│ ExtractionUseCase   │   │ AdminUseCase (CRUD·폰트) │   │ PresentationGenerationUC │◀─ workflow_compiler
│ sample → stats      │   │                          │   │ plan → write → render    │   (_create_presentation_
│ → classify(vision)  │   │                          │   │ → store → (pdf convert)  │    generator_node)
│ → synthesize(LLM)   │   └──────────────────────────┘   └──────────────────────────┘
└──┬────────┬─────────┘
   │        │               domain/blueprint (VO·schemas·policies·interfaces·errors)
   ▼        ▼
SampleExtractorRegistry          PageClassifierPort         SlideRendererPort
 ├ PdfStyleExtractor (PyMuPDF,    └ VisionPageClassifier     └ PptxSlideRenderer (python-pptx)
 │   PdfPyMuPdfExtractor 재사용)     (기존 VisionDescriberPort
 └ PptxStyleExtractor (python-pptx)   어댑터를 주입, 프롬프트만 다름)
                                 BlueprintRepository (MySQL: document_blueprint, _asset)
                                 FontCatalog (설치 폰트 스캔, env BLUEPRINT_FONT_DIR)
                                 DocumentConversionAdapter.to_pdf_from_pptx (MCP pptx_to_pdf)
```

### 2.2 Data Flow

**추출**
```
upload(pdf|pptx) → SampleExtractorRegistry.resolve(ext)
  → SampleStats(pages[ spans(font,size,bold,color,bbox), tables(bbox), images(sha,bbox), has_text ], slide_size, theme?)
  → RepeatAssetPolicy(stats)        → assets[] (≥2페이지 동일 sha·근접 bbox → logo/decoration, 표지 전면 → cover)
  → PaletteClusterPolicy(stats)     → palette(primary, accent[], text, bg)      (면적·빈도 가중)
  → SizeHierarchyPolicy(stats)      → sizes(h1,h2,body,caption), fonts(heading, body)
  → PageClassifier(page_png, hints) → PagePatternDraft[] (strict; 실패 → kind=unknown, degraded)
  → BlueprintSynthesizer(LLM strict) → NarrativeDraft(sections[], tone)   (입력: 패턴 순서+제목 텍스트)
  → DocumentBlueprintDraft (서버 필드 채움: source_kind, page_count, warnings, font_mapping 제안)
→ 응답: draft + page_thumbnails[] (편집 화면용)
```

**생성**
```
worker node(state) → blueprint = repo.get(blueprint_id) (inactive → 안내 노옵)
  → evidence_block, conversation_block = compiler._split_fill_context (문서생성기 동형)
  → SlidePlanner(LLM strict): narrative + pattern catalog + 사용자 지시 + max_slides → SlidePlan[]
      SlidePlanValidationPolicy: pattern_id ∈ blueprint, 슬롯 id ∈ pattern, count ≤ max → 위반 시 재시도 1회, 여전히 위반 슬라이드는 제외+warning
  → SlotWriter(LLM strict, 슬라이드당 1회, Semaphore(concurrency 재사용)): SlideContent(slots{text|bullets|table|chart})
      SlotContentPolicy: 길이·행열·차트 series 수 검증 → 위반 슬롯은 빈 슬롯+warning (degraded)
  → PptxSlideRenderer.render(blueprint, slides) → bytes
  → AttachmentStore.save(.pptx, DOCUMENT)
  → output_format==pdf: conversion.to_pdf_from_pptx → 저장; 실패/미설정 → PPTX만 + warning
  → GenerateResult 동형 DTO → AIMessage(다운로드 링크, 경고)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|---|---|---|
| PdfStyleExtractor | PyMuPDF (직접 — `PdfPyMuPdfExtractor`는 ImageCandidate 필터 경로라 재사용 대상 아님, v0.2) | span/표/이미지(xref 중복 제거) 통계, 페이지 렌더 PNG |
| PptxStyleExtractor | python-pptx | 테마 major/minor 폰트·도형 좌표·표/차트 영역(`PageStats.charts`, v0.2)·그림 blob, 렌더 PNG는 **없음** → 분류는 도형 통계 기반 |
| VisionPageClassifier | 기존 `VisionDescriberPort` 구현체(`VisionAdapterRegistry.build`) | 페이지 PNG → `PagePatternDraft` |
| BlueprintSynthesizer / SlidePlanner / SlotWriter | `LLMFactory` + `with_structured_output(strict→json 폴백)` | 텍스트 LLM 호출 (비전 불필요, 워커 LLM 사용) |
| PptxSlideRenderer | python-pptx, FontCatalog | 슬라이드 렌더 |
| DocumentConversionAdapter | MCP | pptx→pdf |

---

## 3. Data Model

### 3.1 Entity Definition (domain/blueprint/value_objects.py)

```python
class PatternKind(str, Enum):   # Literal 로도 schemas 에 복제 (strict)
    COVER="cover"; TOC="toc"; SECTION_LEAD="section_lead"; TEXT="text"
    CHART_WITH_NOTES="chart_with_notes"; TABLE="table"; TWO_COLUMN="two_column"
    IMAGE_WITH_NOTES="image_with_notes"; CLOSING="closing"; UNKNOWN="unknown"

class SlotKind(str, Enum): TITLE="title"; TEXT="text"; BULLETS="bullets"; TABLE="table"; CHART="chart"; IMAGE="image"; FOOTER="footer"

@dataclass(frozen=True)
class RelBox: x: float; y: float; w: float; h: float          # 0..1 슬라이드 비율, 검증

@dataclass(frozen=True)
class Slot: id: str; kind: SlotKind; box: RelBox; role: str; max_chars: int | None; max_rows: int | None; asset_id: str | None  # IMAGE 슬롯 고정 에셋

@dataclass(frozen=True)
class PagePattern: id: str; kind: PatternKind; slots: tuple[Slot, ...]; background: str | None; sample_page: int; notes: str

@dataclass(frozen=True)
class StyleTokens:
    slide_size: tuple[float, float]                 # inch
    fonts: dict[str, str]                           # {"heading": "HY헤드라인M", "body": "맑은 고딕"} (원본명)
    sizes: dict[str, float]                         # {"h1": 28, "h2": 20, "body": 14, "caption": 10} pt
    palette: dict[str, str]                         # {"primary": "#1F3A5F", "accent1": ..., "text": ..., "bg": ...}
    table_style: TableStyle                         # header_bg, header_text, border, zebra
    header_footer: HeaderFooter                     # logo_asset_id, page_number_format, footer_text

@dataclass(frozen=True)
class NarrativeSection: role: str; pattern_ids: tuple[str, ...]; guidance: str
@dataclass(frozen=True)
class Narrative: sections: tuple[NarrativeSection, ...]; tone: str; language: str

@dataclass(frozen=True)
class BlueprintAsset: id: str; kind: Literal["logo","decoration","cover"]; mime: str; width: int; height: int; sha256: str; box: RelBox; adopted: bool

@dataclass(frozen=True)
class DocumentBlueprint:
    id: str; name: str; description: str; schema_version: int = 1
    source_kind: Literal["pdf","pptx"]; page_count: int
    style: StyleTokens; patterns: tuple[PagePattern, ...]; narrative: Narrative
    assets: tuple[BlueprintAsset, ...]; font_mapping: dict[str, str]   # 원본 폰트명 → 서버 폰트명
    warnings: tuple[str, ...]; status: Literal["active","inactive"]; created_at; updated_at

# 생성 측
@dataclass(frozen=True) class ChartSpec: type: Literal["bar","line","pie"]; categories: tuple[str,...]; series: tuple[tuple[str, tuple[float,...]], ...]; unit: str | None
@dataclass(frozen=True) class TableSpec: header: tuple[str,...]; rows: tuple[tuple[str,...],...]
@dataclass(frozen=True) class SlotContent: slot_id: str; text: str | None; bullets: tuple[str,...] | None; table: TableSpec | None; chart: ChartSpec | None
@dataclass(frozen=True) class SlidePlan: index: int; pattern_id: str; title: str; intent: str; data_hint: str
@dataclass(frozen=True) class SlideContent: plan: SlidePlan; slots: tuple[SlotContent,...]; warnings: tuple[str,...]
@dataclass(frozen=True) class PresentationResult: file_id: str; filename: str; pdf_file_id: str | None; slide_count: int; chart_count: int; warnings: tuple[str,...]; usage: dict
```

**schemas.py (LLM Draft, pydantic `extra="forbid"`)**: `PagePatternDraft(kind, slots[SlotDraft(kind, box, role, max_chars?)], layout_notes)`, `NarrativeDraft`, `SlidePlanDraft(slides[...])`, `SlideContentDraft(slots[...])`. `DRAFT_COPIED_FIELDS`/`SERVER_COMPUTED_FIELDS` 필드셋 동등성 테스트(multimodal 동형). dict/Any 금지 — `fonts`/`sizes`/`palette`는 Draft에서는 명시 필드 모델(`PaletteDraft(primary, accent1, accent2, text, bg)`), VO에서만 dict.

### 3.2 Entity Relationships

```
[document_blueprint] 1 ── N [document_blueprint_asset]
        ▲ (soft ref: worker tool_config.blueprint_id)
[agent worker presentation_generator]
        │ 실행 시
[attachment store] ◀── 생성 PPTX/PDF (TTL 첨부)
```

### 3.3 Database Schema — `db/migration/V066__create_document_blueprint.sql`

```sql
CREATE TABLE document_blueprint (
  id            VARCHAR(36)  NOT NULL COMMENT 'blueprint ID (UUID)',
  name          VARCHAR(100) NOT NULL COMMENT '표시 이름',
  description   VARCHAR(500) NOT NULL DEFAULT '' COMMENT '설명',
  source_kind   VARCHAR(10)  NOT NULL COMMENT '원본 종류 (pdf 또는 pptx)',
  page_count    INT          NOT NULL COMMENT '원본 페이지 수',
  schema_version INT         NOT NULL DEFAULT 1 COMMENT 'blueprint JSON 스키마 버전',
  blueprint_json JSON        NOT NULL COMMENT 'style·patterns·narrative·font_mapping·warnings 직렬화',
  status        VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT '상태 (active 또는 inactive)',
  created_by    VARCHAR(36)  NOT NULL COMMENT '등록 관리자 사용자 ID',
  created_at    DATETIME     NOT NULL COMMENT '생성 시각',
  updated_at    DATETIME     NOT NULL COMMENT '수정 시각',
  PRIMARY KEY (id), KEY idx_document_blueprint_status (status)
) COMMENT='Golden Sample 에서 추출한 발표자료 양식 blueprint';

CREATE TABLE document_blueprint_asset (
  id            VARCHAR(36)  NOT NULL COMMENT '에셋 ID (UUID)',
  blueprint_id  VARCHAR(36)  NOT NULL COMMENT '소속 blueprint ID',
  kind          VARCHAR(20)  NOT NULL COMMENT '에셋 종류 (logo 또는 decoration 또는 cover)',
  mime          VARCHAR(50)  NOT NULL COMMENT 'MIME 타입',
  width         INT          NOT NULL COMMENT '픽셀 너비',
  height        INT          NOT NULL COMMENT '픽셀 높이',
  sha256        CHAR(64)     NOT NULL COMMENT '내용 해시',
  box_json      JSON         NOT NULL COMMENT '슬라이드 비율 좌표 (x y w h)',
  adopted       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '관리자 채택 여부',
  data          LONGBLOB     NOT NULL COMMENT '이미지 바이트 (TTL 없는 영구 보관)',
  created_at    DATETIME     NOT NULL COMMENT '생성 시각',
  PRIMARY KEY (id), KEY idx_document_blueprint_asset_bp (blueprint_id)
) COMMENT='blueprint 로고·장식·표지 이미지 에셋';
```

> Plan FR-09 조정: `AttachmentStore`는 TTL 자동 삭제가 있어 에셋 영구 보관에 부적합 → LONGBLOB 보관(로고류는 수백 KB 이하, 에셋당 2MB·blueprint당 20개 상한). COMMENT 안에 쉼표 금지 규칙 준수.

---

## 4. API Specification

### 4.1 Endpoint List (모두 `require_role("admin")`, 에러 `{detail:{code,message}}`)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/admin/blueprints/extract` | multipart `file` → `BlueprintDraftResponse` (저장 안 함) |
| POST | `/api/v1/admin/blueprints` | 편집된 draft + 에셋 채택 → 저장 (201) |
| GET | `/api/v1/admin/blueprints` | 목록(요약: id,name,source_kind,page_count,status,pattern_count,updated_at) |
| GET | `/api/v1/admin/blueprints/{id}` | 상세(blueprint 전체 + 에셋 메타) |
| PUT | `/api/v1/admin/blueprints/{id}` | name/description/style/patterns/narrative/font_mapping/status/asset adopted 갱신 |
| DELETE | `/api/v1/admin/blueprints/{id}` | soft delete(status=inactive) |
| GET | `/api/v1/admin/blueprints/{id}/assets/{asset_id}` | 이미지 바이트(미리보기) |
| GET | `/api/v1/admin/blueprints/fonts` | 서버 설치 폰트 목록 + 기본 폰트 |
| GET | `/api/v1/blueprints/options` | 에이전트 빌더용 active 목록(id,name) — 로그인 사용자 |

### 4.2 Detailed Specification

#### `POST /api/v1/admin/blueprints/extract`
Request: multipart `file` (.pdf/.pptx, ≤30MB), query `max_pages` (기본 60).
Response 200:
```json
{ "draft": { "name": "sample", "source_kind": "pdf", "page_count": 12, "schema_version": 1,
    "style": { "slide_size": [13.333, 7.5], "fonts": {"heading": "HY헤드라인M", "body": "맑은 고딕"},
               "sizes": {"h1": 28, "h2": 20, "body": 14, "caption": 10},
               "palette": {"primary": "#1F3A5F", "accent1": "#E07A1F", "text": "#222222", "bg": "#FFFFFF"},
               "table_style": {"header_bg": "#1F3A5F", "header_text": "#FFFFFF", "border": "#CCCCCC", "zebra": true},
               "header_footer": {"logo_asset_id": "a1", "page_number_format": "{n} / {total}", "footer_text": "KB 여신심사부"} },
    "patterns": [ { "id": "p1", "kind": "cover", "sample_page": 1, "background": "#1F3A5F",
                    "slots": [ {"id": "title", "kind": "title", "box": {"x":0.08,"y":0.35,"w":0.84,"h":0.15}, "role": "제목", "max_chars": 40} ] } ],
    "narrative": { "sections": [ {"role": "표지", "pattern_ids": ["p1"], "guidance": "주제·일자·부서"} ], "tone": "보고체 개조식", "language": "ko" },
    "font_mapping": {"HY헤드라인M": "NanumGothicBold", "맑은 고딕": "NanumGothic"},
    "warnings": ["page 7: 패턴 분류 실패(unknown)", "font '맑은 고딕' 미설치 → NanumGothic 제안"] },
  "assets": [ {"id": "a1", "kind": "logo", "mime": "image/png", "width": 320, "height": 90, "box": {...}, "adopted": true, "thumbnail_b64": "..."} ],
  "page_thumbnails": ["<b64>", "..."],
  "classification": {"succeeded": 11, "failed": 1}, "timings_ms": {"extract": 820, "classify": 14200, "synthesize": 3100} }
```
Errors: 415 `UNSUPPORTED_MEDIA`(확장자/손상), 413 `PAYLOAD_TOO_LARGE`, 409 `MULTIMODAL_NOT_CONFIGURED`/`MULTIMODAL_DISABLED`(비전 모델 미설정), 400 `VALIDATION_ERROR`, 500 `UNSUPPORTED_VISION_PROVIDER`.

#### `POST /api/v1/admin/blueprints`
Request: `{ draft: <위 draft 편집본>, assets: [{id, adopted, data_b64}] }` → 201 `{id, ...상세}`. 검증 실패 400 `VALIDATION_ERROR`(패턴 id 중복, 슬롯 box 범위, narrative pattern_ids 미존재, 에셋 상한).

#### 워커 실행(에이전트 그래프 내부, HTTP 없음)
`PresentationGenerationUseCase.generate(llm, blueprint, tool_config, evidence_block, conversation_block, user_instruction, owner_user_id, request_id) -> PresentationResult`. 예외: `BlueprintNotConfiguredError`(안내 노옵), `PresentationGenerateError`(LLM 응답 공백·렌더 실패), `McpConversionError`(PDF만 degraded).

---

## 5. UI/UX Design

### 5.1 Screen Layout — `/admin/blueprints`

```
┌ Blueprint 라이브러리 ───────────────────────────── [+ 새 blueprint] ┐
│ 목록 테이블: 이름 | 원본 | 페이지 | 패턴 수 | 상태 | 수정일 | [편집][비활성화] │
└──────────────────────────────────────────────────────────────────┘
[+ 새 blueprint] → 추출 화면
┌ 1. 업로드 (.pdf/.pptx, 30MB) [추출 시작] 진행: 추출→분류→종합 ─────────┐
│ 2. 결과 탭: [스타일] [페이지 패턴] [서사] [폰트 매핑] [에셋] [경고]      │
│   스타일: 팔레트 색 칩(편집) · 크기 체계 입력 · 표 스타일 · 헤더/푸터      │
│   페이지 패턴: 썸네일 그리드(페이지별 kind 드롭다운·슬롯 목록·제외 토글)   │
│   서사: 섹션 행(역할·패턴 선택·지침) 추가/삭제/순서                       │
│   폰트 매핑: 원본 폰트 → 서버 폰트 select (미설치 경고)                  │
│   에셋: 썸네일 + kind + 채택 체크                                       │
│ 3. 이름/설명 입력 → [저장]                                              │
└──────────────────────────────────────────────────────────────────────┘
```
에이전트 빌더: `PresentationGeneratorConfigPanel` — blueprint select(옵션 API), output_format(pptx|pdf), pptx→pdf MCP 도구 select(pdf일 때), max_slides(1..60, 기본 15).

### 5.2 User Flow
```
관리자: /admin/blueprints → 새 blueprint → 업로드·추출 → 탭 검토·편집 → 저장
소유자: 에이전트 빌더 → 워커 도구 presentation_generator → blueprint 선택 → 저장
사용자: 채팅 첨부(xlsx) + "3분기 연체율 PPT 10장 이내로" → 다운로드 링크
```

### 5.3 Component List (idt_front)

| Component | Location | Responsibility |
|---|---|---|
| AdminBlueprintsPage | `pages/AdminBlueprintsPage/index.tsx` | 목록 + 라우팅(추출/편집 모드) |
| BlueprintUploadStep | 〃`/BlueprintUploadStep.tsx` | 파일 선택·추출 호출·진행 |
| BlueprintList, BlueprintEditor, BlueprintTabs(Style/Patterns/Narrative/FontMapping/Assets/Warnings 서브컴포넌트 1파일) | 〃 | 목록 · 추출/편집(가역 패턴 제외 토글, 저장 시 적용) · 편집 탭 (v0.8: 탭별 파일 분리 대신 단일 파일) |
| PresentationGeneratorConfigPanel | `components/agent-builder/` | 워커 설정 (DocumentGeneratorConfigPanel 동형) |
| types/blueprint.ts | `types/` | 타입 + `PATTERN_KINDS`/`SLOT_KINDS` as const + 라벨 + `BLUEPRINT_LIMITS` |
| services/blueprintService.ts, hooks/useBlueprints.ts (extract 뮤테이션 포함) | | API·쿼리(`queryKeys.blueprints.*`) |
| utils/blueprintValidators.ts | | 클라 검증(box 0..1, 이름 필수, 패턴 id 유일) |

### 5.4 Page UI Checklist

#### /admin/blueprints (목록)
- [ ] Button: "새 blueprint" → 추출 화면
- [ ] Table 컬럼: 이름, 원본(pdf/pptx 배지), 페이지 수, 패턴 수, 상태(active/inactive 배지), 수정일
- [ ] Row action: 편집, 비활성화(확인 다이얼로그)
- [ ] Empty state 문구, 로딩 스켈레톤, 에러 메시지(`ApiError.message`)

#### /admin/blueprints (추출/편집)
- [ ] Input: file (accept .pdf,.pptx), 30MB 초과 시 클라 경고
- [ ] Button: "추출 시작"(LoadingButton, isPending) / 진행 단계 텍스트
- [ ] Tab: 스타일 — 팔레트 4+ 색 input(type=color + hex 텍스트), 크기 4 number(h1,h2,body,caption), 표 스타일(header_bg, header_text, border hex 입력 + zebra checkbox), 헤더/푸터(logo 에셋 select — 채택 에셋만 + '로고 없음', page_number_format, footer_text)
- [ ] Tab: 페이지 패턴 — 페이지 썸네일 카드(kind select 10종, 슬롯 목록(id/kind/role/max_chars), "패턴 제외/제외 취소" 가역 토글(저장 시 적용·서사 참조 정리), unknown 경고 배지)
- [ ] Tab: 서사 — 섹션 행(role text, pattern multi-select, guidance textarea), 추가/삭제/위·아래 이동, tone/language 입력
- [ ] Tab: 폰트 매핑 — 원본 폰트명 → 서버 폰트 select(목록 API), 미설치 경고 아이콘
- [ ] Tab: 에셋 — 썸네일, kind select(logo/decoration/cover), 채택 checkbox
- [ ] Tab: 경고 — warnings 목록
- [ ] Input: 이름(필수, ≤100), 설명(≤500)
- [ ] Button: 저장(LoadingButton) → 성공 시 목록 이동·무효화

#### 에이전트 빌더 워커 설정 (presentation_generator)
- [ ] Select: blueprint (active 목록, 없음 시 안내 링크 `/admin/blueprints`)
- [ ] Radio: output_format pptx | pdf
- [ ] Input(text): pptx→pdf MCP 도구 id (pdf 선택 시 표시, 빈 값 허용 — 문서생성기 패널과 동형, `mcp_` 접두 검증)
- [ ] Number: max_slides 1..60 (기본 15)
- [ ] 검증 오류 인라인 표시, 저장 시 tool_config 직렬화

---

## 6. Error Handling

### 6.1 Error Code Definition

| HTTP | code | Cause | Handling |
|---|---|---|---|
| 400 | VALIDATION_ERROR | pydantic/정책 검증 실패 | 필드 메시지 표시 |
| 404 | BLUEPRINT_NOT_FOUND | id 없음/inactive(상세 제외) | 목록 갱신 |
| 409 | MULTIMODAL_NOT_CONFIGURED / MULTIMODAL_DISABLED | 비전 모델 미설정·비활성 | `/admin/multimodal` 안내 |
| 413 | PAYLOAD_TOO_LARGE | 30MB 초과 | |
| 415 | UNSUPPORTED_MEDIA | 확장자·손상 파일(`ExtractionError`) | |
| 422→400 | VALIDATION_ERROR | FastAPI 기본 422 를 400으로 매핑(멀티모달 동형) | |
| 500 | UNSUPPORTED_VISION_PROVIDER | 레지스트리 미등록 provider | |

워커 실행(HTTP 아님): blueprint 미설정/inactive → 안내 노옵 AIMessage; LLM 공백 2회 → "발표자료 생성 실패: …"; PDF 변환 실패 → PPTX 링크 + "(PDF 변환 실패 — PPTX 제공)" 경고.

### 6.2 Error Response Format
```json
{ "detail": { "code": "VALIDATION_ERROR", "message": "patterns[2].slots[0].box.x must be within 0..1" } }
```

### 6.3 Degraded vs Failure 경계 (위키 degradation-vs-failure-boundary)

| 상황 | 처리 |
|---|---|
| 페이지 1장 비전 분류 실패/타임아웃 | 패턴 kind=unknown + warning, 추출 계속 |
| 종합 LLM(narrative) 실패 | narrative = 패턴 순서 기반 기본 서사 + warning |
| 폰트 미설치 | 기본 폰트 + warning |
| 슬라이드 1장 plan 검증 실패(재시도 후) | 제외 + warning |
| 슬롯 1개 내용 검증 실패 | 빈 슬롯 + warning |
| PDF 변환 실패/도구 미설정 | PPTX만 + warning |
| 비전 모델 미설정·확장자 미지원·파일 손상·blueprint inactive | **예외/409·415** |

---

## 7. Security Considerations

- [x] admin 전용 라우트(`require_role("admin")`), 옵션 API만 로그인 사용자
- [x] 업로드 확장자 화이트리스트 + 30MB + `max_pages` 상한(기본 60) — 비용·DoS 가드
- [x] LLM 출력은 strict 스키마 → 데이터로만 렌더(python-pptx 텍스트 run), HTML/마크업·수식 미해석
- [x] 프롬프트 주입 방어: 근거 블록을 "데이터"로 선언, 시스템 프롬프트에 지시 무시 문구(multimodal prompts 동형)
- [x] 에셋 MIME sniff(PNG/JPEG만), 크기 상한 2MB/개, 20개/blueprint
- [x] 파일명 경로 컴포넌트 제거(`AttachmentStore` 기존 동작)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|---|---|---|---|
| L1 단위/계약 | domain VO·schemas·policies·AST 레이어 계약, 추출기(합성 PDF/PPTX), 렌더러(재오픈 검증), UseCase(fake LLM/vision) | pytest | Do |
| L1 API | admin 라우터 전 엔드포인트, 워커 노드 컴파일 | pytest TestClient | Do |
| L2 UI | AdminBlueprintsPage, ConfigPanel | Vitest+RTL+MSW | Do |
| L3 E2E(백엔드) | 합성 샘플 → 추출 → 저장 → 워커 생성 → PPTX 재오픈 (UseCase mock 없음) | pytest | Do |
| Smoke | 실 LLM 1회(`-m llm`) | pytest | Do(module-6) |

### 8.2 L1 API Test Scenarios

| # | Endpoint | Method | Test | Status | Expect |
|---|---|---|---|---|---|
| 1 | /admin/blueprints/extract | POST | 합성 PDF(표지+목차+차트+표+결론 5p) + fake vision | 200 | patterns 5, kinds 순서 일치, assets 로고 1(2p 반복), palette.primary = 주입 색 |
| 2 | 〃 | POST | 합성 PPTX | 200 | source_kind=pptx, slide_size=(13.333,7.5), fonts.heading = 테마 폰트 |
| 3 | 〃 | POST | .docx | 415 | UNSUPPORTED_MEDIA |
| 4 | 〃 | POST | 손상 PDF | 415 | |
| 5 | 〃 | POST | 31MB | 413 | |
| 6 | 〃 | POST | 비전 미설정 | 409 | MULTIMODAL_NOT_CONFIGURED |
| 7 | 〃 | POST | 비전 1페이지 타임아웃 | 200 | 해당 kind=unknown, classification.failed=1 |
| 8 | /admin/blueprints | POST | 유효 draft | 201 | id, DB row, asset row adopted 반영 |
| 9 | 〃 | POST | box.x=1.2 / 중복 pattern id / narrative 미존재 pattern | 400 | VALIDATION_ERROR |
| 10 | /admin/blueprints/{id} | PUT | font_mapping·status 갱신 | 200 | updated_at 변경 |
| 11 | /admin/blueprints/{id} | DELETE | soft | 200 | status=inactive, 옵션 API 에서 제외 |
| 12 | /admin/blueprints/fonts | GET | | 200 | default 포함 |
| 13 | /admin/blueprints | GET | 비관리자 | 403 | |
| 14 | 워커 노드 | – | blueprint inactive | – | 안내 AIMessage, 예외 없음 |
| 15 | 워커 노드 | – | 정상(fake LLM) | – | AIMessage 에 다운로드 링크, 파일 존재 |
| 16 | 워커 노드 | – | output_format=pdf + MCP 실패 | – | PPTX 링크 + 경고 문구 |

### 8.3 L2 UI Action Test Scenarios

| # | Page | Action | Expected |
|---|---|---|---|
| 1 | 목록 | 로드 | 행 렌더, 배지 |
| 2 | 추출 | 파일 선택 + 추출 | multipart content-type, 진행 표시 → 탭 렌더 |
| 3 | 스타일 탭 | 색 hex 수정 | draft 상태 반영 |
| 4 | 패턴 탭 | kind 변경·제외 | 저장 payload 반영 |
| 5 | 서사 탭 | 섹션 추가·순서 이동 | 순서 반영 |
| 6 | 폰트 탭 | select 변경 | font_mapping 반영, 미설치 경고 |
| 7 | 저장 | 이름 누락 | 인라인 에러, 요청 없음 |
| 8 | 저장 | 성공 | 목록 이동, 쿼리 무효화 |
| 9 | ConfigPanel | blueprint 없음 | 안내 링크 |
| 10 | ConfigPanel | pdf 선택 | MCP select 표시, max_slides 범위 검증 |

### 8.4 L3 E2E Scenario (백엔드 통합, fake LLM/vision)

| # | Scenario | Steps | Success |
|---|---|---|---|
| 1 | 추출→저장→생성 | 합성 PDF extract → draft 저장 → 워커 tool_config → generate(첨부 표 데이터) → PPTX 재오픈 | 슬라이드 수 = plan 수, 각 슬라이드 도형 kind = 패턴 슬롯, 차트 shape 존재·series 색 = palette.accent1, run font = font_mapping 값, 로고 picture 존재 |
| 2 | degraded | plan 1장 pattern_id 오류 + 슬롯 1개 초과 길이 | 제외·빈 슬롯 + warnings 2건, 전체 성공 |
| 3 | 실 LLM 스모크(`-m llm`) | 합성 샘플 → 실 비전 분류 → 실 planner/writer → PPTX | cover/chart 패턴 검출, 차트 ≥1, 파일 재오픈 OK |

### 8.5 Seed Data
합성 fixture 코드 생성(`tests/fixtures/blueprint_samples.py`): PDF(fitz, 5페이지, 2색 팔레트, 로고 PNG 2회 반복, 표 1, 차트 이미지 1) / PPTX(python-pptx, 동일 구성). DB seed 불필요(테스트에서 저장).

---

## 9. Clean Architecture

### 9.1 Layer Structure (백엔드)

| Layer | Files |
|---|---|
| domain/blueprint | `value_objects.py`, `schemas.py`, `policies.py`(PaletteCluster, SizeHierarchy, RepeatAsset, SlidePlanValidation, SlotContent), `interfaces.py`(SampleExtractorPort, PageClassifierPort, SlideRendererPort, BlueprintRepository, FontCatalogPort), `errors.py`, `tool_config.py`(PresentationGeneratorToolConfig) |
| application/blueprint | `registries.py`(SampleExtractorRegistry), `extraction_use_case.py`, `admin_use_case.py`, `generation_use_case.py`, `prompts_contract.py`(없음 — 프롬프트는 infra) |
| infrastructure/blueprint | `extractors/pdf_style_extractor.py`, `extractors/pptx_style_extractor.py`, `vision/page_classifier.py`, `llm/synthesizer.py`, `llm/slide_planner.py`, `llm/slot_writer.py`, `prompts.py`, `renderer/pptx_renderer.py`, `renderer/chart_builder.py`, `fonts.py`, `models.py`, `repository.py` |
| interfaces/api | `interfaces/schemas/blueprint.py`, `api/routes/admin_blueprint_router.py`, `api/blueprint_di.py` |
| 수정 | `domain/agent_builder/tool_registry.py`(+presentation_generator), `application/agent_builder/{schemas,create_agent_use_case,update_agent_use_case,workflow_compiler}.py`, `infrastructure/document_extractor/document_conversion_adapter.py`(+to_pdf_from_pptx), `api/main.py`(+wire), `pyproject.toml`(완료) |

### 9.2 Dependency Rules
domain → 표준 라이브러리만(AST 계약 테스트 `tests/domain/blueprint/test_layer_contract.py`, application 동형). application → domain + `src.domain.llm.interfaces`/`llm_model`. infrastructure → domain(+LangChain/PyMuPDF/python-pptx). api → application/infrastructure 조립만(`blueprint_di.py`).

### 9.3 Key Signatures

```python
class SampleExtractorPort(Protocol):
    supported_extensions: tuple[str, ...]
    def extract(self, data: bytes, filename: str, max_pages: int) -> SampleStats: ...
class PageClassifierPort(Protocol):
    async def classify(self, page_png: bytes, hints: PageHints, options: DescribeOptions) -> PagePatternDraft: ...
class SlideRendererPort(Protocol):
    def render(self, blueprint: DocumentBlueprint, slides: Sequence[SlideContent], assets: Mapping[str, bytes], font_mapping: Mapping[str, str]) -> bytes: ...
class BlueprintExtractionUseCase:
    async def run(self, data: bytes, filename: str, max_pages: int, request_id: str) -> ExtractionOutcome  # draft, assets(bytes), thumbnails, stats
class PresentationGenerationUseCase:
    async def generate(self, llm, blueprint, assets, tool_config, evidence_block, conversation_block, user_instruction, owner_user_id, request_id) -> PresentationResult
```
VisionPageClassifier 는 `VisionAdapterRegistry.build(provider, ...)` 로 얻은 `VisionDescriberPort` 를 감싸되, **프롬프트가 다르므로** `BaseVisionAdapter` 의 messages 빌더를 주입 가능하게 하지 않고, 분류 전용 시스템/태스크 프롬프트를 `infrastructure/blueprint/prompts.py` 에 두고 어댑터의 `_call(messages, schema)` 경로만 재사용한다(어댑터 public 확장 `describe_with(messages, schema)` 1개 추가 — multimodal 어댑터 수정 최소 1건, 기존 테스트 불변).

---

## 10. Decision Records

| # | 결정 | 근거 |
|---|---|---|
| D1 | 좌표 0..1 비율 저장 | PDF(pt)·PPTX(EMU) 원본 차이 흡수, 슬라이드 크기 변경에 안전 |
| D2 | 에셋 LONGBLOB (AttachmentStore 미사용) | TTL 삭제 회피, 로고류 소용량 |
| D3 | 비전 모델은 multimodal_setting 재사용 | 설정 단일 소스, 새 키 0 |
| D4 | PPTX 원본은 페이지 렌더 없이 도형 통계로 분류, PDF 동봉 시 렌더 사용 | python-pptx 렌더 불가, LibreOffice 의존 회피 |
| D5 | 슬롯 작성은 슬라이드당 LLM 1회(동시) | 슬라이드 간 독립, 부분 실패 격리 |
| D6 | 차트 3종(bar/line/pie) + 표 | python-pptx 안정 API 범위 |
| D7 | 워커 tool_config 소프트 참조(blueprint_id) | document_generation_type 과 달리 전역 공유 자원 |
| D8 | `describe_with` 1개 추가로 어댑터 재사용 | 어댑터 복제 금지, 기존 동작 불변 |

---

## 11. Implementation Guide

### 11.1 Implementation Order
1. 의존성(완료: python-pptx) → V066 마이그레이션 + 모델
2. domain/blueprint (VO·schemas·policies·interfaces·errors·tool_config) + 계약 테스트
3. infrastructure 추출기 2종 + 합성 fixture + FontCatalog
4. 비전 분류기(`describe_with`) + 종합 LLM + ExtractionUseCase
5. repository + AdminUseCase + admin 라우터 + DI + main 배선
6. planner/writer + 렌더러 + GenerationUseCase + conversion `to_pdf_from_pptx`
7. 워커 도구 등록 + 바인딩 + compiler 노드
8. 프론트 관리자 페이지 + ConfigPanel + 타입/서비스/훅
9. L3 통합 + 실 LLM 스모크 + 품질 게이트

### 11.2 Key Files — §9.1 참조

### 11.3 Session Guide

| Module | 내용 | 신규/수정 | 의존 |
|---|---|---|---|
| module-1 | V066 + domain/blueprint + 계약 테스트 | 8 / 0 | – |
| module-2 | 추출기 PDF·PPTX + fixture + FontCatalog + 정책 적용 | 6 / 0 | 1 |
| module-3 | 비전 분류기 + `describe_with` + 종합 LLM + ExtractionUseCase + registries | 6 / 1 | 2 |
| module-4 | models/repository + AdminUseCase + 스키마 + admin 라우터 + `blueprint_di` + main | 6 / 1 | 3 |
| module-5 | planner/writer/렌더러/chart_builder + GenerationUseCase + `to_pdf_from_pptx` | 6 / 1 | 1,4 |
| module-6 | tool_registry + 바인딩 + compiler 노드 + L3 통합 + 스모크 | 2 / 4 | 5 |
| module-7 | 프론트: types/service/hooks/validators + AdminBlueprintsPage(탭 5) + ConfigPanel + nav/route/api/queryKeys + 테스트 | 12 / 6 | 4,6 |

권장 세션: `--scope module-1,module-2` → `module-3` → `module-4` → `module-5` → `module-6` → `module-7`.

---

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 0.1 | 2026-08-22 | Option C 선택, 초안. Plan FR-09 에셋 저장소 조정(LONGBLOB) | 배상규 (with Claude) |
| 0.8 | 2026-08-22 | Act-1 반영: G1 슬롯 VO 변환 실패 → 슬롯 제외+warning(§6.3), G4 `FontCatalogPort.propose_mapping` 선언, G5 워커 노드 → `generate(callbacks=[UsageCallback])`(FR-17), G7 `max_pages` 400, G2/G3 표 색·로고 select, G9 가역 토글, §8.4 #2 degraded E2E 추가; Design 동기화: DATETIME(V065 관례), MCP id text input, 탭 단일 파일 | 배상규 (with Claude) |
| 0.7 | 2026-08-22 | module-7 반영: 추출 응답 `assets[].data_b64`(원본 바이트) 추가 — 저장(POST) 시 클라이언트가 되돌려 보냄(§4.2 간극 보정); 워커 설정은 빌더 `presentation_generator` 전용 필드 + 드래프트(`presentationGeneratorDraft`) + 상세 프리필은 워커 tool_config 에서; 탭 5 + 경고 탭 | 배상규 (with Claude) |
| 0.6 | 2026-08-22 | module-6 반영: 워커 설정은 Create/Update 요청의 `presentation_generator` 전용 필드(영속 엔티티 없음, 바인딩 헬퍼가 tool_config 주입), 런타임은 `SessionScopedBlueprintRepository`(읽기 전용), 사용자 지시 = 마지막 HumanMessage, 라우팅 가이드 블록에 발표자료 워커 포함. 실 LLM 스모크: 분류 5/5·4장·토큰 4,239 | 배상규 (with Claude) |
| 0.5 | 2026-08-22 | module-5 반영: 생성 프롬프트는 `prompts_generation.py` 분리, 워커 LLM 구조화 호출 `StructuredCaller`(어댑터 헬퍼 재사용), 계획 재시도는 미존재 pattern_id·빈 계획일 때만(초과분은 절단+warning), 작성 실패 슬라이드는 빈 슬롯으로 렌더, 표지 전면 이미지 위 제목은 흰색 | 배상규 (with Claude) |
| 0.4 | 2026-08-22 | module-4 반영: 직렬화는 `domain/blueprint/serialization.py`(blueprint_json 단일 출처), PUT 은 전체 draft 를 받아 불변 필드(id/source_kind/page_count/created_at) 유지·에셋 추가 금지, `/api/v1/blueprints/options` 는 로그인 사용자, config 키 2개(`blueprint_font_dir`/`blueprint_default_font`) 소비 지점 `blueprint_di` 1곳 | 배상규 (with Claude) |
| 0.3 | 2026-08-22 | module-3 반영: 추출 단계 서사 종합은 비전 어댑터를 텍스트 LLM으로 재사용(`NarrativeSynthesizer(adapter)`), `VisionProviderPort.resolve → VisionSession(settings, classifier, synthesizer)` DI 계약, PPTX 휴리스틱 분류(cover/table/chart/image/closing/text) | 배상규 (with Claude) |
| 0.2 | 2026-08-22 | module-1·2 구현 반영: PDF 추출기 PyMuPDF 직접 사용, `PageStats.charts` 추가, 본문 크기=글자수 가중·caption=최소 크기·배경 근접색 accent 제외 | 배상규 (with Claude) |
