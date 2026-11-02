# image-generation-tool Completion Report

> **Status**: Complete (코드 미커밋, 수동 E2E 미실행)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 기준 커밋 3578c1d + 워킹트리 (branch: feature/agent-run-turn-index-fix)
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-11-02
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 89% → Act-1 → 95%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | image-generation-tool. 에이전트 내부 도구 `image_generate` (이미지 생성·첨부 이미지 편집) |
| Start Date | 2026-10-30 (Plan·Design) |
| End Date | 2026-11-02 (Do 5개 모듈, Check, Act-1, Report) |
| Duration | 약 4일 (달력 기준). Do는 10-31 ~ 11-02 |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────┐
│  Design Match Rate: 95% (정적 공식, 런타임 미포함)      │
├──────────────────────────────────────────────────────┤
│  FR 충족:        16 / 17                              │
│  FR 부분:         1 / 17  (FR-16 기본 크기 설정 미사용)  │
│  Plan 성공 기준 충족: 6 / 11                            │
│  Plan 성공 기준 부분: 2 / 11                            │
│  미실행·미측정:   3 / 11  (수동 E2E 2건, 커버리지 1건)    │
│  Act-1 Important 수정: 4 / 4                           │
└──────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트에 이미지 생성 도구가 없었고, 이미지 생성 API 호출 코드가 저장소 전체에 0건이었다. |
| **Solution** | 전용 합성 노드 + provider 키 어댑터 레지스트리 + `llm_model.model_kind`(chat/image)와 장당 단가. 산출물은 DOCUMENT 저장소와 기존 다운로드 라우터를 재사용한다. |
| **Function/UX Effect** | 정적 Match Rate 95%. 단위·모킹 테스트 기준 턴당 상한(4장) 초과 요청은 5번째부터 거부 안내를 받고 실행은 계속된다. 인라인 이미지는 인증 fetch 후 object URL로 그린다. 수동 E2E 9개 시나리오는 실행하지 않았다. |
| **Core Value** | 코어(supervisor·final_answer 프롬프트)를 바꾸지 않고 도구 1개와 모델 등록으로 이미지 생성 업무를 에이전트에 맡길 수 있게 됐다. 새 API 엔드포인트와 새 테이블은 없다. |

---

## 1.4 Success Criteria Final Status

> Plan §4 (Definition of Done §4.1 + Quality Criteria §4.2). 충족 6, 부분 2, 미실행·미측정 3, 전체 11건.

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-17 구현 및 테스트 통과 (TDD) | 부분 | FR 16/17 충족. FR-16의 `image_generation_default_size` 설정을 읽는 곳이 없다 (G-M1). §3.1 참조 |
| SC-2 | 관리자 등록 → 도구 부착 → "배너 만들어 줘" → 인라인·다운로드 (수동 E2E) | 미실행 | 정적 경로 확인: 등록(llm_model schemas.py:28-35), 저장(create_agent_use_case.py:203-211), 노드(workflow_compiler.py:2162-2219), 후처리(run_agent_use_case.py:1732), 프론트 렌더 테스트 통과. 실서버 실행 없음 |
| SC-3 | 이미지 첨부 + "배경을 흰색으로" → 편집 결과 표시 (수동 E2E) | 미실행 | 정적: 편집 명령 조립(workflow_compiler.py:2936-2957), edit 경로(use_case.py:118-125), `images.edit`(openai_image_generator.py:101-112) |
| SC-4 | 턴당 5번째 생성 요청은 거부 안내, 실행 실패 없음 (단위) | 충족 | policies.py:26-29, 노드 workflow_compiler.py:2172-2178. 테스트 `test_turn_cap_blocks_without_calling_use_case`, `test_at_or_over_limit_raises` |
| SC-5 | ai_run 상세·사용량 화면에서 이미지 비용 합산 확인 | 부분 | 원장 행 기록(use_case.py:137-163), `cost_usd_override`(tracker.py:461-494), `complete_run`의 `SUM(ai_llm_call)` 집계(tracker.py:148). 화면 표시는 실행하지 않음 |
| SC-6 | 히스토리 재조회에서 이미지 재표시, 토큰 만료 시 다운로드 링크 폴백 | 충족 (정적) | 저장 본문에 후처리 마크다운 포함(run_agent_use_case.py:414-427). 폴백 테스트 AuthenticatedImage #2 통과 |
| SC-7 | 전체 pytest/Vitest 회귀 0 (상시 실패 목록 동일), verify 스킬 3종 통과 | 충족 | §5.2. 백엔드 실패 53건 = master 상시 실패 목록. 프론트 상시 실패 9건 + 로드 플레이크 2건(단독 통과). verify 3종 기능 범위 위반 0 |
| SC-8 | SOT·wiki 어긋남 보고 | 충족 | §4.3. 보고만 하고 수정하지 않음 |
| SC-9 | 신규 모듈 테스트 커버리지 80% 이상 | 미측정 | 커버리지 측정 기록 없음 |
| SC-10 | ruff·eslint 신규 오류 0, tsc 통과 | 충족 | 신규 프론트 파일 eslint 0. tsc 209건은 기준선과 동일. Act-1 변경 줄 ruff 0 |
| SC-11 | 마이그레이션 COMMENT 테스트 통과 | 충족 | V081 전 컬럼 COMMENT(V081:6-12), ORM `comment=` 동일(models.py:53-60), `test_migration_ddl_comments` 통과 |

**Success Rate**: 6/11 met (55%). 부분 2건, 미실행·미측정 3건. 수동 E2E(SC-2, SC-3)가 끝나면 Plan 기준 판정을 다시 해야 한다.

## 1.5 Key Decisions & Outcomes

> PRD는 없다. 결정 출처는 Plan §1.4(사용자 결정 기록, 2026-10-30)와 Design §12(D-01~D-11) 및 v0.2 정정 2건이다.

### 1.5.1 Plan 사용자 결정 (2026-10-30)

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 생성 모델 = OpenAI 이미지 API + provider 키 어댑터 레지스트리 (OpenAI·호환만 구현) | 예 | `main.py:3064-3065`에 openai·openai_compatible 등록. Gemini·사내 모델은 미구현 (범위 밖) |
| [Plan] | 모델 관리 = LLM 모델 레지스트리에 종류 플래그, 에이전트 도구 설정에서 선택 | 예 | `model_kind` 컬럼(V081), 빌더 설정 패널에서 선택 |
| [Plan] | 산출물 = 영구 보관 + 다운로드 링크 (문서 산출물과 동일 경로) | 예 | DOCUMENT 저장소 재사용. 정리 잡은 없음 (§4.1 후속) |
| [Plan] | 입력 = 텍스트 → 이미지 + 이번 턴 첨부 이미지 편집 | 예 | `mode=edit`, `state.attachments`의 이미지 사용 |
| [Plan] | 답변 표시 = 인증 fetch → object URL, 히스토리 재조회 동일 | 예 | `AuthenticatedImage`(4건 테스트). 본문 마크다운을 저장하므로 재조회에도 같은 방식으로 그림 |
| [Plan] | 상한 = 호출당 1장, 기본 1024px, 턴당 최대 4장, 전부 설정값 | 부분 | 턴당 4장은 설정값으로 적용. 기본 크기 설정(`IMAGE_GENERATION_DEFAULT_SIZE`)은 읽는 곳이 없다 (G-M1) |
| [Plan] | 비용 = `price_per_image_usd` 추가, 건수×단가를 ai_run 비용에 합산 | 예 | 토큰 0인 LLM 호출 행 1건으로 기록 (D-04) |

### 1.5.2 Design D-01 ~ D-11

| ID | Decision | Followed? | Outcome |
|----|----------|:---------:|---------|
| D-01 | 전용 합성 노드 (ToolFactory 미경유) | 예 | 구조화 출력·상한·저장·원장을 한 노드에서 처리. 단 노드가 약 58줄로 40줄 규칙을 넘는다 (G-M6) |
| D-02 | 산출물은 DOCUMENT 저장소 + 기존 다운로드 라우터 | 예 | 새 엔드포인트 0건. `.png`의 media type 누락은 Act-1에서 수정 (G-I3) |
| D-03 | `generated_images` 상태 채널 + 종료 시 본문 후처리 | 예 | 답변 본문에 빠진 이미지 링크를 결정적으로 덧붙인다. 승인 대기로 끝난 턴에서는 이미지 링크가 빠진다 (G-M8, 미해결) |
| D-04 | 비용 = LLM 호출 행 (토큰 0, cost = 단가, purpose `image_generation`) | 예 | 원장 스키마 변경 없이 합산. 단가 미등록 시 0과 경고 로그 |
| D-05 | `model_kind` + `price_per_image_usd`, 채팅·비전 후보는 chat만 | 예 (편차 있음) | 서버 가드 3곳 + 프론트 필터 3곳. 평가·스윕·미들웨어·청킹 드롭다운은 필터 대상 밖이라 미적용 (G-M14) |
| D-06 | 어댑터 레지스트리, OpenAI·호환만 | 예 | 미등록 provider는 명시 오류 |
| D-07 | 정책 VO는 추상 size·quality, 어댑터가 모델명으로 번역 | 예 | gpt-image는 `medium`/`high`, dall-e-3은 `standard`/`hd`와 `response_format` 지정 |
| D-08 | 편집 입력은 이번 턴 첨부만, 없으면 생성으로 폴백하고 명시 | 예 (편차 있음) | 서브 그래프에는 첨부가 넘어가지 않아 서브에서 편집 요청은 항상 폴백된다 (G-M7) |
| D-09 | 서브 그래프 상한 = 부모의 절반 (하한 1), 결과 합산 | 예 (한계 있음) | 부모가 이미 쓴 건수를 빼지 않아 턴 합계가 부모 상한을 넘을 수 있다 (G-M7) |
| D-10 | 프론트 인증 fetch → object URL, 실패 시 다운로드 링크 폴백 | 예 | 토큰을 URL에 넣지 않음. 테스트 4건 |
| D-11 | 첨부 이미지를 프롬프트 작성 LLM에 따로 넘기지 않음 (상태 messages로 자동 전달) | 아니오 | 근거가 틀렸다. 노드의 draft 호출은 텍스트만 넣으므로 비전 모델도 첨부를 보지 못한다. 편집 이미지는 provider에 직접 전달되므로 결과 영향은 작다 (G-M9). Design §12 정정 대상 |

### 1.5.3 Design v0.2 정정 (Do 중 2건)

| Source | Correction | Followed? | Outcome |
|--------|-----------|:---------:|---------|
| [Design v0.2] | 도구 설정을 `tool_configs`가 아니라 전용 요청 필드 `image_generation`으로 받는다 (발표자료 설정과 같은 방식). `tool_configs`는 RAG 설정 스키마 전용이었다 | 예 | 코드와 일치. 단 Design 본문 §2.1, §2.2, §5.4 #7, §8.3 #7에 `tool_configs["image_generate"]` 표기가 남아 있다 (G-M12) |
| [Design v0.2] | 노드 owner는 auth_ctx가 없으면 `subject_user_id`로 폴백 | 예 | 코드와 일치 (workflow_compiler.py:2149-2151). 둘 다 없으면 빈 owner로 저장된다 (G-M11) |

**Design 대비 추가 편차 (v0.3 Act-1 중 확인)**: 에러 계약. 설계 §6.2는 `{"detail": {"code", "message"}}`를 가정했지만, 실제 구현은 `detail` 문자열의 접두어(`IMAGE_MODEL_INVALID:` 등)다. Act-1에서 이 접두어 계약으로 확정하고 설계 정정 대상으로 남겼다.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [image-generation-tool.plan.md](../01-plan/features/image-generation-tool.plan.md) | Draft v0.1.0 (구현 기준으로 사용, 상태 미갱신) |
| Design | [image-generation-tool.design.md](../02-design/features/image-generation-tool.design.md) | v0.2 (tool_configs 표기·D-11 정정 대기) |
| Check | [image-generation-tool.analysis.md](../03-analysis/image-generation-tool.analysis.md) | v0.3 (Match 95%) |
| Act | Current document | Complete |

---

## PDCA Cycle Summary

### Plan
- 문서: `docs/01-plan/features/image-generation-tool.plan.md` (2026-10-30)
- 목표: 에이전트가 이미지를 생성하거나 첨부 이미지를 편집해 채팅 답변에 돌려주게 한다.
- 범위: 내부 도구 1종, OpenAI 어댑터 1종, 모델 종류·단가, 빌더 설정 패널, 인라인 표시. FR 17건.
- Plan 추정 기간: 명시하지 않음.

### Design
- 문서: `docs/02-design/features/image-generation-tool.design.md` (v0.1 2026-10-30, v0.2 2026-10-31)
- 선택: Option C (실용 절충). 전용 합성 노드, DOCUMENT 저장소 재사용, `generated_images` 채널과 종료 시 후처리, LLM 호출 행으로 비용 기록.
- 핵심 결정: §1.5 참조. v0.2 정정 2건(`image_generation` 전용 필드, owner 폴백).

### Do
- 구현 단위 (5개 모듈):
  - module-1 (10-31): V081 마이그레이션, LlmModel 필드, CRUD, 채팅·비전 드롭다운 kind 필터
  - module-2 (10-31): `domain/image_generation`, 레지스트리, OpenAI 어댑터, `GenerateImageUseCase`, 원장 기록
  - module-3 (10-31): 상태 채널, 전용 노드, compile 분기, 서브 그래프 상한, TOOL_REGISTRY, 답변 후처리, 저장 검증(v0.2 정정 반영)
  - module-4 (11-02): 프론트 `AuthenticatedImage`, `MarkdownRenderer` img, `ImageGenerationConfigPanel`, 빌더 배선, 관리자 폼
  - module-5 (11-02): 회귀 실행, verify 스킬, 문서 보고
- 실제 기간: 약 3일 (10-31 ~ 11-02). 코드는 커밋하지 않았다 (base 3578c1d, branch feature/agent-run-turn-index-fix).
- 신규 백엔드 테스트 영역: domain/image_generation, application/image_generation(레지스트리·유스케이스·원장·누출 계약), infrastructure/image_generation(OpenAI 어댑터, 모킹), llm_model 종류 정책·필드, agent_builder(노드 8건, compile 분기, 서브 상한 2건, 생성 이미지 후처리 8건, 바인딩 7건, 모델 종류 가드), tracker 비용 override, API 저장 오류 상태 5건, document_extractor png media type, update 재검증 2건.
- 신규 프론트 테스트 영역: utils/imageGeneration 9, utils/llmModelKind 3, AuthenticatedImage 4, MarkdownRenderer.image 2, ImageGenerationConfigPanel 4, documentExtractorService 2, AdminLlmModelsPage +2, AgentBuilderPage +4.

### Check
- 문서: `docs/03-analysis/image-generation-tool.analysis.md` (v0.1 → v0.2 → v0.3)
- 1차 (gap-detector 초안): 85%. 프론트 항목을 확인하지 못해 0.5로 계산했다.
- 2차 (메인 세션 재채점, 프론트 module-4 테스트 근거 반영): 89%. Contract 축 82%가 목표 90%에 못 미치는 원인이다.
- 발견 사항: Critical 0, Important 4 (G-I1~G-I4), Minor 14 (G-M1~G-M14).

### Act
- Act-1 (11-02): Important 4건 수정 (§5.3). 수정 후 재채점 Overall 95%. 이터레이션 1회.
- Report (11-02): 본 문서.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | V081: `model_kind VARCHAR(16) NOT NULL DEFAULT 'chat'`, `price_per_image_usd DECIMAL(10,4) NULL`, 전 컬럼 COMMENT | 충족 | 기존 행은 chat. COMMENT 테스트 통과 |
| FR-02 | 엔티티·스키마·ORM·관리자 CRUD·단가 API가 두 필드를 다룸. 채팅·비전 드롭다운은 chat만 | 충족 | Act-1로 `MODEL_KIND_MISMATCH` 접두어와 프론트 매핑 추가 (G-I2). 기본 모델은 chat만 허용 (추가 구현) |
| FR-03 | `TOOL_REGISTRY["image_generate"]`(category action), 부팅 동기화로 `internal:image_generate` 노출 | 충족 | tool_registry.py:67-78 |
| FR-04 | `ImageGenerationToolConfig`: llm_model_id(필수), default_size, quality | 충족 | tool_config.py:14-34 |
| FR-05 | `ImageGeneratorRegistry`: provider 키 → 팩토리, 미등록은 명시 오류 | 충족 | registries.py, main.py |
| FR-06 | `OpenAIImageGenerator`: generate/edit, base_url·api_key_env, 429·5xx·타임아웃 1회 재시도, 정책 위반은 재시도 없이 안내 | 충족 | 재시도 대기는 고정 1초 (설계는 지수 백오프, G-M10) |
| FR-07 | `GenerateImageUseCase`: 정책 검사 → 어댑터 → DOCUMENT 저장 → 결과 VO | 충족 | use_case.py:61-103 |
| FR-08 | 전용 노드: 구조화 출력 `{prompt, size, mode, source_image_index}` | 충족 | schemas.py:11-32, `_draft_image_request` |
| FR-09 | 편집 모드: 이번 턴 첨부가 없으면 생성으로 폴백하고 명시 | 충족 | policies.py:31-38, 폴백 문구 answer_links.py:32-33. 서브 그래프 미전달 (G-M7) |
| FR-10 | 턴당 상한: `generated_image_count`, 초과 시 AIMessage 거부, 실행 계속 | 충족 | supervisor_state.py:102-106, 노드 2172-2178 |
| FR-11 | 산출물 본문 계약: 이미지 줄 + 다운로드 줄 + 프롬프트 요약 | 충족 | 프롬프트 규범 대신 결정적 덧붙임으로 구현 (D-03). answer_links.py:13-52 |
| FR-12 | 생성 1건당 `image_count=1`, `cost_usd = 단가`, ai_run 합산. 단가 없으면 0과 경고 | 충족 | use_case.py:137-163, tracker.py:461-494 |
| FR-13 | 프론트 `img`: 산출 경로는 인증 fetch → object URL, 실패 시 링크 폴백, 해제 | 충족 | 프론트 테스트 6건. 서버 media type은 Act-1에서 수정 (G-I3). 실제 브라우저 렌더는 미확인 |
| FR-14 | 프론트 `ImageGenerationConfigPanel`: 모델(image·활성), 크기 3종, 품질 2종 | 충족 | 테스트 4건. 저장은 `image_generation` 필드 |
| FR-15 | 관리자 폼: 종류 라디오, 장당 단가(image일 때만), 목록 배지 | 충족 | AdminLlmModelsPage IG1·IG2 |
| FR-16 | 설정 4종 (`max_per_turn`, `default_size`, `timeout_sec`, `max_prompt_chars`) + `.env.example` | 부분 | `image_generation_default_size`를 읽는 코드가 없다. 기본 크기는 코드에 하드코딩 (G-M1). 나머지 3종은 사용 |
| FR-17 | 기존 미들웨어(승인 게이트·프롬프트 가드·메모리) 변경 없이 동작 | 충족 | category action, 기존 코드 미변경. 승인 게이트 E2E는 미실행 |

**FR 합계: 16 충족, 1 부분 (FR-16).** 판정은 Analysis §4.3 (Check 시점)에 Act-1 수정 결과를 반영했다.

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Performance | 생성 1건 타임아웃 60초(설정), 비동기 호출 | `asyncio.wait_for`로 타임아웃 → ImageProviderError. 실측 없음 | 부분 (실측 미실행) |
| Security | 다운로드 소유자 검증, 입력 이미지는 이번 턴 첨부만, API 키는 env 이름만 저장 | 기존 소유자 검증 적용. 경로는 프롬프트·로그에 넣지 않음 (이름만). 누출 계약 테스트 16번 통과 | 충족 |
| Privacy | 바이트는 저장소 파일에만. DB·로그·이력에는 file_id·크기·모델만 | `GeneratedImage`에 바이트 필드 없음. 누출 계약 테스트 통과. 로그는 프롬프트 앞 80자 | 충족 (정적) |
| Compatibility | 기존 도구·채팅 회귀 0. `model_kind` 기본 chat | 전체 회귀 기준선 동일 (§5.2) | 충족 |
| Architecture | domain에 SDK 금지, 어댑터는 infrastructure, 함수 40줄 | verify-architecture 기능 범위 위반 0. 노드 58줄 (G-M6) | 부분 (함수 길이 1건) |
| DDL | 테이블·전 컬럼 COMMENT | V081 + ORM 동일, COMMENT 테스트 통과 | 충족 |
| 상한 (PIL) | 응답 이미지 픽셀 상한 | `MAX_IMAGE_PIXELS` 재사용 (설계 §7). 전역 상태 변경과 이벤트 루프 동기 실행 문제 (G-M5) | 부분 |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 | `idt/src/domain/image_generation/` (value_objects, policies, tool_config, schemas, interfaces, exceptions) | 신규 완료 |
| 애플리케이션 | `idt/src/application/image_generation/` (use_case, registries, binding, answer_links) | 신규 완료 |
| 인프라 | `idt/src/infrastructure/image_generation/openai_image_generator.py` | 신규 완료 |
| 그래프 통합 | `workflow_compiler.py`, `supervisor_state.py`, `supervisor_nodes.py`, `run_agent_use_case.py`, `tracker.py`, `tool_registry.py` | 수정 완료 |
| 모델 레지스트리 | `domain/llm_model/`, `application/llm_model/`, `infrastructure/llm_model/`, `db/migration/V081__…` | 수정·신규 완료 |
| API·설정 | `api/main.py`, `api/routes/agent_builder_router.py`, `document_extractor_router.py`, `llm_model_router.py`, `config.py`, `.env.example`, `pyproject.toml` (openai·pillow 명시) | 수정 완료 |
| 프론트 | `types/imageGeneration.ts`, `utils/imageGeneration.ts`, `utils/llmModelKind.ts`, `components/chat/AuthenticatedImage.tsx`, `MarkdownRenderer.tsx`, `components/agent-builder/ImageGenerationConfigPanel*.tsx`, `pages/AgentBuilderPage`, `pages/AdminLlmModelsPage`, `services/documentExtractorService.ts` | 신규·수정 완료 |
| 백엔드 테스트 | `idt/tests/` 아래 domain·application·infrastructure·api·db 영역 | 완료 |
| 프론트 테스트 | `idt_front/src/` 아래 `*.test.tsx` 및 MSW handlers | 완료 |
| 문서 | Plan, Design v0.2, Analysis v0.3, 본 Report | 완료 |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 수동 E2E L1 (API 16건, Analysis §11) | 백엔드 서버와 `OPENAI_API_KEY` 없음. 프론트 dev server만 실행 | High | 반나절 |
| 수동 E2E L2 (UI 12건) | 위와 같음 | High | 반나절 |
| 수동 E2E L3 (시나리오 9건, Design §8.4) | 위와 같음. 승인 게이트·서브 에이전트·히스토리 재진입 포함 | High | 1일 |
| 커버리지 80% 측정 (SC-9) | 측정 기록 없음 | Medium | 1시간 |
| 디스크 정리 잡 | 산출물 영구 보관 정책 (Plan §5). 기존 문서 산출물과 같은 정책이므로 후속 과제 | Medium | 별도 |
| 코드 커밋·PR | 사용자 지시 없음. 현재 브랜치는 `feature/agent-run-turn-index-fix` (다른 기능과 같은 브랜치) | High | — |

### 4.2 Minor Gaps (Analysis §9, 미해결)

| ID | 내용 | Priority |
|----|------|----------|
| G-M1 | `image_generation_default_size` 설정을 읽는 곳이 없다. 설정을 요청 스키마 기본값에 쓰거나 항목을 삭제 | Low |
| G-M2 | 모델 수정에서 `validate_default_is_chat` 위반이 404로 나간다 (422가 맞음) | Low |
| G-M3 | 에이전트가 쓰는 chat 모델을 image로 바꾸는 것을 막지 않는다. 단가를 null로 되돌릴 수 없다 | Low |
| G-M5 | PIL 판독을 이벤트 루프에서 동기 실행한다. `Image.MAX_IMAGE_PIXELS` 전역 변경이 동시 요청에 안전하지 않다 | Medium |
| G-M6 | `image_generate_node`가 약 58줄이다 (40줄 규칙 초과) | Low |
| G-M7 | 서브 그래프에 첨부가 전달되지 않는다. 서브 상한이 부모 사용분을 빼지 않는다 | Medium |
| G-M8 | 승인 대기로 끝난 턴에서 게이트 전 이미지 링크가 빠진다 (재개 답변에는 붙는다) | Medium |
| G-M9 | D-11 근거가 틀렸다. draft LLM은 텍스트만 본다 | Low (설계 정정) |
| G-M10 | 재시도 대기가 고정 1초다 (설계는 지수 백오프) | Low (설계 정정) |
| G-M11 | auth_ctx와 subject_user_id가 모두 없으면 빈 owner로 저장된다 | Low |
| G-M12 | 설계 본문에 `tool_configs["image_generate"]` 표기가 남아 있다 | Low (설계 정정) |
| G-M13 | `_append_generated_images`가 `answer_links` 모듈 함수로 구현됐다 (동등 구현) | Low (설계 정정) |
| G-M14 | 평가·스윕·미들웨어·청킹 드롭다운은 chat 필터를 적용하지 않았다 | Low |

### 4.3 SOT·wiki 어긋남 (보고만, 수정하지 않음)

| 문서 | 위치 | 어긋남 |
|------|------|--------|
| `docs/SOURCE-OF-TRUTH.md` | 129행 (모델 레지스트리) | kind·단가·도구 항목이 없다 |
| `docs/wiki/backend/api/router-map.md` | 에이전트 라우터 | `image_generation` 필드와 422 코드 없음 |
| `docs/wiki/frontend/screens/admin-screens.md` | 33행 | 종류·단가 폼 설명 없음 |
| `docs/wiki/frontend/screens/chat-screens.md` | 채팅 말풍선 | 인라인 이미지 렌더 설명 없음 |

위키 갱신은 `/wiki update` 명시 호출 때만 한다.

---

## 5. Quality Metrics

### 5.1 Match Rate 변화

| Metric | Check 1차 (gap-detector) | Check 2차 (재채점) | Act-1 후 | Target |
|--------|:-----:|:-----:|:-----:|:-----:|
| Structural | 95 | 95 | 96 | — |
| Functional | 84 (프론트 미확인 0.5 처리) | 94 | 96 | — |
| API Contract | 82 | 82 | 95 | — |
| **Overall (정적 공식)** | 85 | 89 | **95** | 90 |
| Critical 결함 | 0 | 0 | 0 | 0 |
| Important 결함 | 4 | 4 | 0 | 0 |

산식: Overall = Structural×0.2 + Functional×0.4 + Contract×0.4. 런타임 항목을 넣지 않은 정적 산식이다. 런타임 포함 산식(Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35)은 Runtime을 측정하지 않아 쓰지 않았다. 95%는 정적 기준이며, E2E 결과에 따라 달라질 수 있다.

### 5.2 Regression 기록

| 영역 | 결과 | 판정 |
|------|------|------|
| 백엔드 전체 pytest (Do 중) | 11,020 passed / 53 failed. 실패는 master 상시 실패 목록과 파일·건수 일치 (pymupdf4llm 21, agent_builder_router_stream 9, parent_child_retriever 7, general_chat_router 7, collection_router_embedding 4, ws_router_auth_context 2, es_client, test_main, test_main_logging) | 기준선 동일 |
| 백엔드 대상 suite (Act-1 후: api, agent_builder, llm_model, multimodal, domain, image_generation) | 5,826 실행 / 상시 실패 24건 외 실패 0 | 통과 |
| 프론트 Vitest | 1,500 passed / 9 상시 실패 + 로드 플레이크 2건 (단독 실행 시 통과) | 기준선 동일 |
| tsc | 209 errors | 기준선 동일 (신규 0) |
| eslint | 신규 파일 0 (프로젝트 나머지 기존 오류는 그대로) | 충족 |
| verify-architecture / logging / tdd | 기능 범위 위반 0 | 충족 |

### 5.3 Gap Resolution (Act-1, 2026-11-02)

| Gap | 문제 | 수정 | 테스트 |
|-----|------|------|--------|
| G-I1 | 모델 부재 응답이 설계의 422가 아니라 404로 나갔다. 메시지 "찾을 수 없습니다"가 404 분기에 걸렸다 | `save_error_http_exception()` 신설. `IMAGE_MODEL_INVALID`·`IMAGE_CONFIG_INVALID`·`MODEL_KIND_MISMATCH` 접두어는 422. 생성·수정·스킬 부착 3곳에 적용 | `tests/api/test_agent_builder_save_errors.py` 5건 |
| G-I2 | 에이전트 모델에 이미지 모델을 넣으면 거부되지만 오류 코드가 없었다 | `require_chat_model` 메시지에 `MODEL_KIND_MISMATCH:` 접두어 추가. 프론트 `IMAGE_GENERATION_ERROR_CODES` 매핑 | `test_model_kind_policy`, `utils/imageGeneration.test.ts` |
| G-I3 | `.png`가 다운로드 media type 목록에 없어 `application/octet-stream`으로 나갔다 | `_MEDIA_TYPES`에 png·jpg·jpeg·webp 추가. 파일명 확장자는 실제 mime에 맞춤 (`output_filename(now, mime=)`) | `test_document_extractor_router` png 케이스, `TestOutputFilename.test_extension_follows_mime` |
| G-I4 | 에이전트 수정마다 이미지 모델을 재검증해, 이미지 모델이 비활성이면 무관한 수정도 막혔다 | `image_generation` 요청이 있을 때만 재검증 | `TestUpdateAgentImageGenerationRevalidation` 2건 |

남은 Minor 14건(§4.2)은 Act-1 대상이 아니었다. 이번 사이클에서 수정하지 않았다.

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **설계 정정을 Do 중에 기록했다.** `tool_configs`가 RAG 전용 스키마라는 사실을 module-3에서 발견했고, v0.2에서 전용 `image_generation` 필드로 바꿨다. 코드와 설계가 같은 결정을 가리키게 됐다.
- **기존 저장소와 라우터를 재사용했다.** 새 엔드포인트, 새 테이블 없이 DOCUMENT 저장소와 다운로드 라우터의 소유자 검증을 그대로 썼다.
- **답변 링크를 결정적으로 보존했다.** final_answer 프롬프트를 믿지 않고 `generated_images` 채널로 올린 뒤 종료 시 본문에 덧붙였다. 저장 본문에 남으므로 히스토리 재조회도 같은 결과를 낸다.

### 6.2 What Needs Improvement (Problem)

- **단위 테스트만으로 HTTP 상태 코드를 잡지 못했다.** 저장 검증은 UseCase 수준 테스트만 있어서 "찾을 수 없습니다" 문구가 404로 나가는 결함(G-I1)을 놓쳤다. 정적 분석에서야 발견됐다.
- **gap-detector 초안이 불완전했다.** 프론트 항목을 확인하지 못했고, 턴 한도(30턴)에 걸렸으며, 보고서를 쓸 Write 도구가 없었다. 메인 세션이 점수를 재채점하고 보고서를 직접 저장했다.
- **설계 문서 일괄 정정을 하지 않았다.** v0.2 정정 때 본문 표기 `tool_configs`를 다 바꾸지 않아서 G-M12가 남았다. D-11도 근거를 확인하지 않은 채 적었다.
- **환경 문제.** Bash heredoc에 한글과 따옴표가 섞이면 실패해서 Edit 도구로 바꿨다. 여러 미커밋 변경이 있는 워크트리에서 `git stash`를 쓰면 위험하다. 예전 stash 항목 때문에 회귀 오탐이 한 번 났다.

### 6.3 What to Try Next (Try)

- 라우터가 상태 코드를 바꾸는 계약은 TestClient 테스트를 설계 §8.2에 항목으로 넣고, 상태 코드를 단언한다.
- 설계를 정정할 때는 용어 전체를 grep해서 본문을 한 번에 고친다 (예: `grep "tool_configs"`).
- 서브 에이전트 보고서 작성은 Write 권한이 있는 메인 세션이 맡거나, 서브 에이전트에 보고서 저장 권한과 턴 여유를 준다.
- 워크트리에서 `git stash` 대신 브랜치 또는 임시 디렉터리로 격리한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 설계 전제(RAG 설정 스키마 재사용)를 확인하지 않음 | 기존 스키마 재사용을 가정하기 전에 해당 스키마를 열어 확인하는 항목을 Plan 체크리스트에 넣는다 |
| Design | 정정 시 본문 표기가 일부 남음 | 버전 올릴 때 용어 grep 체크를 넣는다 |
| Do | 프론트 테스트 근거가 Check에서 늦게 활용됨 | 모듈 완료 시 "기준 항목 ↔ 테스트 이름" 표를 만든다 |
| Check | gap-detector 턴 한도와 보고 도구 문제 | 보고 저장은 메인 세션이 맡는다. 점수 기준(프론트 unverified 처리)을 명시한다 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| Testing | 라우터 계약은 TestClient 상태 코드 테스트를 기본으로 | 상태 코드 결함을 Check 전에 발견 |
| Environment | 백엔드 서버와 `OPENAI_API_KEY`를 E2E용으로 준비 | 수동 E2E 9건 실행 가능 |
| Git | 워크트리 격리 방식 정리(브랜치 분리) | stash 사고 방지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 수동 E2E 실행: L1 (API 16건), L2 (UI 12건), L3 (시나리오 9건). 백엔드 기동 + `OPENAI_API_KEY` 필요. Analysis §11, Design §8.4 기준
- [ ] 커밋 (사용자 지시 시): 대상은 신규·수정 소스, 테스트, 문서. `.bkit/` 런타임 파일 제외. 현재 브랜치 `feature/agent-run-turn-index-fix`에 섞이지 않도록 브랜치 분리 여부 결정
- [ ] 설계 정정: §2.1·§2.2·§5.4 #7·§8.3 #7의 `tool_configs` 표기(G-M12), 메서드 PATCH(G-M4), D-11 근거(G-M9), 재시도 백오프(G-M10), `validate_default_is_chat` 추가, 에러 계약을 접두어 문자열로 정정(§6.2)
- [ ] `/pdca archive image-generation-tool` (커밋 후)
- [ ] `/wiki update` 호출 시: §4.3 SOT·wiki 어긋남 4건 반영

### 8.2 Follow-up (Minor, 우선순위 순)

| Item | Gap | Priority |
|------|-----|----------|
| PIL 판독을 스레드풀로 이동하고 픽셀 상한 검사를 분리 | G-M5 | Medium |
| 서브 그래프 첨부 전달, 서브 상한에서 부모 사용분 차감 | G-M7 | Medium |
| 승인 대기 턴에서 게이트 전 이미지 링크 유지 방식 결정 | G-M8 | Medium |
| 기본 크기 설정 사용 또는 설정 항목 삭제 | G-M1 | Low |
| 노드 함수 분리 (58줄 → 40줄 이하) | G-M6 | Low |
| 모델 수정 오류 상태 코드 정정 | G-M2 | Low |
| 사용 중 chat 모델의 kind 변경 방지 | G-M3 | Low |
| 빈 owner 방어 | G-M11 | Low |
| 평가·스윕·미들웨어·청킹 드롭다운 chat 필터 적용 여부 결정 | G-M14 | Low |
| 산출물 정리 잡 (디스크 증가 대응) | Plan §5 | Medium |
| 커버리지 80% 측정 | SC-9 | Medium |

### 8.3 Next PDCA Cycle

| Item | Priority | Note |
|------|----------|------|
| Gemini 또는 사내 호스팅 이미지 어댑터 | Low | 레지스트리 키만 열어 두었다. 실제 요구가 생기면 시작 |
| 이미지 편집 UI (마스크·크롭) | Low | Plan 범위 밖 |
| 생성 이미지를 KB에 저장 | Low | Plan 범위 밖 |

---

## 9. Changelog

### v1.0.0 (2026-11-02)

**Added:**
- 내부 도구 `image_generate` (TOOL_REGISTRY, category action)와 전용 합성 노드
- `domain/image_generation/`, `application/image_generation/`, `infrastructure/image_generation/` (OpenAI·호환 어댑터, provider 레지스트리)
- `llm_model.model_kind`, `llm_model.price_per_image_usd` (V081)
- 빌더 `ImageGenerationConfigPanel`, 채팅 인라인 `AuthenticatedImage`, 관리자 종류·단가 폼
- 설정 4종 (`IMAGE_GENERATION_*`)
- 턴당 상한, 서브 그래프 상한, 원장 기록 (`purpose=image_generation`)

**Changed:**
- `llm_model` 채팅·비전 드롭다운과 서버 저장 검증을 chat 종류로 제한
- 에이전트 저장 API에 `image_generation` 필드 추가
- `MarkdownRenderer`에 `img` 컴포넌트 추가
- `tracker`에 비용 override 추가

**Fixed (Act-1):**
- 모델 부재 응답이 404로 나가던 문제 (G-I1)
- `MODEL_KIND_MISMATCH` 오류 코드 누락 (G-I2)
- 생성 이미지 다운로드 media type 누락 (G-I3)
- 무관한 에이전트 수정이 이미지 모델 재검증으로 막히던 문제 (G-I4)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-02 | Completion report (Match 95%, 수동 E2E 미실행) | 배상규 + Claude |
