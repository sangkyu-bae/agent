# golden-sample-blueprint Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1
> **Analyst**: 배상규 (with Claude) — 정적 분석: gap-detector 에이전트 / 런타임: 직접 실행
> **Date**: 2026-08-22
> **Design Doc**: [golden-sample-blueprint.design.md](../02-design/features/golden-sample-blueprint.design.md) (v0.7)
> **Plan Doc**: [golden-sample-blueprint.plan.md](../01-plan/features/golden-sample-blueprint.plan.md) (v0.1)

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

## Strategic Alignment Check

| Element | Expected | Status |
|---|---|:-:|
| Core Problem (WHY) | 양식 재현 + PPT 출력 | ✅ 추출→blueprint→슬롯 채움→PPTX 경로 구현, 실 LLM 스모크로 동작 확인 |
| Target User (WHO) | P2 관리자/소유자 | ✅ `/admin/blueprints` + 빌더 워커 설정, admin 전용 API |
| Value Proposition | "형식은 blueprint, 내용만 LLM" | ✅ LLM 출력은 strict 스키마 → 데이터로만 렌더, 패턴 외 출력은 검증 정책으로 차단 |
| 전략적 불일치 | — | 없음. 단 Design §6.3 degraded 경계 1건 누락(G1)이 "전체 성공" 원칙을 깨뜨릴 수 있어 Critical |

---

## Match Rate (v2.3.0 공식, 런타임 실행)

| Axis | Score | 근거 |
|---|:-:|---|
| Structural | 97% | 파일/엔드포인트/테이블/컴포넌트 전수 존재 (§1) |
| Functional Depth | 89% | §5.4 체크리스트 누락 3, §6.3 경계 1 누락, FR-17 부분 (§2) |
| API Contract | 96% | 9/9 라우트 3-way 일치, `max_pages` 422·MCP select 차이 (§3) |
| Runtime | 95% | 백엔드 214 passed(L1/L3/계약), 프론트 157 passed(L2), 실 LLM 스모크 통과(module-6); Design §8.4 #2 degraded E2E 전용 테스트 없음(단위만) |
| **Overall** | **94%** | 0.15×97 + 0.25×89 + 0.25×96 + 0.35×95 = 94.0 |

런타임 실행 기록 (2026-08-22):
- `pytest tests/domain/blueprint tests/application/blueprint tests/infrastructure/blueprint tests/api/test_admin_blueprint_router.py tests/api/test_blueprint_wiring.py tests/api/test_blueprint_e2e.py tests/application/agent_builder/test_workflow_compiler_presentation.py tests/application/agent_builder/test_presentation_generator_binding.py tests/domain/agent_builder/test_tool_registry.py tests/infrastructure/document_extractor/test_conversion_adapter.py tests/infrastructure/multimodal/test_vision_adapters.py tests/db/test_migration_ddl_comments.py` → **214 passed**
- `vitest run src/pages/AdminBlueprintsPage src/components/agent-builder/PresentationGeneratorConfigPanel.test.tsx src/utils src/constants/adminNav.test.ts` → **157 passed**
- 전체 회귀(module-7 종료 시점): 백엔드 58 failed = baseline(신규 0), 프론트 9 failed = baseline 4파일(신규 0), tsc 199 = baseline, ruff/ESLint 신규 파일 0
- 실 LLM 스모크 `pytest -m llm tests/api/test_blueprint_smoke.py` → 1 passed (분류 5/5, 4장, 토큰 4,239)

---

## 1. Structural Match — 97%

### Design §2.1 / §9.1 backend files

| Design item | Implementation | ✓ |
|---|---|:-:|
| domain/blueprint value_objects·schemas·policies·interfaces·errors·tool_config | `src/domain/blueprint/{value_objects,schemas,policies,interfaces,errors,tool_config}.py` | ✅ |
| (v0.4) `domain/blueprint/serialization.py` | exists — used by repository:19 and schemas/blueprint.py:18 | ✅ |
| application/blueprint registries·extraction·admin·generation | all 4 present | ✅ |
| infra extractors/pdf_style_extractor, pptx_style_extractor | present | ✅ |
| infra vision/page_classifier, llm/{synthesizer,slide_planner,slot_writer}, prompts, prompts_generation | present (+ `llm/structured.py`, v0.5) | ✅ |
| infra renderer/{pptx_renderer,chart_builder}, fonts, models, repository | present | ✅ |
| interfaces/schemas/blueprint.py, api/routes/admin_blueprint_router.py, api/blueprint_di.py | present | ✅ |
| `main.py` +`wire_blueprint` 1회 | `src/api/main.py:5296-5302` (1 call) | ✅ |
| WorkflowCompiler `presentation_generator`/`blueprint_repository` args | `main.py:2686-2687`; `workflow_compiler.py:149-150,180-181` | ✅ |
| `config.py` blueprint_font_dir / blueprint_default_font | `src/config.py:158-159`, consumed only in `blueprint_di.py:127-129` | ✅ |
| tool_registry `presentation_generator` | `src/domain/agent_builder/tool_registry.py:65-74` | ✅ |
| binding / create / update / compiler node | `presentation_generator_binding.py:18`; `create_agent_use_case.py:172`; `update_agent_use_case.py:171`; `workflow_compiler.py:973` | ✅ |
| `describe_with` (D8) | `base_vision_adapter.py:78-85` | ✅ |
| `to_pdf_from_pptx` | `document_conversion_adapter.py:89-99` | ✅ |

### Design §3.3 DB

| Item | Impl | ✓ |
|---|---|:-:|
| `document_blueprint` (11 cols, idx status) | `V066__create_document_blueprint.sql:7-20` + `models.py:18-57` | ✅ |
| `document_blueprint_asset` (11 cols, idx bp) | `V066:22-35` + `models.py:60-91` | ✅ |
| `DATETIME(6)` per Design | impl uses `DATETIME` (no fractional) | ⚠️ deviation |

### Design §4.1 endpoints — 9/9 routes registered

`admin_blueprint_router.py:75,104,120,130,139,151,168,180,194` → extract, create, list, fonts, get, put, delete, asset, options. `blueprint_di.py:152-153` includes both routers.

### Design §5.3 frontend components

| Design | Impl | ✓ |
|---|---|:-:|
| AdminBlueprintsPage/index.tsx | present | ✅ |
| BlueprintUploadStep.tsx | present | ✅ |
| BlueprintStyleTab / PatternsTab / NarrativeTab / FontMappingTab / AssetsTab (5 files) | consolidated into `BlueprintTabs.tsx` (internal components `StyleTab:85`, `PatternsTab:180`, `NarrativeTab:257`, `FontMappingTab:358`, `AssetsTab:406`, `WarningsTab:458`) + `BlueprintEditor.tsx`, `BlueprintList.tsx` | ⚠️ file-layout deviation, behavior present |
| PresentationGeneratorConfigPanel | `components/agent-builder/` (+ Modal) | ✅ |
| types/blueprint.ts (`PATTERN_KINDS`/`SLOT_KINDS`/labels/`BLUEPRINT_LIMITS`) | `types/blueprint.ts:4,18,29,59` | ✅ |
| blueprintService.ts, useBlueprints.ts | present; **`useBlueprintExtract.ts` not a separate file** — `useExtractBlueprint` lives in `useBlueprints.ts:30` | ⚠️ minor |
| utils/blueprintValidators.ts | present | ✅ |
| adminNav / App route / api consts / queryKeys | `adminNav.ts:89`, `App.tsx:26,104`, `api.ts:141-148`, `queryKeys.ts:101-108` | ✅ |

**Deductions**: −2 (component file split), −1 (DATETIME precision).

---

## 2. Functional Depth — 89%

### §5.4 Page UI Checklist

**/admin/blueprints (목록) — 4/4 ✅**
Button `index.tsx:25-31`; table columns 이름/원본/페이지/패턴수/상태/수정일 `BlueprintList.tsx:45-51`; row actions + ConfirmDialog `BlueprintList.tsx:78-112`; empty `:32-38`, skeleton `:16-24`, error `error.message` `:25-31`.

**/admin/blueprints (추출/편집) — 10.5/13**

| Checklist item | Evidence | ✓ |
|---|---|:-:|
| file input accept .pdf,.pptx + 30MB 클라 경고 | `BlueprintUploadStep.tsx:40-45`, `blueprintValidators.ts:48` | ✅ |
| 추출 시작 LoadingButton + 진행 텍스트 | `BlueprintUploadStep.tsx:47-55` | ✅ |
| 스타일: 팔레트 color+hex | `BlueprintTabs.tsx:94-111` | ✅ |
| 스타일: 크기 4 number | `BlueprintTabs.tsx:117-131` | ✅ |
| 스타일: 표 스타일 header_bg, **header_text, border**, zebra | only `header_bg` (`:136-141`) + `zebra` (`:143-150`) — **header_text/border 편집 UI 없음** | ❌ |
| 스타일: 헤더/푸터 **logo 에셋 select**, page_number_format, footer_text | `:154-171` has only format+text — **logo_asset_id select 없음** | ❌ |
| 패턴: 썸네일·kind select 10종·슬롯 목록·제외·unknown 배지 | `:214-247` (kind select `:221-232`, slots `:233-240`, 제외 `:241-247`, 배지 `:208-212`) | ✅ |
| 서사: role/multi-select/guidance/추가·삭제·이동, tone/language | `:272-351` | ✅ |
| 폰트 매핑 select + 미설치 경고 | `:368-396` | ✅ |
| 에셋: 썸네일·kind select·채택 checkbox | `:415-451` | ✅ |
| 경고 탭 | `:458-467` | ✅ |
| 이름(≤100)·설명(≤500) | `BlueprintEditor.tsx:135-153` | ✅ |
| 저장 LoadingButton → 목록 이동·무효화 | `BlueprintEditor.tsx:169-176`; invalidate `useBlueprints.ts:40,50-51` | ✅ |

**에이전트 빌더 워커 설정 — 4.5/5**
blueprint select + 없음 안내 링크 `PresentationGeneratorConfigPanel.tsx:39-66`; output_format radio `:72-83`; max_slides number 1..60 `:106-114`; 인라인 오류 `:117-121`; 저장 직렬화 `AgentBuilderPage/index.tsx:286,345` → `buildPresentationGeneratorRequest`. **MCP 도구는 Design이 "Select"라 했으나 free-text `<input>`** (`:92-98`) — 반쪽.

**Page UI subtotal: 19/22 = 86%**

### §2.2 Data-flow steps — 15/15 ✅

추출: registry resolve `extraction_use_case.py:106` → extract `:109` → RepeatAsset `:230` → Palette/SizeHierarchy `_style_tokens:256-257` → classify `_classify_all:153` → synthesize `_narrative:196` → assemble+warnings `:222-252` → thumbnails `:132`.
생성: repo.get + inactive 노옵 `workflow_compiler.py:1015-1020` → `_split_fill_context` `:1021` → planner+SlidePlanValidationPolicy `generation_use_case.py:159-192` → SlotWriter+Semaphore `:196-215` → SlotContentPolicy `:239` → render `:132` → AttachmentStore `:149-155` → pdf `:245-267` → AIMessage `workflow_compiler.py:1381-1391`.

### §6.3 Degraded/failure boundary — 6/7

| Row | Impl | ✓ |
|---|---|:-:|
| 페이지 1장 분류 실패 → unknown+warning | `extraction_use_case.py:183-191` | ✅ |
| narrative 실패 → 기본 서사+warning | `:204-218` | ✅ |
| 폰트 미설치 → 기본+warning | `fonts.py:82-86` | ✅ |
| plan 검증 실패 → 제외+warning | `policies.py:243-251`, `generation_use_case.py:178-192` | ✅ |
| **슬롯 1개 검증 실패 → 빈 슬롯+warning** | `SlotContentPolicy` covers length/kind, but VO construction happens **before** the policy and **outside** the try — malformed chart/table raises `ValueError` and aborts the whole deck | ❌ |
| PDF 변환 실패/미설정 → PPTX만+warning | `generation_use_case.py:254-266` | ✅ |
| 미설정/미지원/손상/inactive → 예외·409·415 | router `:84-100`, `errors.py`, compiler `:1016` | ✅ |

### Plan FR-01…FR-20

✅ FR-01,03,04,05,06,08,10,11,12,13,14,16,18,19,20 (15)
⚠️ FR-02 (PyMuPDF 직접 사용, `PdfPyMuPdfExtractor` 미재사용 — Design v0.2 §2.3에서 의도적 변경으로 기록됨 → 사실상 충족)
⚠️ FR-07 (제안·경고 O `fonts.py:76-87`; 그러나 `FontCatalogPort`에 `propose_mapping` 미선언 — 포트 계약 누수)
⚠️ FR-09 (에셋 저장 O, 관리자 채택 O — 단 Design D2로 `AttachmentStore` 대신 LONGBLOB, 의도적)
⚠️ FR-15 (PPTX 저장·PDF MCP·degraded 전부 O — `GenerateResult 동형 DTO`는 `PresentationResult`로 별도 정의, 의도적)
⚠️ FR-17 (구조화 로그 O `generation_use_case.py:274-287`, `extraction_use_case.py:137-149`; **UsageCallback → ai_run 기록 미배선** — 노드가 `callbacks=` 를 전달하지 않음 `workflow_compiler.py:1025-1035`. `document_generator` 노드와 동일한 한계)

**FR subtotal ≈ 18.0/20 = 90%**

**Functional Depth = (86 + 100 + 86 + 90)/4 ≈ 89%**

---

## 3. API Contract (3-way) — 96%

Design §4.1/§4.2 ↔ `admin_blueprint_router.py` ↔ `blueprintService.ts` + `types/blueprint.ts`

| # | Endpoint | Design | Server | Client | Contract |
|---|---|:-:|:-:|:-:|:-:|
| 1 | POST /api/v1/admin/blueprints/extract | ✅ | `:75-101` | `blueprintService.ts:15-29` (`ADMIN_BLUEPRINTS_EXTRACT`, multipart, `max_pages`) | **PASS** |
| 2 | POST /api/v1/admin/blueprints (201) | ✅ | `:104-117` | `:45-51`, `BlueprintCreateRequest{draft,assets[]}` = `blueprint.py:129-131` | **PASS** |
| 3 | GET /api/v1/admin/blueprints | ✅ | `:120-127` `list[BlueprintSummary]` | `:31-36` `BlueprintSummary[]`, `include_inactive` param | **PASS** |
| 4 | GET /{id} | ✅ | `:139-148` | `:38-43` | **PASS** |
| 5 | PUT /{id} | ✅ | `:151-165` `{draft}` | `:53-59` `BlueprintUpdateRequest{draft}` | **PASS** |
| 6 | DELETE /{id} (soft) | ✅ | `:168-177` (200 + full blueprint) | `:61-66` returns `BlueprintResponse` | **PASS** |
| 7 | GET /{id}/assets/{asset_id} | ✅ | `:180-191` raw bytes | endpoint const only (`api.ts:146`), no service method — assets rendered from inline `thumbnail_b64` | **PASS (unused-by-design)** |
| 8 | GET /admin/blueprints/fonts | ✅ | `:130-136` `{installed,default}` | `:68-71` `FontsResponse{installed,default}` | **PASS** |
| 9 | GET /api/v1/blueprints/options (login user) | ✅ | `:194-202` `get_current_user` | `:74-79` `{items:[{id,name}]}` | **PASS** |

**Route-ordering check**: `/fonts` (`:130`) is declared before `/{blueprint_id}` (`:139`) — no shadowing. ✅

**Field-name check**: `BlueprintPayload` (`schemas/blueprint.py:97-112`) fields id/name/description/source_kind/page_count/schema_version/style/patterns/narrative/assets/font_mapping/warnings/status ≡ `BlueprintDraft` (`types/blueprint.ts:144-158`) exactly. `AssetPreview.data_b64` (server `:186`) ↔ client `:178` ↔ round-trip on POST (`BlueprintEditor.tsx:68,83-86`) — Design v0.7 gap-closure honored. ✅

**Error codes §6.1**: VALIDATION_ERROR 400 (`:72,116,164`), BLUEPRINT_NOT_FOUND 404 (`:148,162,177,190`), MULTIMODAL_DISABLED/NOT_CONFIGURED 409 (`:95-98`), PAYLOAD_TOO_LARGE 413 (`:88`), UNSUPPORTED_MEDIA 415 (`:85,94`), UNSUPPORTED_VISION_PROVIDER 500 (`:100`). Shape `{detail:{code,message}}` = `_error()` `:62-65` = Design §6.2. ✅
**Gap**: Design §6.1 row "422→400 매핑(멀티모달 동형)" — request bodies are typed `body: dict` and hand-validated via `_validation()` (`:68-72`), so 422 never fires for those; but `extract`'s `max_pages: int = Query(..., ge=1, le=200)` still emits FastAPI **422**, not 400. Minor contract drift.

**presentation_generator field contract**
`types/presentationGenerator.ts:6-11` `{blueprint_id, output_format, mcp_pptx_to_pdf_tool_id, max_slides}` ↔ `agent_builder/schemas.py:45-54` `PresentationGeneratorConfigRequest` (identical names/defaults `pptx`/`15`) ↔ `domain/blueprint/tool_config.py:16-20`. Attach points `schemas.py:115` (Create) / `:166` (Update) ↔ client `AgentBuilderPage/index.tsx:286,345`, type `types/agentBuilder.ts:72,116`. Prefill `agentDetailMapping.ts:81-82` reads `tool_config` by `tool_id === 'presentation_generator'` (server-side id, matches binding `:15,30`). Client validation `utils/presentationGenerator.ts:39-45` mirrors server `tool_config.py:22-38` (mcp_ prefix, 1..60). **PASS**

**Deductions**: −4 (422→400 mapping on `max_pages`).

---

## 4. Gap List

| # | Sev | Conf | Location | Issue | Suggested fix |
|---|---|:-:|---|---|---|
| G1 | **Critical** | 90% | `src/application/blueprint/generation_use_case.py:238` (+`value_objects.py:316-323,331-336`) | `_slot_content()` builds `ChartSpec`/`TableSpec` VOs **outside** the `try` and **before** `SlotContentPolicy`. LLM output with `len(series.values) != len(categories)` or ragged table rows raises `ValueError`, propagates through `asyncio.gather` → entire presentation fails. Violates Design §6.3 "슬롯 1개 내용 검증 실패 → 빈 슬롯 + warning". | Wrap per-slot conversion: `try: contents.append(_slot_content(s)) except ValueError as e: warnings.append(f"slot '{s.slot_id}': {e}")` and keep the slide. Add a unit test with a mismatched-length chart draft. |
| G2 | Important | 95% | `BlueprintTabs.tsx:132-151` | 표 스타일 편집에서 `header_text`·`border` 입력 누락 (Design §5.4). 추출 기본값(`#FFFFFF`/`#CCCCCC`, `extraction_use_case.py:264-268`)이 관리자에게 고정된다. | Add two hex inputs next to `header_bg`, patching `table_style`. |
| G3 | Important | 95% | `BlueprintTabs.tsx:152-172` | 헤더/푸터 **logo 에셋 select** 누락 (Design §5.4). `header_footer.logo_asset_id`는 추출 시 자동 선택만 되고 편집 불가 — 렌더러가 이 값을 그대로 씀(`pptx_renderer.py:136`). | Add `<select>` over `draft.assets.filter(a => a.kind==='logo'\|\|a.adopted)` + "없음" 옵션, patch `header_footer.logo_asset_id`. |
| G4 | Important | 85% | `src/domain/blueprint/interfaces.py:87-92` vs `extraction_use_case.py:231` | `FontCatalogPort`는 `installed/default_font/suggest`만 선언하는데 UseCase는 `propose_mapping()`을 호출 — Protocol 계약 누수(타입체크·대체 구현 불가). | Declare `def propose_mapping(self, source_fonts: tuple[str, ...]) -> tuple[dict[str,str], tuple[str,...]]: ...` on the Port. |
| G5 | Important | 80% | `workflow_compiler.py:1025-1035` | Plan FR-17의 "UsageCallback로 ai_run 사용량 기록"이 미배선 — `generate(..., callbacks=…)` 미전달(파라미터는 존재 `generation_use_case.py:117`). 사용량은 로그·`PresentationResult.usage`에만 남음. | Thread `callback`/`run_id` into `_create_presentation_generator_node` like the tool-wrapping path (`:417-432`), or record the deviation in Design (문서생성기와 동일 한계). |
| G6 | Minor | 90% | `PresentationGeneratorConfigPanel.tsx:92-98` | Design §5.1/§5.4는 MCP 도구 **select**를 요구하나 free-text input. 오타 시 런타임 degraded로만 드러남. | Reuse the MCP tool list hook used by `DocumentGeneratorConfigPanel`, fall back to text input if the list is empty. |
| G7 | Minor | 85% | `admin_blueprint_router.py:78` | `max_pages` 범위 위반이 FastAPI 기본 **422**로 나감 — Design §6.1 "422→400 매핑". | Validate `max_pages` in the handler and raise `_error("VALIDATION_ERROR", …, 400)`, or add a router-scoped `RequestValidationError` handler. |
| G8 | Minor | 90% | `V066__create_document_blueprint.sql:17-18`, `models.py:52-57` | Design §3.3은 `DATETIME(6)`; 구현은 `DATETIME`(초 단위). 동일 초 내 `updated_at` 정렬(`repository.py:92-94`)·프론트 edit 동기화 키(`BlueprintEditor.tsx:51`)가 흔들릴 수 있음. | Either migrate to `DATETIME(6)` or update Design §3.3 to match code. |
| G9 | Minor | 80% | `BlueprintTabs.tsx:241-247` | Design은 "패턴 제외 **토글**", 구현은 비가역 삭제(narrative 참조도 함께 제거 `:190-196`). 실수 시 복구 불가. | Make it a toggle (`excluded` local flag) filtered at save time, or add an undo. |
| G10 | Minor | 75% | Design §5.3 vs `pages/AdminBlueprintsPage/*` | 탭 5개 파일 대신 `BlueprintTabs.tsx` 단일 파일(469줄), `useBlueprintExtract.ts` 미분리. | Update Design §5.3 to the actual file layout (code is truth). |

---

## 5. Plan §4.1 Definition of Done / Success Criteria

| # | Criterion | Status | Evidence |
|---|---|:-:|---|
| SC-1 | FR-01~20 구현 + 각 항목 대응 테스트(TDD) | ⚠️ Partial | 20/20 구현(FR-17 부분). 테스트 21개 파일: `tests/domain/blueprint/{test_value_objects,test_schemas,test_policies,test_tool_config,test_serialization,test_layer_contract}.py`, `tests/application/blueprint/*`(5), `tests/infrastructure/blueprint/*`(7), `tests/api/test_admin_blueprint_router.py`(11 tests) |
| SC-2 | 합성 샘플 추출→편집→저장→워커→PPTX E2E (fake LLM/vision) | ✅ Met | `tests/api/test_blueprint_e2e.py:298 test_l3_extract_save_generate_roundtrip`; fixtures `tests/fixtures/blueprint_samples.py` |
| SC-3 | 실 LLM 스모크 1회 | ✅ Met | `tests/api/test_blueprint_smoke.py:104 test_real_openai_extract_then_generate` (Design v0.6: 분류 5/5·4장·4,239토큰 기록) |
| SC-4 | 생성 PPTX 검증: 순서·팔레트·폰트·네이티브 차트 | ✅ Met | 렌더러 `pptx_renderer.py:52-57`(순서), `:216`(palette text), `ctx.font():92-94`(font_mapping), `chart_builder.py:41`(native `add_chart`); 검증 `tests/infrastructure/blueprint/test_pptx_renderer.py` + E2E |
| SC-5 | 관리자 화면 Vitest + adminNav 테스트 갱신 | ✅ Met | `AdminBlueprintsPage/index.test.tsx` (10 tests, L2 #1~#8), `PresentationGeneratorConfigPanel.test.tsx`, `utils/blueprintValidators.test.ts`, `constants/adminNav.test.ts` (modified; route `adminNav.ts:89`) |
| SC-6 | verify-architecture / logging / tdd 통과, 회귀 0 | ⚠️ Unverified | AST 계약 테스트 존재 (`tests/domain/blueprint/test_layer_contract.py`, `tests/application/blueprint/test_layer_contract.py`); logger 사용 확인(print 0); **실행 결과는 정적 분석 범위 밖** |
| SC-7 (Q) | 신규 모듈 커버리지 ≥80% | ⚠️ Unverified | 테스트 밀도는 높으나 커버리지 측정 미실행 |
| SC-8 (Q) | ruff/ESLint 0, tsc 0 | ⚠️ Unverified | 정적 판독상 위반 징후 없음 |
| SC-9 (Q) | 함수 40줄·if 2단계·DDL COMMENT | ✅ Met | V066 전 컬럼 COMMENT + 테이블 COMMENT, 콤마 없음; 최장 함수 `_render_slot` 36줄 |

**Success rate: 5 Met / 4 Partial-or-Unverified / 0 Not Met.**

---

## 6. Decision Record D1–D8 Compliance

| # | Decision | Status | Evidence |
|---|---|:-:|---|
| D1 | 좌표 0..1 비율 저장, EMU 변환은 렌더러만 | ✅ | `RelBox.__post_init__` `value_objects.py:70-78`; `_rel()` `pdf_style_extractor.py:29-34`; 유일한 EMU 변환 `_Ctx.emu()` `pptx_renderer.py:84-90` (`_EMU_PER_INCH:32`) |
| D2 | 에셋 LONGBLOB (AttachmentStore 미사용) | ✅ | `models.py:15,85-87`; `V066:32`; 저장 경로 `repository.py:116-130` — blueprint 에셋에 `AttachmentStore` 미사용(생성 산출물에만 사용 `generation_use_case.py:149-155`) |
| D3 | 비전 모델은 multimodal_setting 재사용, 새 설정 키 0 | ✅ | `blueprint_di.py:59-75` (`_mm.resolve_vision_model`/`build_adapter`); 동시성·타임아웃 재사용 `extraction_use_case.py:157,181,207`. 새 키는 폰트 2개뿐(§8.3 허용) |
| D4 | PPTX는 렌더 없이 도형 통계 분류, PDF는 렌더 사용 | ✅ | `_heuristic_pattern/_heuristic_kind` `extraction_use_case.py:370-408` (분기: `render_png is None` `:161-164`); PDF 렌더 `pdf_style_extractor.py:86`; `PageStats.charts` `value_objects.py:118` |
| D5 | 슬롯 작성 슬라이드당 LLM 1회, 동시 | ✅ | `_write_all` Semaphore + gather `generation_use_case.py:204-215`; 부분 실패 격리 `:231-237` (단 G1의 예외 경로 존재) |
| D6 | 차트 3종(bar/line/pie) + 표 | ✅ | `_TYPES` `chart_builder.py:16-20`; `ChartType` Literal `value_objects.py:22`; `ChartTypeLiteral` `schemas.py:32`; 프론트 미노출(생성 측 전용) |
| D7 | 워커 tool_config 소프트 참조(blueprint_id), 영속 엔티티 없음 | ✅ | `presentation_generator_binding.py:39-45` (`asdict` 주입만); FK 없음(`V066`); 런타임 `find_by_id` + inactive 안내 `workflow_compiler.py:1015-1020` |
| D8 | `describe_with` 1개 추가로 어댑터 재사용 | ✅ | `base_vision_adapter.py:78-85`; `describe()`가 `describe_with`로 위임 `:76` (기존 동작 불변); 분류 프롬프트 분리 `infrastructure/blueprint/prompts.py` |

**8/8 followed.**

---

## 7. Plan §2.2 Out-of-Scope — 위반 0

| Out-of-scope item | Verified not implemented |
|---|---|
| 픽셀 동일 레이아웃 / 폰트 파일 복제·내장 | `fonts.py`는 이름 매핑만 (`propose_mapping:76-87`), 폰트 임베딩 API 호출 없음 |
| DOCX/PDF 직접 출력, 기존 DocumentGenerator에 blueprint 적용 | 렌더러는 PPTX 단일 (`pptx_renderer.py`), PDF는 MCP 변환 경로만 (`generation_use_case.py:260`); `document_generator` 경로에 blueprint 참조 0 |
| 다중 샘플 병합 / 버전 관리 / 승인 워크플로우 | `extract`는 단일 `UploadFile` (`router:77`); status는 active/inactive 2값 (`value_objects.py:20`), 버전 테이블 없음 |
| .potx / 애니메이션 / 스마트아트 | python-pptx 사용 API는 textbox/table/chart/picture만 |
| 스캔 PDF 정밀 추출 | `has_text` 플래그만 기록 (`pdf_style_extractor.py:85`), OCR 없음 |
| 원본 파일 장기 보관 | `extract`는 `data`를 반환값에 담지 않음; 저장은 에셋 바이트만 (`admin_use_case.py:118-133`) |
| 비관리자 blueprint 등록 | 모든 쓰기 라우트 `require_role("admin")` (`:79,107,123,132,142,155,171,184`); `options`만 `get_current_user` (`:196`) — Design §7 일치 |

---

## 8. Runtime Verification Plan (existing coverage per Design §8)

### L1 — 단위/계약 + API (pytest)

| Design §8.2 # | Scenario | Covering test file |
|---|---|---|
| 1,2 | 합성 PDF/PPTX extract → patterns·palette·fonts | `tests/infrastructure/blueprint/test_pdf_style_extractor.py`, `test_pptx_style_extractor.py`, `tests/application/blueprint/test_extraction_use_case.py`, `tests/api/test_admin_blueprint_router.py:132` |
| 3,4,5 | .docx 415 / 손상 415 / 31MB 413 | `test_admin_blueprint_router.py:159 (parametrized), :168` |
| 6 | 비전 미설정 409 | `test_admin_blueprint_router.py:159` |
| 7 | 1페이지 타임아웃 → unknown, failed=1 | `tests/application/blueprint/test_extraction_use_case.py` |
| 8,9 | 저장 201 / box·중복·narrative 400 | `test_admin_blueprint_router.py:185, :208, :217` |
| 10,11 | PUT 갱신 / DELETE soft | `test_admin_blueprint_router.py:238, :249` |
| 12 | fonts 200 | `test_admin_blueprint_router.py:257` |
| 13 | 비관리자 403 / options 허용 | `test_admin_blueprint_router.py:268` |
| 14,15,16 | 워커 노드 inactive·정상·PDF 실패 | `tests/application/agent_builder/test_workflow_compiler_presentation.py:150,166,180,219` |
| — | 도메인 계약·정책·직렬화·레이어 | `tests/domain/blueprint/{test_value_objects,test_schemas,test_policies,test_tool_config,test_serialization,test_layer_contract}.py`, `tests/application/blueprint/test_layer_contract.py` |
| — | 렌더러 재오픈·차트 | `tests/infrastructure/blueprint/test_pptx_renderer.py` |
| — | repository·fonts·프롬프트/LLM | `test_repository.py`, `test_fonts.py`, `test_prompts_and_llm.py`, `test_generation_llm.py` |
| — | 라우트 등록·인증 가드 | `tests/api/test_blueprint_wiring.py:13` |
| — | 워커 바인딩 | `tests/application/agent_builder/test_presentation_generator_binding.py` |

**Command**: `pytest tests/domain/blueprint tests/application/blueprint tests/infrastructure/blueprint tests/api/test_admin_blueprint_router.py tests/api/test_blueprint_wiring.py tests/application/agent_builder/test_workflow_compiler_presentation.py tests/application/agent_builder/test_presentation_generator_binding.py -q`

### L2 — UI (Vitest + RTL + MSW)

| Design §8.3 # | Scenario | Covering test |
|---|---|---|
| 1 | 목록 로드·배지 | `AdminBlueprintsPage/index.test.tsx:38` |
| — | 비활성화 다이얼로그 → DELETE | `:48` |
| — | 목록 오류 alert | `:63` |
| 2 | 파일 선택 + 추출 (multipart, 진행 → 탭) | `:75 (docx 차단)`, `:86` |
| 3,4,5,6 | 스타일 hex / 패턴 kind / 서사 추가 / 폰트 select → payload | `:96` (4 items in one test) |
| 7 | 이름 누락 → 인라인, 요청 없음 | `:143` |
| 8 | 저장 성공 → 이동·무효화 | `:169` (edit/PUT), `:96` (create/POST) |
| 9,10 | ConfigPanel 없음 안내 / pdf select·범위 | `components/agent-builder/PresentationGeneratorConfigPanel.test.tsx` |
| — | 순수 변환·검증 | `utils/blueprintValidators.test.ts` |
| — | nav 목록 | `constants/adminNav.test.ts` |

**Command**: `npm run test -- src/pages/AdminBlueprintsPage src/components/agent-builder/PresentationGeneratorConfigPanel.test.tsx src/utils/blueprintValidators.test.ts src/constants/adminNav.test.ts`
**Gap**: Design §8.3 #5는 "섹션 추가·**순서 이동**"인데 순서 이동(`move()` `BlueprintTabs.tsx:263-269`) 단독 검증 없음 — Minor.

### L3 — E2E (백엔드 통합) + Smoke

| Design §8.4 # | Scenario | Covering test |
|---|---|---|
| 1 | 추출→저장→워커 생성→PPTX 재오픈 | `tests/api/test_blueprint_e2e.py:298 test_l3_extract_save_generate_roundtrip` |
| 2 | **degraded** (plan pattern_id 오류 + 슬롯 초과) | ❌ **전용 E2E 없음** — 단위 레벨만 (`tests/application/blueprint/test_generation_use_case.py:285, :308`). Design §8.4 #2 미충족 |
| 3 | 실 LLM 스모크 `-m llm` | `tests/api/test_blueprint_smoke.py:104` |

**Command**: `pytest tests/api/test_blueprint_e2e.py -q` / `pytest -m llm tests/api/test_blueprint_smoke.py -q`

---

## 9. Recommended Actions

**즉시 (Critical/Important)**
1. **G1** — `_slot_content()` per-slot try/except (Design §6.3 위반, 전체 생성 실패 유발). 회귀 테스트: 길이 불일치 `ChartDraft` → 슬라이드 유지 + warning 1건.
2. **G2·G3** — 스타일 탭에 `header_text`/`border` 입력, 헤더/푸터에 logo 에셋 select 추가 (§5.4 체크리스트 3항).
3. **G4** — `FontCatalogPort.propose_mapping` 선언 추가.
4. **L3 #2** — degraded E2E 시나리오 추가 (Design §8.4 명시 항목).

**문서 갱신 (코드가 진실)**
- Design §5.3 → 실제 파일 레이아웃(`BlueprintTabs.tsx` 단일 파일, `useBlueprintExtract.ts` 미분리) 반영 (G10).
- Design §3.3 `DATETIME(6)` ↔ 코드 `DATETIME` 정합 (G8).
- Design §5.1/§5.4 MCP 도구 "select" ↔ 구현 text input (G6) — UI 개선 또는 문서 수정 택1.
- Plan FR-17 UsageCallback 항목 (G5) — 배선하거나 "문서생성기와 동일 한계"로 명시.

---

## 10. Act-1 결과 (2026-08-22, Checkpoint 5: "지금 모두 수정")

| # | Sev | 조치 | 검증 |
|---|---|---|---|
| G1 | Critical | `generation_use_case._convert_slots()` — Draft→VO 변환 실패(ValueError)를 슬롯 제외 + warning 으로 격리 (§6.3) | `test_invalid_chart_shape_from_llm_is_degraded_not_fatal` + L3 `test_l3_degraded_plan_and_slots_still_produce_deck` |
| G2 | Important | 스타일 탭 표 `header_text`·`border` hex 입력 추가 | `index.test.tsx` Act-1 케이스 |
| G3 | Important | 헤더/푸터 로고 에셋 select(채택 에셋만 + '로고 없음') | 〃 |
| G4 | Important | `FontCatalogPort.propose_mapping` 선언 | 계약 테스트 통과 |
| G5 | Important | 워커 노드 → `generate(callbacks=[UsageCallback])` 전달 (FR-17) | `test_usage_callback_is_forwarded_to_generator` |
| G6 | Minor | **설계 갱신** — 문서생성기 패널도 MCP id 는 text input 이라 동형 유지 (gap-detector 전제 오류) | Design v0.8 §5.4 |
| G7 | Minor | `max_pages` 범위 위반 → 400 VALIDATION_ERROR | `test_extract_max_pages_out_of_range_is_400_not_422` |
| G8 | Minor | **설계 갱신** — `DATETIME` (V065 관례, 코드가 진실) | Design v0.8 §3.3 |
| G9 | Minor | 패턴 제외를 가역 토글로 (저장 시 `excludePatterns` 적용·서사 참조 정리) | `excludePatterns` 단위 + 페이지 테스트 |
| G10 | Minor | **설계 갱신** — 탭 단일 파일·`useBlueprints` 통합 | Design v0.8 §5.3 |
| §8.3 #5 | Runtime | 서사 섹션 순서 이동 UI 검증 추가 | 페이지 테스트 |
| §8.4 #2 | Runtime | degraded E2E 전용 테스트 추가 | `tests/api/test_blueprint_e2e.py` |

**Act-1 후 게이트**: 백엔드 7842 passed / 58 failed(= baseline, 신규 0) · 프론트 1116 passed / 9 failed(= baseline 4파일, 신규 0) · ruff/ESLint 기능 파일 0 · tsc 199(= baseline).

**재산정 Match Rate**: Structural 97 → 97, Functional 89 → 97(§5.4 3건·§6.3 1건·FR-17 해소), Contract 96 → 99(422→400; MCP 입력은 설계 갱신), Runtime 95 → 99(§8.4 #2·§8.3 #5 보강).
**Overall = 0.15×97 + 0.25×97 + 0.25×99 + 0.35×99 ≈ 98%**

잔여(이월): 커버리지 수치 측정(SC-7), 관리자 화면 실 브라우저 E2E, 로컬 vLLM/Ollama 스모크.
