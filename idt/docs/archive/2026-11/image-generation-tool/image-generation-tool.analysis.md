# image-generation-tool Gap Analysis

> **Summary**: 설계(Design v0.2)와 구현(idt + idt_front)을 정적으로 대조했다. 백엔드 생성 코어(도메인·레지스트리·OpenAI 어댑터·UseCase·원장·노드·서브 그래프·답변 후처리)와 프론트(인증 이미지 렌더·설정 패널·관리자 폼·종류 필터)는 설계와 거의 같다. 초기 분석(89%)에서 나온 Important 4건(저장 오류 상태 코드, `MODEL_KIND_MISMATCH` 코드, 다운로드 Content-Type, 수정 시 불필요한 재검증)은 Act-1에서 모두 수정해 **95%**가 됐다. 런타임 검증(수동 E2E·L1~L3)은 하지 않았다.
>
> **Act-1 (2026-11-02) 수정 내역**
> | Gap | 수정 | 테스트 |
> |---|---|---|
> | G-I1 | `agent_builder_router.save_error_http_exception()` 신설 — `IMAGE_MODEL_INVALID`/`IMAGE_CONFIG_INVALID`/`MODEL_KIND_MISMATCH` 접두 메시지는 "찾을 수 없" 문구가 있어도 422. 생성·수정·스킬 부착 3곳이 같은 규칙 사용 | `tests/api/test_agent_builder_save_errors.py` 5건 |
> | G-I2 | `LlmModelPolicy.require_chat_model` 메시지에 `MODEL_KIND_MISMATCH: ` 접두어. 프론트 `IMAGE_GENERATION_ERROR_CODES.MODEL_KIND_MISMATCH` + 안내문 매핑 | `test_model_kind_policy` 접두어 단언, `utils/imageGeneration.test.ts` |
> | G-I3 | 다운로드 `_MEDIA_TYPES`에 `.png/.jpg/.jpeg/.webp`. `ImageGenerationPolicy.output_filename(now, mime=)`로 확장자를 실제 mime에 맞춤, UseCase가 `image.mime` 전달 | `test_document_extractor_router` png 케이스, `TestOutputFilename.test_extension_follows_mime` |
> | G-I4 | `UpdateAgentUseCase`는 `request.image_generation`이 있을 때만 이미지 모델을 재검증 | `TestUpdateAgentImageGenerationRevalidation` 2건 |
>
> Act-1 후 재채점: Structural 96 (HTTP 상태 테스트 추가) / Functional 96 (UI #8 → 1.0, 백엔드 로직 G-I4 해소 ≈ 92) / Contract 95 (#4 0.9, #5 0.9, #6 1.0 — 오류 코드는 `{code,message}` 객체가 아닌 접두어 문자열 계약으로 유지, 설계 §6.2 정정 대상). Overall = 96×0.2 + 96×0.4 + 95×0.4 = **95.6 → 95%**. 회귀: api·agent_builder·llm_model·multimodal·domain 5,826건 중 상시 실패 24건 외 실패 0.
>
> **Author**: gap-detector (bkit) 초안 + 메인 세션 보정(프론트 unverified 항목을 module-4 구현·테스트 사실로 재채점)
> **Created**: 2026-11-02
> **Status**: Draft
> **Plan**: [image-generation-tool.plan.md](../01-plan/features/image-generation-tool.plan.md)
> **Design**: [image-generation-tool.design.md](../02-design/features/image-generation-tool.design.md) (v0.2)
> **PRD**: 없음

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트가 이미지를 만들어 낼 도구가 없다. 생성 API 호출 코드가 전무하다. |
| **WHO** | P2 에이전트 소유자(도구 부착·모델 선택), P1 채팅 이용자(요청·결과 확인), 관리자(모델·단가 등록). |
| **RISK** | 다운로드 엔드포인트가 인증 헤더를 요구해 마크다운 img로는 표시되지 않는다. 프론트가 인증 fetch 후 렌더해야 하며, 히스토리 재조회·토큰 만료·대량 이미지에서 깨지기 쉽다. |
| **SUCCESS** | 이미지 생성 모델을 붙인 에이전트에 "배너 만들어 줘" → 답변에 이미지 인라인 표시 + 다운로드. 첨부 이미지 편집 동작. 턴당 상한 초과 시 거부. ai_run 비용에 장당 단가 합산. 기존 도구·채팅 회귀 0. |
| **SCOPE** | 내부 도구 1종, OpenAI 어댑터 1종, 모델 레지스트리 플래그·단가, 도구 설정 UI, 인라인 표시. 사내 호스팅 모델·Gemini, 이미지 편집 UI(크롭·마스크), 생성 이미지의 KB 저장은 제외. |

---

## 1. 분석 개요

| 항목 | 값 |
|------|----|
| 분석 대상 | image-generation-tool |
| 설계 문서 | `idt/docs/02-design/features/image-generation-tool.design.md` (v0.2) |
| 구현 경로 | `idt/src/{domain,application,infrastructure}/image_generation/`, `idt/src/{domain,application,infrastructure}/llm_model/`, `idt/src/application/agent_builder/*`, `idt/src/application/agent_run/tracker.py`, `idt/src/api/{main.py,routes/*}`, `idt_front/src/{types,utils,services,components,pages}` |
| 분석 방식 | 정적 분석(Read/Grep). **서버를 띄우지 않아 런타임 검증(L1~L3)은 하지 않음** |
| 백엔드 확인 범위 | §11.1의 src 파일 전부 본문을 읽었다(gap-detector). 테스트는 클래스·함수 이름 확인 + Do 단계 실행 결과로 보강 |
| 프론트 확인 범위 | gap-detector는 심볼 존재만 확인했다. 메인 세션이 module-4에서 구현·실행한 테스트(아래 §6.1 근거 열)로 본문 동작을 확인해 재채점했다 |
| Do 단계 회귀 기록 | 백엔드 전체 pytest 11,020 통과 / 53 실패(master 상시 실패 목록과 파일·건수 일치). 프론트 Vitest 1,500 통과 / 9 상시 실패 + 로드 플레이크 2건(단독 통과). tsc 209건(기준선 동일), 신규 파일 eslint 0. verify-architecture·logging·tdd 이 기능 범위 위반 0. 수동 E2E(§8.4) 미실행 |

---

## 2. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| WHY(생성 도구 부재)를 해결하는가 | ✅ | `TOOL_REGISTRY["image_generate"]`(tool_registry.py:67-78, category action), 전용 노드(workflow_compiler.py:796-808, 2136-2221), OpenAI 어댑터(openai_image_generator.py:57-186) |
| "도구 추가 = 코어 무변경" 원칙 | ✅ | supervisor와 final_answer 프롬프트는 바꾸지 않았다. 링크 보존은 상태 채널과 후처리로 처리한다(run_agent_use_case.py:1362-1363, 1732) |
| 일반화 우선(특화 하드코딩 금지) | ✅ | provider 키 레지스트리(registries.py:14-35), 모델 종류는 데이터(`llm_model.model_kind`)로 관리 |
| RISK(인증 헤더 때문에 img가 깨짐) 대응 | ⚠️ | 프론트 `AuthenticatedImage`(인증 fetch → object URL → 해제, 실패 폴백 링크)는 테스트 4건 통과. 서버 다운로드는 `.png`를 `application/octet-stream`으로 내려준다(G-I3) |
| 주요 설계 결정 준수 | ✅(부분 편차) | §8 D-01~D-11. D-11은 근거가 실제 동작과 다르다(G-M9) |

전략적 불일치(Critical)는 없다.

---

## 3. 점수

### 3.1 축별 점수

| 축 | 점수 | 상태 | 근거 요약 |
|----|:----:|:----:|-----------|
| Structural | 95% | ✅ | §11.1의 백엔드 src·DI·config·env·pyproject·V081 전부 존재. 프론트 신규·수정 파일 전부 존재. 차이: 테스트 파일 구성(`test_registry_and_use_case.py` 통합), `api/test_llm_model_router`(M)와 에이전트 저장 422의 HTTP 수준 테스트 부재 |
| Functional | 94% | ✅ | §5.4 UI 체크리스트 97.5%(메인 세션 재채점), 백엔드 로직 약 90%(수정 흐름 차단, 기본 크기 설정 미사용, 노드 40줄 초과) |
| API Contract | 82% | ⚠️ | 8개 계약 중 PASS 3, 문서 정정 수준 2, PARTIAL 3. 오류 상태 코드, `MODEL_KIND_MISMATCH` 부재, 다운로드 media type |

### 3.2 Match Rate (정적 공식)

```
Overall = Structural×0.2 + Functional×0.4 + Contract×0.4
        = 95×0.2 + 94×0.4 + 82×0.4
        = 19.0 + 37.6 + 32.8 = 89.4
```

**Overall Match Rate: 89%** (런타임 미실행, 정적 공식). gap-detector 초안은 프론트 미확인 항목을 0.5로 계산해 85%였고, 메인 세션이 module-4 테스트 근거로 재채점해 89%가 됐다. 목표 90% 미달의 원인은 Contract 축(Important 4건)이다.

---

## 4. Plan 성공 기준

### 4.1 Definition of Done (Plan §4.1)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| FR-01~FR-17 구현 및 테스트 통과(TDD) | ⚠️ | §4.3 FR 표 참조. FR-16 부분(기본 크기 설정 미사용), FR-02 오류 코드 계약 부분 |
| 관리자 등록 → 빌더 도구 부착 → "배너 만들어 줘" → 인라인과 다운로드 (수동 E2E) | 미실행 | 정적으로는 경로가 이어져 있다. 등록(llm_model schemas.py:28-29), 저장(create_agent_use_case.py:205-211), 노드(workflow_compiler.py:2162-2219), 후처리(run_agent_use_case.py:1732), 저장 본문(run_agent_use_case.py:414-427), 프론트 렌더(MarkdownRenderer.image.test.tsx) |
| 첨부 + "배경을 흰색으로" → 편집 결과 (수동 E2E) | 미실행 | 정적: `_build_image_command`(workflow_compiler.py:2936-2957), edit 경로(use_case.py:118-125), `images.edit`(openai_image_generator.py:101-112) |
| 턴당 5번째 생성은 거부, 실행 실패 없음 | ✅ | policies.py:26-29, 노드 workflow_compiler.py:2172-2178. 테스트 `test_turn_cap_blocks_without_calling_use_case`, `test_at_or_over_limit_raises` |
| ai_run 상세·사용량에서 이미지 비용 합산 | ⚠️ | 원장 행(use_case.py:137-163), `cost_usd_override`(tracker.py:461-494), `complete_run`이 `SUM(ai_llm_call)` 집계(tracker.py:148). `purpose` 컬럼 VARCHAR(50)이라 마이그레이션 불필요(V021:95). 화면 표시는 런타임 미실행 |
| 히스토리 재조회 재표시, 토큰 만료 시 다운로드 링크 폴백 | ✅(정적) | 저장 본문에 후처리 마크다운 포함(run_agent_use_case.py:414-427). 프론트 폴백 AuthenticatedImage.test.tsx #2 통과 |
| 전체 pytest/Vitest 회귀 0 (상시 실패 목록 동일), verify 스킬 3종 | ✅ | §1 Do 단계 회귀 기록 |
| SOT·wiki 어긋남 보고 | ✅ | module-5 보고 완료(SOT 129행, router-map, admin-screens 33행, chat-screens) |

### 4.2 Quality Criteria (Plan §4.2)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| 신규 모듈 커버리지 80% | 미측정 | |
| ruff·eslint 0, tsc 통과 | ✅(기준선) | 신규 파일 eslint 0, tsc 209건 기준선 동일 |
| 마이그레이션 COMMENT 테스트 | ✅ | V081:6-12 전 컬럼 COMMENT, ORM `comment=` 동일(models.py:53-60), `test_migration_ddl_comments` 통과 |

### 4.3 FR 상태 요약

| FR | 판정 | 근거 | FR | 판정 | 근거 |
|----|:----:|------|----|:----:|------|
| FR-01 | ✅ | V081 | FR-10 | ✅ | supervisor_state.py:102-106, supervisor_nodes.py:364-367, 노드 2172-2178 |
| FR-02 | ⚠️ | 필드·kind 검증 있음. 오류 코드 계약은 G-I1, G-I2 | FR-11 | ✅ | answer_links.py:25-34, 결정적 덧붙임 37-52 |
| FR-03 | ✅ | tool_registry.py:67-78 | FR-12 | ✅ | D-04(원장 행). 단가 없으면 0과 경고(use_case.py:143-149) |
| FR-04 | ✅ | tool_config.py:14-34 | FR-13 | ⚠️ | 프론트 렌더·폴백·해제 테스트 통과. 서버 media type은 G-I3 |
| FR-05 | ✅ | registries.py, main.py:3064-3065 | FR-14 | ✅ | ImageGenerationConfigPanel(테스트 4건), 저장은 v0.2 `image_generation` 필드(AgentBuilderPage 테스트 #7) |
| FR-06 | ✅ | openai_image_generator.py:114-157. 백오프 고정 1초(G-M10) | FR-15 | ✅ | AdminLlmModelsPage 종류 라디오·장당 단가·배지·가격 모달(테스트 IG1·IG2) |
| FR-07 | ✅ | use_case.py:61-103 | FR-16 | ⚠️ | 설정 4종·.env.example 반영. `image_generation_default_size`를 읽는 곳 없음(G-M1) |
| FR-08 | ✅ | schemas.py:11-32, `_draft_image_request` 2223-2250 | FR-17 | ✅ | category action. 승인 게이트·가드 코드 미변경 |
| FR-09 | ✅ | policies.py:31-38, workflow_compiler.py:2943-2956, 폴백 문구 answer_links.py:32-33 | | | |

---

## 5. Structural 대조 (설계 §11.1)

### 5.1 백엔드 src

| 설계 파일 | 구현 | 비고 |
|-----------|:----:|------|
| domain/image_generation/value_objects.py | ✅ | `ImageSize`·`ImageQuality`·`GenerationMode`·`SourceImage`·`ImageBytes`·`GenerateImageCommand`·`GeneratedImage.to_state_dict`(L10-85). `fell_back_to_generate`를 Command에 추가(L55) |
| domain/image_generation/policies.py | ✅ | 5개 정적 메서드(L13-47) |
| domain/image_generation/tool_config.py | ✅ | L14-34 |
| domain/image_generation/schemas.py | ✅ | `ImageRequestDraft` extra=forbid, Literal(L11-32) |
| domain/image_generation/interfaces.py | ✅ | `ImageGeneratorPort`(L11-24) |
| domain/image_generation/exceptions.py | ✅ | 6종(L4-49) |
| domain/agent_builder/tool_registry.py | ✅ | L67-78 |
| domain/agent_run/value_objects.py | ✅ | `RunPurpose.IMAGE_GENERATION`(L68) |
| domain/llm_model/entity.py, policies.py | ✅ | 필드(entity L54-55), `MODEL_KINDS`·`require_chat_model`·`require_image_model`·`validate_default_is_chat`(policies L11, L34-68) |
| application/image_generation/use_case.py, registries.py | ✅ | |
| (추가) application/image_generation/binding.py | ✅ | v0.2 §4.2 `apply_image_generation_config`/`validate_image_generation_model` |
| (추가) application/image_generation/answer_links.py | ✅ | `render_image_summary`/`append_generated_images`. 설계의 `RunAgentUseCase._append_generated_images`를 모듈 함수로 분리 |
| application/llm_model/{schemas,create,update,update_pricing} | ✅ | schemas L28-35, 46-54, 63, 83-84 / create L96-101 / update L105-110 / pricing L58-60 |
| application/agent_builder/workflow_compiler.py | ✅ | 분기 L796-808, 노드 L2130-2250, 서브 L2881-2924, 명령 조립 L2936-2957 |
| application/agent_builder/supervisor_state.py, supervisor_nodes.py | ✅ | |
| application/agent_builder/run_agent_use_case.py | ✅ | 수집 L1361-1363, 후처리 L1732, 재개 L1234-1235 |
| application/agent_builder/schemas.py, create/update_agent_use_case.py | ✅ | `ImageGenerationConfigRequest`(schemas L52-61, 141, 210), create L203-211·L567-568, update L283-288·L474-475 |
| application/agent_run/tracker.py | ✅ | `cost_usd_override`(L462, 478, 490-494) |
| application/multimodal/settings_use_case.py | ✅ | `_validate_model`에 `is_chat_model` 조건(L197) |
| infrastructure/image_generation/openai_image_generator.py | ✅ | |
| infrastructure/llm_model/{models,llm_model_repository}.py | ✅ | models L53-60, repo L124-125·170-171·192-193 |
| infrastructure/llm_model/seed.py | — | 변경 없음. 시드는 전부 chat(엔티티 기본값) |
| api/routes/llm_model_router.py | ✅(변경 불필요) | 스키마 경유 additive |
| api/main.py | ✅ | import L211-214, DI L3063-3083 |
| config.py | ✅ | L216-219 |
| .env.example | ✅ | L65-68 |
| pyproject.toml | ✅ | `openai>=1.60`(L36), `pillow>=10.0`(L34) |
| db/migration/V081 | ✅ | |

### 5.2 백엔드 테스트

| 설계 §8.2 | 구현 | 비고 |
|-----------|:----:|------|
| #1~3 정책·tool_config·Draft | ✅ | tests/domain/image_generation/test_image_generation_domain.py |
| #4 레지스트리, #6 UseCase, #16 누출 | ✅ | tests/application/image_generation/test_registry_and_use_case.py (TestRegistry/TestGenerate/TestLedger/TestNoLeak) |
| #5 어댑터 | ✅ | tests/infrastructure/image_generation/test_openai_image_generator.py |
| #7~9 노드·compile·서브 | ✅ | test_image_generate_node.py (TestNode 8, TestCompileBranch, TestSubAgentCap) |
| #10~11 후처리·스트림 | ✅ | test_run_agent_generated_images.py |
| #12 LlmModel CRUD | ⚠️ | test_model_kind_fields.py(UseCase 수준). 라우터 TestClient 테스트 없음 |
| #13 에이전트 저장 검증 | ⚠️ | test_image_generation_binding.py·test_agent_model_kind_guard.py(UseCase 수준). **HTTP 상태 코드 테스트가 없어 G-I1을 잡지 못했다** |
| #14 비전 후보 | ✅ | test_agent_model_kind_guard.py::TestMultimodalVisionModel |
| #15 V081 COMMENT | ✅ | 기존 자동 테스트 |
| (추가) tracker override | ✅ | test_tracker_cost_override.py |
| (추가) 모델 종류 정책 | ✅ | tests/domain/llm_model/test_model_kind_policy.py |

### 5.3 프론트

| 설계 | 구현 | 비고 |
|------|:----:|------|
| types/imageGeneration.ts (N) | ✅ | 도구 id·크기 3종·품질 2종·드래프트·오류 코드 `as const` |
| types/llmModel.ts (M) | ✅ | `LLM_MODEL_KIND`, `model_kind`, `price_per_image_usd`(응답 string / 요청 number) |
| types/agentBuilder.ts (M) | ✅ | Create/Update `image_generation`, 폼 `imageGenerationDraft` |
| services/documentExtractorService.ts `fetchGeneratedFileBlob` (+test) | ✅ | documentExtractorService.test.ts 2건 |
| components/chat/AuthenticatedImage.tsx (N) + test | ✅ | 4건(로딩→img, 클릭 다운로드, 실패 폴백, revoke) |
| components/chat/MarkdownRenderer.tsx (M) + image test | ✅ | `img` 컴포넌트 접두어 판정, 외부 URL 기본 img |
| components/agent-builder/ImageGenerationConfigPanel.tsx + Modal + test | ✅ | 4건(필터, 없음 안내, 모델 선택, 크기·품질·단가) |
| pages/AgentBuilderPage (M) + test | ✅ | 4건(#7 전송, #8 제거 시 삭제, #7b 미선택 저장 차단, #10 모델 드롭다운 필터) |
| pages/AdminLlmModelsPage (M) + test | ✅ | 2건(IG1 종류 라디오·장당 단가 POST, IG2 배지·가격 모달) |
| 에이전트 설정 탭·멀티모달 폼 드롭다운 kind 필터 | ✅ | AgentBuilderPage `filterChatModels`(LeftConfigPanel·ModelSettingsModal에 전달), MultimodalSettingsForm `isChatModel` |
| (추가) utils/imageGeneration.ts, utils/llmModelKind.ts (+tests) | ✅ | 요청 변환·프리필·검증·422 접두어 매핑, kind 필터 |
| utils/agentDetailMapping.ts, agentFormPrefill.ts (M) | ✅ | `image_generate` 워커 프리필, 도구 해제 시 드래프트 정리 |
| __tests__/mocks/handlers.ts (M) | ✅ | 모델 응답·pricing 응답에 두 필드 |

Structural = 95% (테스트 구성 차이, 라우터·HTTP 테스트 부재)

---

## 6. Functional 대조

### 6.1 §5.4 Page UI Checklist (메인 세션 재채점)

| # | 항목 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | 산출 파일 경로 img는 인증 fetch, 외부 URL은 기본 img | ✅ | MarkdownRenderer.tsx `img` 컴포넌트, MarkdownRenderer.image.test.tsx 2건 통과 |
| 2 | 스켈레톤 → 이미지, 실패 시 링크 폴백, object URL 해제 | ✅ | AuthenticatedImage.test.tsx #1·#2·#3 통과 |
| 3 | 클릭 시 다운로드(파일명 유지) | ✅ | AuthenticatedImage `onClick → downloadGeneratedFile(fileId, alt)`, 테스트 #1b. 서버 `filename=` 지정(document_extractor_router.py:195-199) |
| 4 | 히스토리 재조회 동일 렌더 | ✅ | 저장 본문 = 후처리 답변(run_agent_use_case.py:414-427, 1732) |
| 5 | 빌더 도구 목록에 노출, 부착 시 패널 열림 | ✅ | 카탈로그 부팅 동기화(서버). LeftConfigPanel `CONFIGURABLE_TOOL_IDS` + `handleToolToggle` 자동 오픈, AgentBuilderPage 테스트 #7(모달 제목 확인) |
| 6 | 모델 드롭다운은 image·활성만, 없으면 안내와 저장 차단 | ✅ | ImageGenerationConfigPanel.test.tsx #5·#6, AgentBuilderPage #7b(저장 차단) |
| 7 | 크기 3종·품질 2종, 저장 payload | ✅ (v0.2 정정) | `image_generation` 전용 필드. AgentBuilderPage #7 payload 검증 |
| 8 | 서버 422 코드별 오류 표시 | ⚠️ 0.75 | `imageGenerationSaveErrorMessage`가 create/update onError에 배선됨. 모델 부재 시 서버가 404를 주는 문제(G-I1)는 접두어 매핑으로 메시지는 맞지만 상태 코드가 설계와 다름 |
| 9 | 관리자 폼 종류 라디오·장당 단가·배지, 채팅·비전 드롭다운 이미지 미노출 | ✅ | AdminLlmModelsPage IG1·IG2, MultimodalSettingsForm `isChatModel` 필터, 서버 가드(settings_use_case.py:197) |
| 10 | 에이전트 모델 드롭다운에 이미지 모델 미노출 | ✅ | AgentBuilderPage `filterChatModels` → LeftConfigPanel/ModelSettingsModal, 테스트 #10. 서버 가드(create L568, update L475) |

UI 체크리스트 점수: 9.75 / 10 = **97.5%**

### 6.2 백엔드 로직 완결성

| 영역 | 판정 | 근거 |
|------|:----:|------|
| 정책 검사(프롬프트·상한·모드 폴백·서브 상한·파일명) | ✅ | policies.py |
| 모델 로드와 kind·active 재검증(실행 시) | ✅ | use_case.py:105-113 |
| 어댑터: 모델별 quality 매핑, dall-e response_format, edit 파일 튜플, base_url, api_key_env | ✅ | openai_image_generator.py:42-112 |
| 재시도 1회, 정책 위반은 재시도 없이 안내 | ✅ | L114-157 |
| PIL 판독, 폭탄 차단, 응답 없음·URL 응답 거부 | ✅ | L159-186 (이벤트 루프 동기 실행은 G-M5) |
| 타임아웃 → ImageProviderError | ✅ | use_case.py:128-135 |
| DOCUMENT 저장(스레드풀), owner = 요청 사용자 | ✅ | use_case.py:81-89. owner는 auth_ctx, 없으면 subject_user_id(workflow_compiler.py:2149-2151, v0.2) |
| 원장(토큰 0, 단가, purpose), 실패는 경고, 단가 없으면 0과 경고 | ✅ | use_case.py:137-163 |
| 노드: 미배선·설정 불량·상한·draft 실패·UseCase 예외는 모두 안내 AIMessage | ✅ | workflow_compiler.py:2162-2208 |
| 첨부 경로를 프롬프트에 노출하지 않음(이름만) | ✅ | L2229, 2238 |
| 로깅: file_id·model·size·mode·elapsed, 프롬프트 앞 80자 | ✅ | use_case.py:97-101 |
| 서브 그래프 상한 절반, 결과 합산 | ✅ | L2881-2884, 2915-2924 |
| 답변 후처리(stream·재개) | ✅ | run_agent_use_case.py:1732, 1235 |
| 에이전트 저장: 설정 주입과 모델 검증 | ⚠️ | 동작한다. 다만 수정할 때마다 재검증해 무관한 수정까지 막힌다(G-I4) |
| 기본 크기 설정(`IMAGE_GENERATION_DEFAULT_SIZE`) 사용 | ❌ | config.py:217을 읽는 곳이 없다(G-M1) |
| 함수 40줄 규칙 / §10.4 분리 | ⚠️ | `image_generate_node`가 약 58줄(L2162-2219, G-M6) |
| 플레이스홀더·TODO | 없음 | |

백엔드 로직 점수 ≈ **90%**. Functional = (97.5 + 90) / 2 ≈ **94%**

---

## 7. API Contract 3-way 대조

| # | 계약 | Design | Server | Client | 판정 |
|---|------|:------:|:------:|:------:|:----:|
| 1 | llm-models 생성·수정 요청/응답에 `model_kind`(기본 chat)·`price_per_image_usd` | §4.1-4.2 | schemas.py:28-35, 46-54, 83-84 | types/llmModel.ts, AdminLlmModelsPage(IG1) | PASS (설계 POST/PUT, 라우터 PATCH L114 — 문서 정정) 0.9 |
| 2 | pricing에 `price_per_image_usd` | §4.1 | schemas.py:63, pricing use case L58-60 | AdminLlmModelsPage 가격 모달(IG2) | PASS (설계 PUT, 라우터 PATCH L145) 0.9 |
| 3 | 에이전트 저장 `image_generation: {llm_model_id, default_size, quality}`, null이면 변경 안 함 | §4.2 v0.2 | schemas.py:52-61, 141, 210 / create L205-211 / update L284-288 | `buildImageGenerationRequest`(undefined=변경 안 함), AgentBuilderPage #7·#8 | PASS 1.0 |
| 4 | 422 `IMAGE_MODEL_INVALID` / `IMAGE_CONFIG_INVALID` | §4.2, §6.1-6.2 | binding.py:43, 53, 72, 79, 84. 코드는 `detail` 문자열 접두어. **"찾을 수 없습니다" 문구 때문에 모델 부재가 404로 나간다**(agent_builder_router.py:263-264, 573-574) | utils/imageGeneration.ts 접두어 매핑 | PARTIAL 0.5 |
| 5 | 422 `MODEL_KIND_MISMATCH` (에이전트 모델·비전 모델) | §4.2, §6.1 | 코드 없음. `require_chat_model` 평문 ValueError(policies.py:47-51) → 평문 422 | 매핑 없음 | PARTIAL 0.5 (차단 동작은 맞음) |
| 6 | GET `/api/v1/document-extractor/files/{id}` 생성 이미지 다운로드·인라인 | §4.1, D-02 | 소유자 검증 ✅(L188-192). `.png`가 `_MEDIA_TYPES`(L134-143)에 없어 `application/octet-stream`(L198) | `fetchGeneratedFileBlob` + AuthenticatedImage | PARTIAL 0.75 |
| 7 | tool-catalog `internal:image_generate` (부팅 동기화) | §4.1 | tool_registry.py:67-78 | 빌더 도구 목록(기존 경로) | PASS 1.0 |
| 8 | 답변 본문 `![f](/api/v1/document-extractor/files/{id})` + `다운로드: [f](…)` | §3.4 | answer_links.py:13-52 | MarkdownRenderer img → AuthenticatedImage | PASS 1.0 |

Contract 점수: 6.55 / 8 = **82%**

---

## 8. 설계 결정 D-01~D-11 준수

| ID | 결정 | 판정 | 근거 |
|----|------|:----:|------|
| D-01 | 전용 합성 노드(ToolFactory 미경유) | ✅ | workflow_compiler.py:796-808. 테스트 `test_image_generate_is_function_node_not_tool_factory` |
| D-02 | DOCUMENT 저장소와 기존 다운로드 라우터 | ✅(media type 편차) | use_case.py:81-89. G-I3 |
| D-03 | `generated_images` 채널과 종료 시 본문 후처리 | ✅ | run_agent_use_case.py:1361-1363, 1732, 1235. 승인 대기 런은 공지 문구로 바뀌어 이미지가 빠진다(G-M8) |
| D-04 | 비용 = LLM 호출 행(토큰 0, cost=단가) | ✅ | use_case.py:150-158, tracker.py:478-494 |
| D-05 | `model_kind`와 `price_per_image_usd`, 채팅·비전 후보는 chat만 | ✅(계약 편차) | 서버 가드 3곳 + 프론트 필터 3곳. 기본 모델 chat 강제(policies L64-68). 오류 코드는 G-I2 |
| D-06 | 어댑터 레지스트리, openai·openai_compatible | ✅ | main.py:3064-3065 |
| D-07 | 추상 size/quality, 어댑터가 번역 | ✅ | openai_image_generator.py:36-54 |
| D-08 | 편집 입력은 이번 턴 첨부만, 없으면 폴백과 명시 | ✅ | workflow_compiler.py:2180-2182, 2943-2956, answer_links.py:32-33. 서브 그래프에는 첨부가 전달되지 않는다(G-M7) |
| D-09 | 서브 상한 = 부모의 절반(하한 1), 결과 합산 | ✅(한계 있음) | L2881-2884, 2915-2924. 부모가 이미 쓴 건수를 빼지 않는다(G-M7) |
| D-10 | 프론트 인증 fetch → object URL | ✅ | AuthenticatedImage 테스트 4건 |
| D-11 | 첨부 이미지를 프롬프트 작성 LLM에 따로 넘기지 않음(상태 messages로 자동 전달) | ⚠️ 근거 불일치 | `_draft_image_request`는 텍스트 system/user만 새로 만든다(L2246-2250, 2969-2974). draft 단계에서 비전 모델도 이미지를 보지 못한다. 편집 이미지는 provider에 직접 가므로 결과 영향은 작다(G-M9) |

v0.2 정정 2건(전용 `image_generation` 필드, owner 폴백 subject_user_id)은 코드와 일치한다.

---

## 9. Gap 목록

### 🔴 Critical

없음. Plan 성공 기준을 위반하는 정적 결함은 찾지 못했다. 수동 E2E는 미실행.

### 🟡 Important (메인 세션이 코드에서 재확인함)

| ID | 파일:라인 | 내용 | 신뢰도 | 설계 근거 | 제안 |
|----|-----------|------|:------:|-----------|------|
| G-I1 | api/routes/agent_builder_router.py:263-264 (update), 573-574 (create) / application/image_generation/binding.py:79 | `IMAGE_MODEL_INVALID: 이미지 생성 모델을 찾을 수 없습니다`가 라우터의 `"찾을 수 없" → 404` 분기에 걸린다. 모델 부재 응답이 설계의 422가 아니라 404다 | 95% | §4.2 표(422 IMAGE_MODEL_INVALID), §8.2 #13 | 라우터에서 `IMAGE_` 접두어를 먼저 422로 매핑한다. TestClient 상태 코드 테스트 추가 |
| G-I2 | domain/llm_model/policies.py:47-51, create_agent_use_case.py:568, update_agent_use_case.py:475 | 에이전트 모델로 이미지 모델을 고르면 거부되지만 `MODEL_KIND_MISMATCH` 코드가 없다(평문 422) | 90% | §4.2, §6.1-6.2 | 메시지에 `MODEL_KIND_MISMATCH:` 접두어를 붙이고 프론트 매핑 추가 |
| G-I3 | api/routes/document_extractor_router.py:134-143, 198 | `.png`가 `_MEDIA_TYPES`에 없어 생성 이미지가 `application/octet-stream`으로 나간다. 어댑터가 JPEG/WEBP를 돌려주면 파일명 `.png`와 내용이 어긋난다(openai_image_generator.py:185, policies.py:47) | 70% (렌더 영향은 런타임 미확인) | D-02, D-10, FR-13 | `_MEDIA_TYPES`에 `.png/.jpg/.jpeg/.webp` 추가, 파일명 확장자를 실제 mime에 맞춤 |
| G-I4 | application/agent_builder/update_agent_use_case.py:286-288 | 에이전트 수정마다 `validate_image_generation_model`을 실행한다. 이미지 모델이 비활성화되면 이름·프롬프트 변경 같은 무관한 수정도 막힌다 | 85% | Plan §6.3 "기존 에이전트 수정 흐름을 막지 않음" | `request.image_generation is not None`일 때만 검증. 실행 시에는 노드가 안내(use_case.py:105-113) |

### 🔵 Minor / 의도된 편차 판정

| ID | 파일:라인 | 내용 | 신뢰도 | 판정 / 제안 |
|----|-----------|------|:------:|-------------|
| G-M1 | config.py:217 | `image_generation_default_size`를 읽는 곳이 없다. 기본 크기는 `ImageGenerationToolConfig`(tool_config.py:17)와 `ImageGenerationConfigRequest`(schemas.py:60) 하드코딩 | 95% | 설정을 요청 스키마 기본값에 쓰거나 설정 항목 제거 |
| G-M2 | api/routes/llm_model_router.py:114-126 | 수정에서 `validate_default_is_chat` 위반(ValueError)이 404로 나간다 | 90% | "찾을 수 없"만 404, 나머지 422 |
| G-M3 | application/llm_model/update_llm_model_use_case.py:106-109 | 에이전트가 쓰는 chat 모델의 종류를 image로 바꿔도 막지 않는다. `price_per_image_usd`는 null로 되돌릴 수 없다 | 80% | 관리자 동작이라 Minor |
| G-M4 | 설계 §4.1 | llm-models 메서드가 설계는 POST/PUT, 코드는 PATCH | 100% | 설계 정정 |
| G-M5 | openai_image_generator.py:159-186 | PIL verify/open을 이벤트 루프에서 동기 실행. 전역 `Image.MAX_IMAGE_PIXELS` 변경·복원이 동시 요청에 안전하지 않음 | 85% | `asyncio.to_thread` + 사전 검사 |
| G-M6 | workflow_compiler.py:2162-2219 | `image_generate_node` 약 58줄(40줄 규칙 초과) | 90% | 상한 검사·UseCase 호출 블록 헬퍼 분리 |
| G-M7 | workflow_compiler.py:2874-2885, 2921-2924 | (a) 서브 그래프에 attachments 미전달 → 서브 편집 요청은 항상 generate 폴백. (b) 서브 상한이 부모 사용 건수를 빼지 않아 턴 합계가 부모 상한 초과 가능 | 85% | D-09 문구와는 일치. 설계에 명시 또는 `min(sub_cap, parent_cap - count)` |
| G-M8 | run_agent_use_case.py:1732-1745 | 승인 대기로 끝난 런은 공지 문구로 바뀌어 게이트 전 이미지 링크가 그 턴 답변에서 빠진다(재개 답변에는 붙음) | 75% | 설계 결정 필요 |
| G-M9 | workflow_compiler.py:2228-2250 | draft LLM 입력은 텍스트만. D-11 근거가 실제와 다름 | 90% | D-11 정정 |
| G-M10 | openai_image_generator.py:136 | 재시도 대기 고정 1초(설계는 지수 백오프). 재시도 1회라 실질 차이 없음 | 100% | 설계 문구 정정 |
| G-M11 | workflow_compiler.py:2149-2151 | auth_ctx·subject_user_id 모두 없으면 owner ""로 저장 | 60% | 빈 owner면 생성하지 않고 안내 |
| G-M12 | 설계 §5.4 #7, §2.1, §2.2 #2, §8.3 #7 | `tool_configs["image_generate"]` 표기가 v0.2 §4.2와 어긋난 채 남아 있음 | 100% | 설계 일괄 정정 |
| G-M13 | 설계 §4.3 | `_append_generated_images`를 `answer_links` 모듈 함수로 구현. 노드 token_usage 증분 기준이 본문 길이 | 100% | 동등 구현. 설계 갱신 |
| G-M14 | 프론트 | 평가 실행·스윕·미들웨어·청킹 프로파일 페이지의 모델 드롭다운은 kind 필터를 적용하지 않았다(설계가 명시한 채팅·비전·에이전트 모델 드롭다운 밖) | 100% | 설계에 범위 명시 또는 후속 적용 |

### 🟢 추가 구현 (설계 X, 구현 O)

| 항목 | 위치 | 판단 |
|------|------|------|
| `LlmModelPolicy.validate_default_is_chat` | domain/llm_model/policies.py:64-68 | 이미지 모델이 기본 모델이 되는 것을 막는다. 타당. 설계 §4.2 명시 필요 |
| `LlmModel.is_chat_model`/`is_image_model` | entity.py:57-63 | 타당 |
| `GenerateImageCommand.fell_back_to_generate` | value_objects.py:55 | 타당 |
| `binding.py`, `answer_links.py` 모듈 | application/image_generation/ | v0.2 계약 구현 단위. 설계 §11.1 갱신 |
| 프론트 `utils/imageGeneration.ts`, `utils/llmModelKind.ts`, 관리자 폼 "이미지 모델은 기본 모델 불가" 클라이언트 검증, 도구 부착 후 모델 미선택 저장 차단 | idt_front/src | 타당. 설계 §5.3 갱신 |

---

## 10. 권장 조치

### 즉시 조치 (iterate 후보, Important 4건)
1. G-I1: 에이전트 저장의 `IMAGE_*`·`MODEL_KIND_MISMATCH` 접두 오류를 422로 고정하고 TestClient 상태 코드 테스트 추가
2. G-I2: `MODEL_KIND_MISMATCH:` 접두어를 넣고 프론트 매핑 추가
3. G-I3: 다운로드 `_MEDIA_TYPES`에 이미지 타입 추가, 파일명 확장자를 실제 mime에 맞춤
4. G-I4: 수정 시 이미지 모델 재검증은 `image_generation` 요청이 있을 때만

### 문서 갱신 필요
- 설계 §2.1·§2.2·§5.4 #7·§8.3 #7의 `tool_configs` 표기(G-M12), §4.1 메서드 PATCH(G-M4), §4.3 후처리 위치(G-M13), D-11 근거(G-M9), 재시도 백오프(G-M10), `validate_default_is_chat` 추가, 서브 그래프 첨부 미전달(G-M7), 드롭다운 필터 범위(G-M14)

### 후속 (Minor)
- G-M1 기본 크기 설정 사용, G-M5 PIL 판독 스레드풀 이동, G-M6 노드 분리, G-M3 사용 중 모델 kind 변경 가드, G-M8 승인 대기 답변 이미지, G-M11 빈 owner 방어

---

## 11. Runtime Verification Plan (실행하지 않음, 서버 필요)

전제: 백엔드 `uvicorn src.main:app --port 8000`, `$ADMIN`·`$TOKEN`은 JWT. `OPENAI_API_KEY` 설정. 시드는 설계 §8.5(image 모델 1종, chat 모델 1종, 이미지 도구 에이전트·서브에이전트 보유 에이전트·승인 게이트 에이전트).

### L1: API

| # | 테스트 | 명령 | 기대 상태 | 기대 응답 |
|---|--------|------|:---------:|-----------|
| 1 | 이미지 모델 등록 | `curl -s -X POST localhost:8000/api/v1/llm-models -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"provider":"openai","model_name":"gpt-image-1","display_name":"GPT Image","api_key_env":"OPENAI_API_KEY","model_kind":"image","price_per_image_usd":"0.04"}'` | 201 | `.model_kind=="image"`, `.price_per_image_usd=="0.0400"` |
| 2 | 종류 기본값 | `model_kind` 생략 | 201 | `.model_kind=="chat"` |
| 3 | 미허용 종류 | `"model_kind":"video"` | 422 | pydantic 오류 |
| 4 | 이미지 모델을 기본 모델로 | `"model_kind":"image","is_default":true` | 422 | 기본 모델은 chat만 |
| 5 | 단가 수정 | `PATCH …/llm-models/{id}/pricing` `{"input_price_per_1k_usd":"0","output_price_per_1k_usd":"0","price_per_image_usd":"0.08"}` | 200 | `.price_per_image_usd=="0.0800"` |
| 6 | 목록 노출 | `GET /api/v1/llm-models` | 200 | 각 항목에 `model_kind`·`price_per_image_usd` |
| 7 | 도구 카탈로그 | `GET /api/v1/tool-catalog` | 200 | `internal:image_generate` 존재 |
| 8 | 에이전트 저장 정상 | `POST /api/v1/agents` `{"tool_ids":["internal:image_generate"],"image_generation":{"llm_model_id":"<image id>","default_size":"1024x1024","quality":"standard"},…}` | 201 | |
| 9 | chat 모델을 이미지 설정에 | 8과 같고 `llm_model_id`만 chat 모델 | 422 | `IMAGE_MODEL_INVALID` 접두어 |
| 10 | 없는 모델 | `llm_model_id:"nope"` | 422 (설계) / **현재 404 (G-I1)** | `IMAGE_MODEL_INVALID` 접두어 |
| 11 | 미허용 크기 | `default_size:"512x512"` | 422 | `IMAGE_CONFIG_INVALID` 접두어 |
| 12 | 에이전트 모델로 이미지 모델 | 에이전트 본체 `llm_model_id:"<image id>"` | 422 | 설계 `MODEL_KIND_MISMATCH` / 현재 평문(G-I2) |
| 13 | 이미지 모델 비활성화 후 무관한 수정 | `DELETE /llm-models/{image id}` → `PATCH` 에이전트 `{"name":"x"}` | 설계 의도 200 / **현재 404(G-I4+G-I1)** | |
| 14 | 생성 이미지 다운로드(소유자) | `curl -s -D - …/files/{file_id} -H "Authorization: Bearer $TOKEN" -o out.png` | 200 | 1024×1024. `Content-Type`은 현재 octet-stream(G-I3) |
| 15 | 타인 다운로드 | 다른 사용자 토큰 | 403 | `FORBIDDEN` |
| 16 | 미인증 | 헤더 없음 | 401 | |

### L2: UI (Playwright, Vitest 단위로는 통과)

| # | 페이지 | 동작 | 기대 결과 |
|---|--------|------|-----------|
| 1 | /admin/llm-models | 종류 "이미지 생성" 선택 → 저장 | 장당 단가 입력 표시, 비전 체크 숨김, 목록 배지 |
| 2 | /agent-builder | "이미지 생성" 도구 부착 | 설정 모달 열림, image·활성 모델만 |
| 3 | /agent-builder | 이미지 모델 0건 | 관리자 등록 안내, 저장 차단 |
| 4 | /agent-builder | 1536x1024·hd 선택 → 저장 | `image_generation` 전송 |
| 5 | /agent-builder | 서버 422 `IMAGE_MODEL_INVALID` | 안내 메시지 표시 |
| 6 | /agent-builder | 도구 제거 → 저장 | `image_generation` 미전송 |
| 7 | /agent-builder 모델 설정 | 드롭다운 열기 | 이미지 모델 미노출 |
| 8 | /admin/multimodal | 비전 모델 드롭다운 | 이미지 모델 미노출 |
| 9 | /chat | 생성 답변 수신 | 스켈레톤 → `img[src^="blob:"]` |
| 10 | /chat | 이미지 클릭 | 파일명 유지 다운로드 |
| 11 | /chat | 토큰 만료 상태 재진입 | 폴백 링크 |
| 12 | /chat | 외부 URL 이미지 | 기본 `<img>`, 인증 fetch 없음 |

### L3: E2E (설계 §8.4)

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 1 | gpt-image-1 등록(0.04) → 도구 부착 → "가을 특판 배너 만들어 줘" | 인라인 이미지, 클릭 다운로드, 1024×1024 |
| 2 | 이미지 첨부 + "배경을 흰색으로" | 편집 결과, 폴백 문구 없음 |
| 3 | 첨부 없이 "이 이미지 배경 바꿔 줘" | 생성 결과 + "(첨부 이미지가 없어 새로 생성했습니다)" |
| 4 | 한 턴 5회 생성 유도 | 5번째 상한 안내, RUN_COMPLETED 정상 |
| 5 | ai_run 상세·사용량 | `ai_llm_call` purpose `image_generation`, token 0, cost 0.04×건수, `ai_run.total_cost_usd` 합산 |
| 6 | 세션 재진입 | 이미지 재표시, `conversation_message.content`에 마크다운 이미지 |
| 7 | 이미지 도구를 가진 서브에이전트에 위임 | 서브 상한 2, 부모 답변에 이미지 포함 |
| 8 | 승인 게이트 → 승인 → 재개 | 재개 답변에 이미지, 스냅샷에 `data:image`·base64 없음 |
| 9 | DB·로그 누출 점검 | `ai_run_step`·`ai_llm_call`·로그·스냅샷에 base64 없음, 프롬프트 앞 80자만 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-02 | gap-detector 정적 분석 초안 (Match 85%, 프론트 unverified) | gap-detector |
| 0.2 | 2026-11-02 | 프론트 항목 module-4 테스트 근거로 재채점(Functional 84→94, Overall 89%), Important 4건 코드 재확인, G-M14 추가 | 배상규 |
| 0.3 | 2026-11-02 | Act-1: Important 4건 수정(G-I1~G-I4) + 테스트, 재채점 Overall 95% | 배상규 |
