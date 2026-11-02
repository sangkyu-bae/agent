# image-generation-tool Planning Document

> **Summary**: 에이전트에 붙일 수 있는 내부 도구 `image_generate`를 추가한다. 사용자의 요청(텍스트, 또는 이번 턴에 첨부한 이미지 기반 편집)으로 관리자가 등록한 이미지 생성 모델(OpenAI gpt-image 계열, 어댑터 레지스트리로 확장 가능)을 호출해 이미지를 만들고, 영구 저장소에 보관해 답변 말풍선에 인라인으로 보여주며 다운로드를 제공한다. 비용은 장당 단가로 기존 원장에 합산한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-10-30
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트가 보여줄 수 있는 시각물은 코드로 렌더링하는 차트·문서뿐이다. "이런 이미지를 만들어 달라"는 요청을 받을 도구가 없고, 이미지 생성 API 호출은 코드베이스 어디에도 없다. |
| **Solution** | 내부 도구 `image_generate`(TOOL_REGISTRY 등록 + 전용 합성 노드)를 추가한다. LLM 모델 레지스트리에 "이미지 생성" 종류와 장당 단가를 두고, 에이전트 도구 설정에서 모델을 고른다. 생성 어댑터는 provider 키 레지스트리로 두되 이번엔 OpenAI(호환 base_url 포함)만 구현한다. 산출물은 문서 산출물과 같은 영구 저장소와 다운로드 경로를 쓴다. |
| **Function/UX Effect** | 사용자가 "제품 소개용 배너 이미지를 만들어 줘" 또는 이미지를 첨부하고 "배경을 흰색으로 바꿔 줘"라고 하면, 에이전트가 프롬프트를 조립해 생성하고 답변 안에 이미지가 바로 보인다. 클릭하면 다운로드된다. 히스토리 재조회에서도 보인다. |
| **Core Value** | "도구를 추가하면 에이전트가 그 도구로 라우팅해 실제 업무를 수행한다"는 플랫폼 원칙 그대로, 코어 변경 없이 도구 1개와 모델 등록만으로 이미지 생성 업무를 에이전트에 맡길 수 있다. |

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

## 1. Overview

### 1.1 Purpose

에이전트가 사용자의 요청으로 이미지를 생성하거나 첨부 이미지를 편집해 결과를 채팅 답변에 돌려줄 수 있게 한다.

### 1.2 Background

- `chat-image-attachment`(2026-10-30)로 이미지 **입력**은 가능해졌다. 출력(생성)은 없다. 저장소 전체에서 DALL·E, gpt-image, Imagen, Stable Diffusion 호출이 0건이다.
- 내부 도구 추가 절차는 `docs/rules/tool-and-mcp.md`에 고정되어 있다: `TOOL_REGISTRY` 등록 → `ToolFactory` 분기 또는 전용 합성 노드 → UI 노출은 부팅 시 `SyncInternalToolsUseCase` 자동.
- 산출 파일 패턴이 있다: 문서 생성 워커가 `AgentAttachmentStore`에 `AttachmentType.DOCUMENT`로 저장하고 `GET /api/v1/document-extractor/files/{file_id}`(소유자 검증)로 내려준다. 답변에는 `다운로드: [파일명](/api/v1/document-extractor/files/{id})` 마크다운 링크를 넣고, 프론트 `MarkdownRenderer`의 링크 컴포넌트가 인증 서비스로 다운로드한다.
- 모델 레지스트리(`llm_model`)는 provider·base_url·`supports_vision`(V064)·토큰 단가를 가진다. 이미지 모델은 종류 구분과 장당 단가가 없다.
- OpenAI SDK 2.54가 이미 설치되어 있다(langchain-openai 의존). `client.images.generate` / `client.images.edit` 호출이 가능하다.
- 비전 어댑터 레지스트리(`VisionAdapterRegistry`, provider 키 → 어댑터 팩토리)가 있어 같은 구조로 생성 어댑터 레지스트리를 둘 수 있다.

### 1.3 Related Documents

- `docs/rules/tool-and-mcp.md` (도구 추가 절차·체크리스트)
- `docs/wiki/backend/patterns/supervisor-graph-contracts.md` (워커 산출물 = AIMessage(name) 1건)
- `docs/wiki/backend/db/erd-document-tooling.md` (설정은 agent_tool.tool_config, 산출물 저장소)
- `idt/docs/archive/2026-08/multimodal-extractor/` (어댑터 레지스트리·supports_vision)
- `docs/02-design/features/chat-image-attachment.design.md` (첨부 이미지 dict 계약, 마커·누출 규칙)
- `docs/wiki/frontend/screens/chat-screens.md` (엑셀 산출 미리보기 트리거 패턴)

### 1.4 사용자 결정 기록 (2026-10-30)

| 결정 항목 | 선택 |
|-----------|------|
| 생성 모델 | OpenAI 이미지 API + provider 키 어댑터 레지스트리(이번엔 OpenAI·OpenAI 호환만 구현) |
| 모델 관리 | LLM 모델 레지스트리에 종류 플래그 추가, 에이전트 도구 설정에서 선택 |
| 산출물 보관 | 영구 보관 + 다운로드 링크(문서 산출물과 동일 경로) |
| 입력 범위 | 텍스트→이미지 + 이번 턴 첨부 이미지 기반 편집 |
| 답변 표시 | 인라인 이미지(인증 fetch→object URL) + 다운로드, 히스토리 재조회 동일 |
| 상한 | 호출당 1장, 기본 1024px, 턴당 최대 4장, 전부 설정값 |
| 비용 | `llm_model.price_per_image_usd` 추가, 생성 건수×단가를 ai_run 비용에 합산 |

---

## 2. Scope

### 2.1 In Scope

- [ ] DB: `llm_model`에 `model_kind`('chat' 기본 / 'image') 와 `price_per_image_usd` 추가 (V081, 전 컬럼 COMMENT)
- [ ] 도메인: `LlmModel` 엔티티·스키마·시드·관리자 CRUD에 두 필드 반영, 관리자 화면 LLM 모델 폼에 "종류"·"장당 단가" 입력
- [ ] 도메인: `ImageGenerationToolConfig` VO(모델 id·기본 크기·품질), `ImageGenerationPolicy`(크기 허용값·턴당 상한·프롬프트 길이·편집 입력 제약)
- [ ] 도메인 포트: `ImageGeneratorPort.generate(prompt, size, quality) -> bytes`, `.edit(prompt, image_bytes, mime, size) -> bytes`
- [ ] 인프라: `ImageGeneratorRegistry`(provider 키) + `OpenAIImageGenerator`(gpt-image 계열, base_url 존중, API 키는 `api_key_env`)
- [ ] 애플리케이션: `GenerateImageUseCase`(정책 검사 → 어댑터 호출 → 저장소 저장 → 결과 VO) 
- [ ] 애플리케이션: `TOOL_REGISTRY`에 `image_generate`(category action, requires_env 없음·모델의 api_key_env로 판정), `workflow_compiler` 전용 합성 노드(문서 생성 노드 패턴): LLM이 사용자 요청·대화 문맥에서 프롬프트·크기·편집 여부를 구조화 출력 → 유스케이스 호출 → AIMessage(name) 1건에 인라인 마커 + 다운로드 링크
- [ ] 편집: 이번 턴 `state.attachments`의 이미지(`file_path`,`mime`)를 입력으로 사용. 첨부가 없으면 생성으로 폴백하고 그 사실을 답변에 명시
- [ ] 턴당 상한: 상태에 생성 건수를 두고 상한 초과 시 도구가 거부 메시지 반환(실행 실패 아님)
- [ ] 비용: 생성 성공 시 `UsageCallback`과 같은 원장에 `image_count`·`cost_usd`(건수×단가) 기록, ai_run 총비용 합산, 사용량 화면 표시
- [ ] 답변 계약: `![파일명](/api/v1/document-extractor/files/{file_id})` 마크다운 이미지 + `다운로드: [파일명](...)` 링크
- [ ] 프론트: `MarkdownRenderer`에 `img` 컴포넌트 추가 — 산출 파일 경로면 인증 fetch 후 object URL로 렌더(로딩·실패 폴백·클릭 다운로드), 그 외 경로는 기본 렌더
- [ ] 프론트: 에이전트 빌더 도구 설정 패널 `ImageGenerationConfigPanel`(모델 드롭다운 = `model_kind==='image'` 활성 모델, 기본 크기·품질)
- [ ] 프론트: 관리자 LLM 모델 폼의 종류·장당 단가, 타입·서비스 동기화
- [ ] 테스트: 백엔드 pytest(정책·VO·어댑터(모킹)·유스케이스·노드·레지스트리·마이그레이션 COMMENT·비용), 프론트 Vitest(img 렌더·설정 패널·관리자 폼)

### 2.2 Out of Scope

- Gemini·사내 호스팅(Stable Diffusion 등) 어댑터 구현 (레지스트리 키만 열어 둔다)
- 마스크·크롭·주석 등 편집 UI, 다중 참조 이미지 합성
- 호출당 여러 장(n>1), 1536px 초과 해상도, 투명 배경 등 provider 고유 옵션 전부
- 생성 이미지의 KB·벡터 DB 저장, 이전 턴 생성 이미지를 다음 턴 편집 입력으로 자동 사용
- 생성 이미지 안전성 검수(정책 위반 판정은 provider 응답 오류를 그대로 안내)
- 산출물 정리 잡(기존 문서 산출물도 영구 보관·정리 잡 없음 — 동일 정책)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | V081: `llm_model.model_kind VARCHAR(16) NOT NULL DEFAULT 'chat'`, `price_per_image_usd DECIMAL(10,4) NULL`. 전 컬럼 COMMENT, COMMENT에 콤마 금지. 기존 행은 'chat' | High | Pending |
| FR-02 | `LlmModel` 엔티티·응답/요청 스키마·SQLAlchemy 모델·관리자 등록/수정 API·가격 수정 API가 두 필드를 다룬다. 채팅 모델 드롭다운(에이전트 모델 선택)은 `model_kind=='chat'`만, 비전 드롭다운도 'chat'만 노출 | High | Pending |
| FR-03 | `TOOL_REGISTRY["image_generate"]` 등록(name "이미지 생성", category action). 부팅 동기화로 tool_catalog에 `internal:image_generate` 노출. 손수 시드 금지 | High | Pending |
| FR-04 | `ImageGenerationToolConfig`: `llm_model_id`(필수, model_kind=image·활성 검증은 저장 시 UseCase), `default_size`(1024x1024 기본), `quality`(standard 기본). `WorkerDefinition.tool_config`에 dict로 저장 | High | Pending |
| FR-05 | `ImageGeneratorRegistry`: provider 키 → 어댑터 팩토리. `openai`·`openai_compatible` 등록. 미등록 provider는 명시 오류 | High | Pending |
| FR-06 | `OpenAIImageGenerator`: `images.generate(model, prompt, size, quality, n=1)` / `images.edit(model, image, prompt, size)`. base_url·api_key_env 존중. 429/5xx/타임아웃 1회 재시도(지수 백오프), 정책 위반 오류는 재시도 없이 사용자 안내 문구로 변환 | High | Pending |
| FR-07 | `GenerateImageUseCase.run(request) -> GeneratedImage`: 정책 검사(크기 허용값·프롬프트 길이·턴당 상한) → 어댑터 호출 → `AgentAttachmentStore.save(type=DOCUMENT, 파일명 `generated-{ts}.png`, owner=요청 사용자)` → `{file_id, filename, width, height, bytes, mime, model_id}` | High | Pending |
| FR-08 | 전용 노드 `image_generate_node`: 워커 LLM이 구조화 출력으로 `{prompt, size, mode: generate\|edit, source_image_index}`를 만든다. 사용자 원문·대화 문맥·첨부 이미지 목록(이름만)을 입력으로 준다. 프롬프트는 영어로 번역하지 않고 모델이 판단 | High | Pending |
| FR-09 | 편집 모드: `state.attachments` 중 `type=="image"`가 있어야 한다. 없으면 생성 모드로 폴백하고 답변에 "첨부 이미지가 없어 새로 생성했습니다"를 명시. 입력 이미지는 저장된 `file_path`에서 읽는다(턴 종료 전) | High | Pending |
| FR-10 | 턴당 상한: `SupervisorState.generated_image_count`(기본 0). 상한(`image_generation_max_per_turn`, 기본 4) 도달 시 노드가 AIMessage로 거부 사유를 반환하고 실행은 계속된다 | High | Pending |
| FR-11 | 산출물 AIMessage 본문 계약: `![{filename}](/api/v1/document-extractor/files/{file_id})` 한 줄 + `다운로드: [{filename}](/api/v1/document-extractor/files/{file_id})` + 사용한 프롬프트 요약 1줄. final_answer가 본문을 재작성해도 이 두 줄을 보존하도록 프롬프트 규범에 명시(문서 생성 워커와 동일 규범) | High | Pending |
| FR-12 | 비용: 생성 성공 1건당 `ai_run_step` 산출 메타에 `image_count=1`, `cost_usd = price_per_image_usd`를 기록하고 ai_run 총비용에 합산. 단가 미등록이면 0으로 기록하고 경고 로그 | Medium | Pending |
| FR-13 | 프론트 `MarkdownRenderer` `img`: src가 `/api/v1/document-extractor/files/`로 시작하면 인증 서비스로 blob을 받아 object URL로 렌더(로딩 스켈레톤·실패 시 다운로드 링크 폴백·클릭 시 다운로드). 그 외 src는 기본 `<img>`. object URL은 언마운트 시 해제 | High | Pending |
| FR-14 | 프론트 `ImageGenerationConfigPanel`: 모델 드롭다운(`model_kind==='image' && is_active`), 기본 크기(1024x1024·1536x1024·1024x1536), 품질(standard·hd). 에이전트 저장 payload의 tool_config로 전송. 문서 생성 패널과 같은 모달/패널 패턴 | High | Pending |
| FR-15 | 프론트 관리자 LLM 모델 폼: 종류(chat·image) 라디오, 장당 단가(USD) 입력(종류 image일 때만), 목록 열 표시. 타입·서비스·MSW 동기화 | Medium | Pending |
| FR-16 | 설정값: `image_generation_max_per_turn`(4), `image_generation_default_size`("1024x1024"), `image_generation_timeout_sec`(60), `image_generation_max_prompt_chars`(2000). `.env.example` 반영 | Medium | Pending |
| FR-17 | 승인 게이트·프롬프트 가드·메모리 주입 등 기존 미들웨어는 변경 없이 동작. 도구가 action 카테고리이므로 승인 게이트 대상이 될 수 있어야 한다(기존 게이트 설정으로) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 생성 1건 타임아웃 60초(설정). 노드는 비동기 호출, 저장은 스레드풀 | pytest(타임아웃 모킹) + 수동 측정 |
| Security | 산출물 다운로드는 소유자 검증(기존). 입력 이미지는 이번 턴 첨부(소유자 검증 완료)만. API 키는 env 이름만 저장(기존 규칙). 프롬프트에 첨부 경로 노출 금지 | pytest + 코드 리뷰 |
| Privacy | 생성 이미지 바이트는 저장소 파일에만. DB·로그·실행 이력에는 file_id·크기·모델만 | verify-logging + 계약 테스트 |
| Compatibility | 기존 도구·에이전트·채팅 회귀 0. `model_kind` 기본 'chat'으로 기존 모델 CRUD 무변경 | 전체 pytest/Vitest |
| Architecture | domain에 SDK 금지, 어댑터는 infrastructure, 노드·유스케이스는 application. 함수 40줄 | verify-architecture |
| DDL | 테이블·전 컬럼 COMMENT, `tests/db/test_migration_ddl_comments.py` 통과 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-17 구현 및 테스트 통과(TDD)
- [ ] 관리자가 gpt-image 모델을 종류 image·단가와 함께 등록 → 에이전트 빌더에서 `이미지 생성` 도구 부착·모델 선택 → 채팅 "배너 이미지 만들어 줘" → 답변에 이미지 인라인 + 다운로드 (수동 E2E)
- [ ] 이미지 첨부 + "배경을 흰색으로" → 편집 결과 표시 (수동 E2E)
- [ ] 턴당 5번째 생성 요청은 거부 사유 답변, 실행 실패 없음 (단위 테스트)
- [ ] ai_run 상세·사용량 화면에서 이미지 비용 합산 확인
- [ ] 히스토리 재조회에서 생성 이미지가 다시 보임, 토큰 만료 시 다운로드 링크 폴백
- [ ] 전체 pytest/Vitest 회귀 0(상시 실패 목록 동일), verify 스킬 3종 통과
- [ ] SOT·wiki 어긋남 보고

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] ruff·eslint 신규 오류 0, tsc 통과
- [ ] 마이그레이션 COMMENT 테스트 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 인증 헤더 때문에 마크다운 `<img>`가 401로 깨짐 | High | High | FR-13: `img` 컴포넌트가 인증 fetch → object URL. 실패 시 다운로드 링크 폴백. 테스트로 고정 |
| final_answer가 산출물 마크다운(이미지·링크)을 요약하며 지움 | High | Medium | 문서 생성 워커와 같은 "산출 링크 보존" 프롬프트 규범 + 단위 테스트. 필요 시 final_answer 후처리로 링크 재삽입 |
| 이미지 모델이 채팅 모델 드롭다운에 섞여 에이전트에 연결됨 | High | Medium | FR-02: 모든 채팅/비전 드롭다운이 `model_kind=='chat'`만 노출. 서버도 에이전트 저장 시 kind 검증 |
| OpenAI 이미지 API 파라미터가 모델별로 다름(gpt-image-1은 `quality: low/medium/high`, dall-e-3은 `standard/hd`) | Medium | High | 어댑터가 모델명으로 파라미터 매핑. 정책 VO는 추상 값(standard/hd)만 받고 어댑터가 번역. 모킹 테스트로 매핑 고정 |
| 턴당 상한을 state로 세면 서브에이전트 그래프는 별도 state라 우회 가능 | Medium | Medium | 서브 그래프 컴파일 시 부모 상한의 절반을 전달(반복 한도와 같은 규칙) |
| 영구 보관으로 디스크 증가(정리 잡 없음) | Medium | Medium | 기존 문서 산출물과 동일 정책. 리포트에 정리 잡 후속 과제로 명시 |
| 편집 입력이 첨부 파일 경로를 읽는데 턴 종료 cleanup과 경합 | Medium | Low | 노드는 같은 턴 안(그래프 실행 중)에서만 읽는다. cleanup은 stream 종료 finally |
| 비용 원장 스키마가 토큰 기준이라 이미지 건수 필드가 없음 | Medium | Medium | ai_run_step 메타에 기록 + ai_run `cost_usd`에만 합산(원장 테이블 스키마 변경 없음). 설계에서 확정 |
| 프롬프트 가드가 이미지 생성 프롬프트(사용자 원문)를 검사하지 않음 | Low | Medium | 사용자 원문은 이미 그래프 전 가드를 통과. 모델이 만든 프롬프트는 provider 정책에 위임 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `llm_model` 테이블 | DB Model | `model_kind`, `price_per_image_usd` 추가(V081) |
| `src/domain/llm_model/entity.py`, `application/llm_model/schemas.py`, `infrastructure/llm_model/{models,repository,seed}.py` | Domain/App/Infra | 두 필드 반영 |
| `src/api/routes/llm_model_router.py` 응답/요청 | API Schema | additive 필드 |
| `src/domain/agent_builder/tool_registry.py` | Domain | `image_generate` 등록 |
| `src/domain/image_generation/` (신규) | Domain | VO·정책·포트·예외 |
| `src/application/image_generation/` (신규) | Application | `GenerateImageUseCase`, 레지스트리 |
| `src/application/agent_builder/workflow_compiler.py` | Application | 전용 노드 분기 + 서브 그래프 상한 전달 |
| `src/application/agent_builder/supervisor_state.py`, `supervisor_nodes.build_initial_state` | Application | `generated_image_count` 키 |
| `src/infrastructure/image_generation/` (신규) | Infra | `OpenAIImageGenerator` |
| `src/api/main.py`, `config.py`, `.env.example` | DI/Config | 레지스트리·유스케이스 주입, 설정 4종 |
| 비용 집계(`agent_run` UsageCallback/cost_calculator) | Application | 이미지 건수×단가 합산 경로 |
| `idt_front/src/types/llmModel.ts`, `AdminLlmModelsPage` | FE | 종류·단가 |
| `idt_front/src/components/chat/MarkdownRenderer.tsx` | FE | `img` 컴포넌트 |
| `idt_front/src/components/agent-builder/ImageGenerationConfigPanel.tsx` (신규) + 빌더 페이지 배선 | FE | 도구 설정 |
| `idt_front/src/utils/agentToolPayload.ts`, 에이전트 타입 | FE | tool_config 직렬화 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `llm_model` 행 | READ | 에이전트 모델 드롭다운, 비전 드롭다운, 비용 계산기, 시드 | Needs verification (kind 필터 추가, 기본 'chat'으로 기존 동작 동일) |
| `LlmModel` 생성/수정 API | CREATE/UPDATE | 관리자 화면, 테스트 | None (옵셔널 필드) |
| `TOOL_REGISTRY` | READ | `SyncInternalToolsUseCase`, ToolFactory, 컴파일러, `/agents/tools` | None (항목 추가) |
| `workflow_compiler` 워커 분기 | READ | 모든 에이전트 컴파일 | Needs verification (새 tool_id 분기만 추가) |
| `SupervisorState` 키 | READ | 모든 노드, 승인 스냅샷 직렬화 | None (키 추가, get 기본값) |
| `AgentAttachmentStore` DOCUMENT 타입 | CREATE/READ | 문서 생성·추출·블루프린트, 다운로드 라우터 | None (같은 타입 재사용) |
| `MarkdownRenderer` | READ | 모든 어시스턴트 말풍선 | Needs verification (`img` 컴포넌트 추가가 기존 마크다운 렌더에 영향 없어야 함) |
| 승인 스냅샷 `redact_messages` | READ | approval_request | None (산출물은 링크 텍스트) |

### 6.3 Verification

- [ ] 위 소비자 전부 회귀 테스트
- [ ] 에이전트 저장 시 채팅 모델 kind 검증이 기존 에이전트 수정 흐름을 막지 않음
- [ ] 다운로드 라우터 소유자 검증이 생성 이미지에도 그대로 적용

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (기존 Thin DDD 유지) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 도구 실행 형태 | ToolFactory react 도구 / 전용 합성 노드 | 전용 합성 노드 | 구조화 출력(프롬프트·모드)과 저장·상한 제어가 필요. 문서 생성 워커와 동일 |
| 어댑터 구조 | 단일 OpenAI 클래스 / provider 키 레지스트리 | 레지스트리 | 사용자 결정. 비전 어댑터와 같은 확장 지점 |
| 모델 구분 | 별도 테이블 / `llm_model.model_kind` | `model_kind` 컬럼 | 관리자 화면·단가·api_key_env 재사용. 비전 플래그와 같은 additive 방식 |
| 산출물 저장 | 첨부 저장소 TTL / DOCUMENT 영구 | DOCUMENT 영구 | 사용자 결정. 다운로드 라우터 재사용 |
| 인라인 표시 | 토큰 쿼리 공개 URL / 인증 fetch→object URL | 인증 fetch | 토큰을 URL에 노출하지 않음 |
| 편집 입력 | 이전 턴 산출물 자동 / 이번 턴 첨부만 | 이번 턴 첨부만 | 첨부 수명과 일치, 범위 최소 |
| 비용 | 원장 스키마 확장 / ai_run 비용 합산 + step 메타 | 후자 | 스키마 변경 최소. 설계에서 확정 |

### 7.3 Clean Architecture Approach

```
domain/image_generation/      VO(ImageSize, Quality, GenerationMode), ImageGenerationPolicy, ImageGenerationToolConfig,
                              ImageGeneratorPort, 예외 (SDK 금지)
application/image_generation/ GenerateImageUseCase, ImageGeneratorRegistry
application/agent_builder/    workflow_compiler 전용 노드, state 키, 서브 그래프 상한 전달
infrastructure/image_generation/ OpenAIImageGenerator (openai SDK), 모델별 파라미터 매핑
infrastructure/llm_model/     model_kind·price_per_image_usd 컬럼
api/                          main.py DI, llm_model_router 필드, (다운로드 라우터 재사용)
```

---

## 8. 열린 질문 (Design 단계에서 확정)

1. 구조화 출력의 모델: 워커 LLM(에이전트 채팅 모델)이 프롬프트를 만들고 이미지 모델이 생성한다. 비전 지원 채팅 모델이면 첨부 이미지를 보고 편집 프롬프트를 더 정확히 만들 수 있다 — 첨부 전달 여부를 어떻게 결정할지.
2. ai_run 비용 합산의 정확한 지점(UsageCallback 확장 vs 노드가 tracker에 직접 기록).
3. 히스토리 재조회 시 어시스턴트 메시지 본문의 마크다운 이미지가 그대로 저장되는지(저장 content가 final_answer 본문인지 확인).
4. gpt-image 계열 응답 포맷(b64_json 고정 여부)과 dall-e-3 호환 범위.
