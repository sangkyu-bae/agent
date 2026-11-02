# image-generation-tool Design Document

> **Summary**: 내부 도구 `image_generate`를 전용 합성 노드로 추가한다. 관리자가 `llm_model`에 종류 `image`·장당 단가로 등록한 모델을 에이전트 도구 설정에서 고르고, 노드는 워커 LLM의 구조화 출력(프롬프트·크기·모드)으로 provider 어댑터를 호출해 이미지를 만든 뒤 문서 산출물 저장소에 영구 보관한다. 결과는 `generated_images` 상태 채널로 올라가 답변 본문에 마크다운 이미지로 결정적으로 덧붙고, 비용은 토큰 0·단가 1건의 LLM 호출 행으로 기존 원장에 합산된다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-10-30
> **Status**: Draft
> **Planning Doc**: [image-generation-tool.plan.md](../../01-plan/features/image-generation-tool.plan.md)
> **Selected Architecture**: Option C — 실용 절충 (Checkpoint 3, 2026-10-30)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema — V081 (본 문서 §3.3) | ✅ |
| Phase 4 | API Spec — 본 문서 §4 | ✅ |

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

### 1.1 Design Goals

1. 도구 추가 절차(`docs/rules/tool-and-mcp.md`)만 따르면 UI 노출·라우팅·실행이 끝난다. 코어(supervisor·final_answer 프롬프트)는 건드리지 않는다.
2. 산출물·다운로드·소유자 검증은 문서 산출물 경로를 그대로 쓴다. 새 엔드포인트를 만들지 않는다.
3. 링크 유실·상한·비용은 상태 채널 1개와 LLM 호출 행 재사용으로 결정적으로 보장한다.
4. provider 추가 = 어댑터 파일 1개 + `register()` 1줄.

### 1.2 Design Principles

- 이미지 바이트는 저장소 파일에만 존재한다. 상태·메시지·로그·원장에는 `file_id`와 메타만 둔다(chat-image-attachment §7과 같은 규칙).
- 정책 VO는 추상 값(size 프리셋, quality `standard|hd`)만 다루고 provider 파라미터 번역은 어댑터가 한다.
- 노드 실패는 안내 AIMessage로 돌려 그래프를 끊지 않는다(문서 생성 워커 D9 동형).
- 이미지 모델은 채팅 모델과 같은 테이블에 두되 `model_kind`로 분리하고, 채팅·비전 드롭다운은 `chat`만 본다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 항목 | A. 최소 변경 | B. 클린 분리 | **C. 실용 절충 (선택)** |
|---|---|---|---|
| 도구 형태 | ToolFactory LangChain 도구 | 전용 노드 + 별도 바운디드 컨텍스트 | 전용 합성 노드 |
| 산출물 | DOCUMENT 저장소 | 새 테이블 + 전용 API + 메시지 컬럼 | DOCUMENT 저장소·기존 다운로드 |
| 링크 보존 | final_answer에 맡김 | 메시지 컬럼 | `generated_images` 채널 + 종료 시 결정적 덧붙임 |
| 턴당 상한 | 없음 | 상태 채널 | 상태 채널(서브 그래프 절반) |
| 비용 | 미집계 | 새 원장 | LLM 호출 행(토큰 0·단가) |
| DB 변경 | 0 | 테이블 2 + 컬럼 | 컬럼 2 |

### 2.1 Component Diagram

```
[관리자]  AdminLlmModelsPage ── POST/PUT /api/v1/llm-models (model_kind, price_per_image_usd)
[소유자]  AgentBuilderPage ── ImageGenerationConfigPanel ── tool_configs["image_generate"] = {llm_model_id, default_size, quality}
[이용자]  ChatPage ── WS subscribe ("배너 만들어 줘" [+ 이미지 첨부])
                                       │
                                       ▼
RunAgentUseCase ─ WorkflowCompiler.compile
   └─ worker tool_id == "image_generate" → _create_image_generate_node (문서 생성 노드 동형, ToolFactory 미경유)
         image_generate_node(state):
           1. ImageGenerationPolicy.check_turn_cap(state.generated_image_count)   → 초과면 안내 AIMessage
           2. 워커 LLM 구조화 출력 ImageRequestDraft{prompt, size, quality, mode, source_index}
              (입력: 사용자 원문 + 대화 문맥 + 첨부 이미지 이름 목록 + worker_context_block)
           3. GenerateImageUseCase.run(GenerateImageCommand)
                ├─ ImageGenerationPolicy.validate(prompt, size, quality)
                ├─ mode=edit → state.attachments[image][source_index].file_path 읽기 (없으면 generate 폴백)
                ├─ ImageGeneratorRegistry.build(provider=llm_model.provider, llm_model) → ImageGeneratorPort
                ├─ port.generate / port.edit  (타임아웃·재시도)
                ├─ AgentAttachmentStore.save(type=DOCUMENT, "generated-<ts>.png", owner)
                └─ tracker.record_llm_call(purpose=image_generation, token 0, cost=단가)   ← 비용
           4. return {messages:[AIMessage(name=worker)], generated_images:[...], generated_image_count:+1}
                                       │
                                       ▼
   final_answer (기존) → RunAgentUseCase._append_generated_images(answer, state.generated_images)
                         → ANSWER_COMPLETED payload + conversation_message.content (마크다운 이미지 포함)
                                       │
[프론트] MarkdownRenderer.img ── src 가 /api/v1/document-extractor/files/ 면 인증 fetch → object URL → <img>
                                 클릭 → documentExtractorService.downloadGeneratedFile
```

### 2.2 Data Flow

1. 관리자가 모델을 `model_kind=image`, `price_per_image_usd`와 함께 등록한다(`api_key_env`·`base_url` 기존 필드).
2. 소유자가 빌더에서 `이미지 생성` 도구를 붙이고 설정 패널에서 모델·기본 크기·품질을 고른다. `tool_configs`로 저장된다.
3. 채팅 요청 → supervisor가 도구 설명으로 `image_generate` 워커로 라우팅한다.
4. 노드가 상한을 확인하고, 워커 LLM이 `ImageRequestDraft`를 구조화 출력한다. 첨부 이미지가 있고 사용자가 편집을 원하면 `mode=edit`.
5. 유스케이스가 정책 검사 → 어댑터 호출 → 저장 → 원장 기록 → `GeneratedImage` 반환.
6. 노드가 AIMessage(본문: 완료 안내 + `![..](..)` + `다운로드: [..](..)` + 프롬프트 요약)와 상태 채널을 갱신한다.
7. final_answer가 답변을 만들면 유스케이스가 `generated_images`를 보고 본문에 없는 이미지의 마크다운 줄을 끝에 덧붙인다.
8. 프론트가 마크다운 이미지를 인증 fetch로 그린다. 히스토리 재조회 시 저장 본문에 같은 마크다운이 있어 동일하게 그린다.

### 2.3 Dependencies

| 의존 | 상태 | 비고 |
|------|------|------|
| `openai` SDK 2.54 | 설치됨(전이) | `pyproject.toml`에 `openai>=1.60` 명시 추가(이미지 API `images.generate/edit`) |
| `AgentAttachmentStore` DOCUMENT 타입·`GET /api/v1/document-extractor/files/{id}` | 존재 | 재사용 |
| `RunTracker.record_llm_call` | 존재 | purpose 값 1개 추가 |
| `LlmModel` 레지스트리·관리자 화면 | 존재 | 컬럼 2개 추가 |
| `IterationLimitPolicy.sub_agent_limit` 패턴 | 존재 | 상한 절반 전달에 재사용 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/image_generation/value_objects.py
class ImageSize(StrEnum):            # provider 공통 프리셋 (어댑터가 번역)
    SQUARE_1024 = "1024x1024"
    LANDSCAPE_1536 = "1536x1024"
    PORTRAIT_1536 = "1024x1536"

class ImageQuality(StrEnum):
    STANDARD = "standard"
    HD = "hd"

class GenerationMode(StrEnum):
    GENERATE = "generate"
    EDIT = "edit"

@dataclass(frozen=True)
class GenerateImageCommand:
    prompt: str
    size: ImageSize
    quality: ImageQuality
    mode: GenerationMode
    source_image: SourceImage | None        # (file_path, mime, file_name) — edit 일 때
    owner_user_id: str
    request_id: str

@dataclass(frozen=True)
class GeneratedImage:
    file_id: str
    filename: str
    width: int
    height: int
    mime: str                                # "image/png"
    model_id: str
    model_name: str
    provider: str
    prompt: str
    mode: GenerationMode
    elapsed_ms: int
    fell_back_to_generate: bool              # edit 요청인데 첨부가 없어 생성으로 폴백

# domain/image_generation/tool_config.py (DocumentExtractorToolConfig 패턴)
@dataclass(frozen=True)
class ImageGenerationToolConfig:
    llm_model_id: str                        # model_kind == "image" (저장 시 UseCase 가 검증)
    default_size: str = "1024x1024"
    quality: str = "standard"
    def __post_init__(...)                   # 빈 id, 미허용 size/quality → ValueError
    def model_dump(self) -> dict

# domain/image_generation/schemas.py — LLM 출력 전용 (strict structured output)
class ImageRequestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(description="생성 모델에 보낼 프롬프트. 사용자 요청의 의도·스타일·텍스트를 구체적으로")
    size: Literal["1024x1024", "1536x1024", "1024x1536"]
    quality: Literal["standard", "hd"]
    mode: Literal["generate", "edit"]
    source_image_index: int | None = Field(description="edit 일 때 첨부 이미지 순번(0부터). 아니면 null")
    reason: str = Field(description="왜 이 모드·크기를 골랐는지 한 줄")
```

```python
# domain/image_generation/policies.py (순수)
class ImageGenerationPolicy:
    MAX_PROMPT_CHARS (설정 주입), MAX_PER_TURN (설정 주입)
    @staticmethod validate_prompt(prompt, max_chars) -> str        # 공백 정리, 빈 값·초과 → InvalidImageRequestError
    @staticmethod check_turn_cap(count, max_per_turn) -> None      # 초과 → ImageTurnCapExceededError
    @staticmethod resolve_mode(requested, has_attachment) -> (GenerationMode, fell_back: bool)
    @staticmethod sub_agent_cap(parent_cap) -> int                 # max(1, parent // 2)
    @staticmethod output_filename(now) -> str                      # "generated-YYYYmmdd-HHMMSS-<6hex>.png"

# domain/image_generation/interfaces.py
class ImageGeneratorPort(Protocol):
    provider: str
    async def generate(self, *, prompt, size: ImageSize, quality: ImageQuality) -> ImageBytes   # (data, width, height, mime)
    async def edit(self, *, prompt, source: bytes, source_mime, size: ImageSize) -> ImageBytes

# domain/image_generation/exceptions.py
ImageGenerationError(base) → InvalidImageRequestError, ImageTurnCapExceededError,
UnsupportedImageProviderError, ImageModelNotConfiguredError, ImageProviderError(retryable: bool, user_message: str)
```

### 3.2 Entity Relationships

- `WorkerDefinition.tool_config`(dict) ↔ `ImageGenerationToolConfig` (asdict). 에이전트당 도구 1개 = 모델 1개.
- `tool_config.llm_model_id` → `llm_model.id` (소프트 참조. 저장 시 존재·`is_active`·`model_kind=='image'` 검증, 실행 시 재검증 후 없으면 안내 AIMessage).
- `GeneratedImage.file_id` → `AgentAttachmentStore` DOCUMENT 파일(owner = 요청 사용자). 다운로드는 기존 라우터의 소유자 검증.
- `SupervisorState.generated_images: list[dict]` (`{"file_id","filename","mime","width","height","prompt","mode"}`), `generated_image_count: int`, `image_generation_max_per_turn: int`.
- 원장: `ai_llm_call` 1행/생성 (`purpose="image_generation"`, `token_usage` 전부 0, `cost_usd = price_per_image_usd`, `model_name = 이미지 모델명`).

### 3.3 Database Schema

```sql
-- V081__add_model_kind_and_image_price_to_llm_model.sql
-- image-generation-tool Design §3.3: 이미지 생성 모델을 같은 레지스트리에 두되 종류로 구분한다.
-- ⚠️ COMMENT 안에 콤마 금지 (tests/db/test_migration_ddl_comments.py).
ALTER TABLE llm_model
  ADD COLUMN model_kind VARCHAR(16) NOT NULL DEFAULT 'chat'
  COMMENT '모델 종류 — chat(대화·비전) 또는 image(이미지 생성). 채팅 드롭다운은 chat 만 노출'
  AFTER supports_vision,
  ADD COLUMN price_per_image_usd DECIMAL(10,4) NULL
  COMMENT '이미지 생성 1장당 USD 단가 — model_kind=image 일 때만 사용하며 비용 원장에 합산'
  AFTER output_price_per_1k_usd;
```

SQLAlchemy `LlmModelModel`에 `comment=` 동일 반영. 시드 모델은 전부 `chat`(백필 없음). 관리자가 이미지 모델을 직접 등록한다.

### 3.4 상태·메시지 계약

노드 산출 AIMessage 본문(워커 산출물 1건 규칙):
```
이미지 생성 완료 (generated-20261030-153012-a1b2c3.png, 1024x1024)
![generated-20261030-153012-a1b2c3.png](/api/v1/document-extractor/files/<file_id>)
다운로드: [generated-20261030-153012-a1b2c3.png](/api/v1/document-extractor/files/<file_id>)
프롬프트: <prompt 앞 120자>
(첨부 이미지가 없어 새로 생성했습니다)   ← 폴백 시에만
```

최종 답변 후처리(`RunAgentUseCase._append_generated_images`): `state.generated_images` 각 항목의 `file_id`가 답변 본문에 없으면 끝에 빈 줄 + `![filename](/api/v1/document-extractor/files/<file_id>)` 를 덧붙인다. 저장 본문·ANSWER_COMPLETED payload 모두 이 후처리 결과를 쓴다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 | 설명 |
|--------|------|------|------|
| POST/PUT | `/api/v1/llm-models`, `/api/v1/llm-models/{id}` | 요청·응답 필드 추가 | `model_kind`(기본 `chat`), `price_per_image_usd`(옵셔널) |
| PUT | `/api/v1/llm-models/{id}/pricing` | 요청 필드 추가 | `price_per_image_usd` |
| GET | `/api/v1/llm-models` | 응답 필드 추가 | 두 필드 노출(additive) |
| GET | `/api/v1/tool-catalog` | 변경 없음 | 부팅 동기화로 `internal:image_generate` 노출 |
| POST/PUT | 에이전트 생성·수정(`tool_configs`) | 검증 추가 | `image_generate` 설정의 `llm_model_id`가 활성 `image` 모델인지 → 422 `IMAGE_MODEL_INVALID` |
| GET | `/api/v1/document-extractor/files/{file_id}` | 변경 없음 | 생성 이미지 다운로드(소유자 검증 기존) |

### 4.2 Detailed Specification

**LlmModel 응답(additive)**
```json
{ "...": "...", "supports_vision": false, "model_kind": "image", "price_per_image_usd": "0.0400" }
```
Decimal은 기존 가격 필드처럼 JSON 문자열.

**에이전트 저장 시 이미지 생성 설정 (v0.2 정정)**

`tool_configs` 는 RAG 설정 스키마 전용이라, 발표자료 설정과 같은 방식으로 **전용 요청 필드**로 받는다.
```json
{ "tool_ids": ["internal:image_generate", "..."],
  "image_generation": { "llm_model_id": "…", "default_size": "1024x1024", "quality": "standard" } }
```
서버는 `apply_image_generation_config()` 로 `image_generate` 워커의 tool_config 에 주입하고, `validate_image_generation_model()` 로 모델이 활성 `image` 종류인지 검증한다. 수정 요청에서 `image_generation: null`(생략)은 "변경 안 함"이다.
서버 검증 실패:
| Status | code | 조건 |
|---|---|---|
| 422 | `IMAGE_MODEL_INVALID` | 모델 없음 / 비활성 / `model_kind != image` |
| 422 | `IMAGE_CONFIG_INVALID` | size·quality 미허용 값 |

**채팅 모델 선택 제약**: 에이전트 `llm_model_id`·서브에이전트·관리자 멀티모달 비전 모델은 `model_kind == chat`만 허용. 서버 422 `MODEL_KIND_MISMATCH`, 프론트 드롭다운은 `chat`만 노출.

### 4.3 서버 내부 계약

```python
# application/image_generation/use_case.py
class GenerateImageUseCase:
    def __init__(self, registry: ImageGeneratorRegistry, llm_model_repo, store: AttachmentStoreInterface,
                 llm_factory_unused=None, tracker: RunTracker | None, logger, *, max_prompt_chars: int, timeout_sec: int)
    async def run(self, cmd: GenerateImageCommand, *, llm_model_id: str, run_ctx: RunContext | None) -> GeneratedImage
      # 1 정책 검사 2 모델 로드(kind=image·active) 3 어댑터 build 4 generate/edit (asyncio.wait_for)
      # 5 store.save(DOCUMENT) 6 tracker.record_llm_call(purpose=IMAGE_GENERATION, token 0) 7 GeneratedImage

# application/image_generation/registries.py
class ImageGeneratorRegistry:   # VisionAdapterRegistry 동형: register(factory, keys=None) / supported() / build(provider, llm_model, logger)

# infrastructure/image_generation/openai_image_generator.py
class OpenAIImageGenerator(ImageGeneratorPort):
    provider = "openai"      # keys=("openai", "openai_compatible") 로 등록
    # AsyncOpenAI(api_key=os.environ[llm_model.api_key_env], base_url=llm_model.base_url or None)
    # generate: images.generate(model, prompt, size, quality=_quality_param(model_name, quality), n=1, [response_format="b64_json" if dall-e])
    # edit:     images.edit(model, image=(filename, bytes, mime), prompt, size, n=1)
    # 429/5xx/timeout 1회 재시도(지수 백오프). content_policy_violation → ImageProviderError(retryable=False, user_message="요청이 생성 정책에 걸려 거부되었습니다…")
    # 응답 b64_json → bytes, PIL 로 width/height 판독(이미지 포맷 검증 겸함)

# domain/agent_run/value_objects.py
RunPurpose.IMAGE_GENERATION = "image_generation"
```

`_quality_param` 매핑: gpt-image 계열 `standard→"medium"`, `hd→"high"`; dall-e-3 `standard→"standard"`, `hd→"hd"`; 그 외 모델명은 품질 인자 생략.

**workflow_compiler**
```python
# compile 워커 분기 (document_generator 와 나란히)
if worker_def.tool_id == "image_generate":
    node = self._create_image_generate_node(llm, worker_def, auth_ctx=auth_ctx, request_id=request_id,
                                            worker_context_block=..., run_id=run_id)
    function_node_ids.add(worker_def.worker_id)   # 함수형 노드 등록 (wiki: 누락 시 AttributeError)

def _create_image_generate_node(...):
    # 1 ImageGenerationToolConfig(**tool_config) — 실패 → 안내 reply
    # 2 cap = state.get("image_generation_max_per_turn", settings 기본) ; count = state.get("generated_image_count", 0)
    #   ImageGenerationPolicy.check_turn_cap → 초과 시 reply("이번 대화 턴의 이미지 생성 상한(N장)에 도달했습니다…")
    # 3 draft = llm.with_structured_output(ImageRequestDraft).ainvoke(_build_image_request_messages(state, worker_context_block, attachments_names))
    # 4 mode, fell_back = resolve_mode(draft.mode, has image attachment); source = attachments[idx] if edit
    # 5 result = await use_case.run(cmd, llm_model_id=config.llm_model_id, run_ctx=get_current_run_context())
    #   예외(ImageGenerationError) → reply(user_message) ; 그 외 → logger.error(exception=e) + reply("이미지 생성 실패: …")
    # 6 return {"messages":[AIMessage(_render_image_summary(result), name=worker)], "last_worker_id": worker_id,
    #           "token_usage": state["token_usage"] + len(prompt)//4,
    #           "generated_images": [*state.get("generated_images", []), result_dict],
    #           "generated_image_count": count + 1}
```

서브에이전트: `_wrap_sub_agent`의 `build_initial_state(...)`에 `image_generation_max_per_turn=ImageGenerationPolicy.sub_agent_cap(parent_cap)`를 넘기고, 서브 결과의 `generated_images`를 부모 out에 합치며 `generated_image_count`도 더한다.

**RunAgentUseCase**: `_StreamState.generated_images` 수집(chain_end 출력에서 `generated_images` 키, charts와 동형) → `_append_generated_images(answer, images)` → ANSWER_COMPLETED payload·저장 본문에 적용. 승인 재개 경로(`_resume_graph`)도 같은 후처리.

---

## 5. UI/UX Design

### 5.1 Screen Layout

**채팅 답변(어시스턴트 말풍선)**
```
배너 이미지를 만들었습니다. 흰 배경에 "가을 정기예금 특판" 문구가 들어간 …
┌──────────────────────────┐
│  [생성 이미지 1024×1024]    │  ← 인증 fetch → object URL. 로딩 중 회색 스켈레톤
└──────────────────────────┘
generated-20261030-153012-a1b2c3.png  (클릭 → 다운로드)
```
실패(401·404·네트워크): 이미지 자리에 "이미지를 불러오지 못했습니다 — 다운로드" 링크.

**에이전트 빌더 도구 설정 패널 (`ImageGenerationConfigPanel`)**
```
이미지 생성 설정
  모델        [▼ gpt-image-1 (OpenAI)        ]   ← model_kind==='image' && is_active
  기본 크기   (●) 1024×1024  ( ) 1536×1024 가로  ( ) 1024×1536 세로
  품질        (●) 표준  ( ) 고품질
  안내: 단가 $0.04/장 · 턴당 최대 4장 (서버 설정)
```
이미지 모델이 하나도 없으면 "관리자 > LLM 모델에서 종류 '이미지 생성' 모델을 먼저 등록하세요" 안내와 저장 차단.

**관리자 LLM 모델 폼**: 종류 라디오(대화 / 이미지 생성) — 이미지 선택 시 비전·토큰 단가 입력을 숨기고 "장당 단가(USD)" 입력 표시. 목록에 종류 배지.

### 5.2 User Flow

1. 관리자 등록 → 2. 소유자 도구 부착·모델 선택·저장(422 시 필드 오류 표시) → 3. 이용자 요청(선택: 이미지 첨부) → 4. 답변에 이미지 인라인 → 5. 클릭 다운로드 → 6. 히스토리 재진입 시 동일 표시.

### 5.3 Component List

| 컴포넌트 | 변경 | 책임 |
|---|---|---|
| `components/chat/MarkdownRenderer.tsx` | 수정 | `img` 컴포넌트: 산출 파일 경로면 `AuthenticatedImage`로 위임 |
| `components/chat/AuthenticatedImage.tsx` (신규) | 신규 | `documentExtractorService.fetchGeneratedFileBlob(fileId)` → object URL, 로딩·실패 폴백, 언마운트 해제, 클릭 다운로드 |
| `services/documentExtractorService.ts` | 수정 | `fetchGeneratedFileBlob(fileId): Promise<Blob>` 추가(기존 download 재사용 가능 여부 확인) |
| `components/agent-builder/ImageGenerationConfigPanel.tsx` (신규) + Modal | 신규 | 설정 폼(문서 생성 패널 패턴) |
| `pages/AgentBuilderPage/index.tsx` | 수정 | 도구 선택 시 패널 배선, `buildToolConfigsForSave`에 병합, 제거 시 설정 삭제 |
| `types/imageGeneration.ts` (신규) | 신규 | `IMAGE_GENERATE_TOOL_ID = 'internal:image_generate'`, `ImageGenerationToolConfig`, size/quality `as const` |
| `types/llmModel.ts`, `AdminLlmModelsPage` | 수정 | `model_kind`, `price_per_image_usd` |
| `hooks/useLlmModels.ts` | 확인 | 필터는 호출 측에서(`model_kind`) |
| `__tests__/mocks/handlers.ts` | 수정 | llm-models 응답에 두 필드 |

### 5.4 Page UI Checklist

- [ ] 말풍선 안 마크다운 이미지가 산출 파일 경로면 인증 fetch로 렌더되고, 외부 URL은 기본 `<img>`
- [ ] 로딩 스켈레톤 → 이미지, 실패 시 다운로드 링크 폴백, object URL 해제
- [ ] 클릭 시 다운로드(파일명 유지)
- [ ] 히스토리 재조회에서도 동일 렌더(저장 본문의 마크다운)
- [ ] 빌더 도구 목록에 "이미지 생성" 노출(tool-catalog), 부착 시 설정 패널 열림
- [ ] 모델 드롭다운은 `image` 종류·활성만, 없으면 안내 + 저장 차단
- [ ] 크기 3종·품질 2종 선택, 저장 payload `tool_configs['internal:image_generate']`
- [ ] 서버 422 코드별 오류 표시
- [ ] 관리자 폼 종류 라디오·장당 단가, 목록 배지. 채팅·비전 드롭다운에 이미지 모델 미노출
- [ ] 에이전트 모델 드롭다운(빌더 설정 탭)에 이미지 모델 미노출

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code / 상황 | 계층 | 처리 |
|---|---|---|
| `IMAGE_MODEL_INVALID` 422 | 에이전트 저장 | 프론트 필드 오류 |
| `IMAGE_CONFIG_INVALID` 422 | 에이전트 저장 | 프론트 필드 오류 |
| `MODEL_KIND_MISMATCH` 422 | 에이전트 모델·비전 모델 저장 | 프론트 안내 |
| 턴당 상한 초과 | 노드 | 안내 AIMessage("상한 N장 도달"), 실행 계속 |
| 모델 미설정·삭제·비활성 | 노드 | 안내 AIMessage("에이전트 편집에서 이미지 모델을 다시 선택") |
| provider 정책 위반(content_policy) | 어댑터 → 노드 | 안내 AIMessage(재시도 없음) |
| 429/5xx/타임아웃 | 어댑터 | 1회 재시도 후 안내 AIMessage |
| 첨부 없는 edit 요청 | 유스케이스 | generate 폴백 + 본문에 명시 |
| 저장 실패 | 유스케이스 | ImageGenerationError → 안내 AIMessage, `logger.error(exception=e)` |

### 6.2 Error Response Format

HTTP는 기존 `{"detail": {"code", "message"}}`. 노드 오류는 모두 AIMessage 본문(워커 산출물 1건 규칙 유지).

### 6.3 보수 동작

- 원장 기록 실패는 경고 로그 후 결과 반환(관측성 degraded 규칙과 동형).
- 단가 미등록 → `cost_usd=0` + 경고 로그.
- 응답 바이트가 PIL로 열리지 않으면 `ImageProviderError`(저장하지 않음).

---

## 7. Security Considerations

| 항목 | 설계 |
|------|------|
| API 키 | `api_key_env` 이름만 저장(기존). 어댑터가 env에서 읽음. 로그 금지 |
| 소유자 | 산출물 owner = 요청 사용자. 다운로드는 기존 소유자 검증. 스케줄·웹훅 실행은 `RunAgentRequest.user_id` 사용 |
| 편집 입력 | 이번 턴 `state.attachments`(이미 소유자 검증됨)만. 경로는 프롬프트·로그에 노출 금지(이름만) |
| 바이트 누출 | 상태·메시지·원장·로그에 base64 금지. `GeneratedImage`에 바이트 없음 |
| 프롬프트 | 사용자 원문은 기존 프롬프트 가드 통과. 모델 생성 프롬프트는 길이 상한 + provider 정책 |
| 폭탄 | 응답 이미지 PIL 판독 시 `MAX_IMAGE_PIXELS`(첨부 설정 재사용) |
| 인라인 표시 | 토큰을 URL에 넣지 않음. 프론트 인증 fetch |

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0 단위 | 정책·VO·tool_config·레지스트리·어댑터(SDK 모킹)·유스케이스·노드·후처리·마이그레이션 COMMENT | pytest | Do |
| L1 API | llm-models 두 필드 CRUD, 에이전트 저장 422 3종 | pytest TestClient | Do |
| L2 UI | AuthenticatedImage·MarkdownRenderer img·ConfigPanel·관리자 폼·드롭다운 필터 | Vitest+RTL+MSW | Do |
| L3 E2E(수동) | 생성·편집·상한·비용·히스토리 | 실서버 | Check |
| 계약 | base64가 상태·메시지·원장에 없음, `.content` 직접 접근 금지(기존 계약 테스트 자동 적용) | pytest | Do |

### 8.2 L0/L1 시나리오

| # | 대상 | 테스트 | 기대 |
|---|------|--------|------|
| 1 | `ImageGenerationPolicy` | 프롬프트 공백·빈 값·초과, 상한 0/4/5, resolve_mode(edit, 첨부 없음)→(generate, True), sub_agent_cap(4)=2·(1)=1, 파일명 형식 | 값·예외 |
| 2 | `ImageGenerationToolConfig` | 정상, 빈 id, size/quality 미허용 | ValueError |
| 3 | `ImageRequestDraft` | extra 금지, Literal 검증 | ValidationError |
| 4 | `ImageGeneratorRegistry` | register 중복, supported, build 미지원 provider | 예외 |
| 5 | `OpenAIImageGenerator` (AsyncOpenAI 모킹) | generate 인자 매핑(gpt-image: medium/high, dall-e-3: standard/hd + response_format), edit 호출 형식, b64→bytes+치수, 429 1회 재시도, content_policy → ImageProviderError(retryable False), base_url 전달 | 호출 인자·예외 |
| 6 | `GenerateImageUseCase` | kind≠image → ImageModelNotConfiguredError, generate 경로 저장·원장(purpose image_generation, token 0, cost=단가), edit 경로 source 읽기, 단가 없음 → cost 0+경고, 타임아웃 → ImageProviderError, 저장 결과에 바이트 없음 | 호출·결과 |
| 7 | 노드 `_create_image_generate_node` | tool_config 불량 → 안내, 상한 초과 → 안내+count 불변, 정상 → AIMessage 본문 3줄·generated_images 추가·count+1, 유스케이스 예외 → 안내·그래프 비중단 | 상태 dict |
| 8 | compile 분기 | `image_generate` 워커가 함수형 노드로 등록되고 ToolFactory 미호출 | 호출 여부 |
| 9 | 서브에이전트 | 부모 cap 4 → 서브 initial 2, 서브 generated_images·count 부모 합산 | 상태 |
| 10 | `_append_generated_images` | 본문에 file_id 있으면 무변경, 없으면 끝에 마크다운 줄 추가, 빈 목록 무변경 | 문자열 |
| 11 | RunAgentUseCase | chain_end 출력의 generated_images 수집 → ANSWER_COMPLETED payload 답변·저장 본문에 마크다운 포함 | 이벤트·저장 |
| 12 | LlmModel CRUD | 생성·수정·가격 수정에 두 필드, 기본 chat, 응답 노출 | API |
| 13 | 에이전트 저장 검증 | image_generate 설정 모델 없음/비활성/chat → 422 IMAGE_MODEL_INVALID; 에이전트 llm_model_id 가 image → MODEL_KIND_MISMATCH | API |
| 14 | 채팅·비전 드롭다운 후보 | 서비스/유스케이스가 kind=chat 만 반환 | 목록 |
| 15 | V081 | COMMENT 테스트, SQLAlchemy comment= | pytest |
| 16 | 누출 계약 | 노드 출력·상태·AIMessage·원장 행 직렬화에 `data:image` 없음 | 문자열 |

### 8.3 L2: UI Action Test Scenarios

| # | 대상 | 액션 | 기대 |
|---|---|---|---|
| 1 | AuthenticatedImage | 마운트 | 서비스 호출, 스켈레톤 → img src blob: |
| 2 | AuthenticatedImage | 서비스 실패 | 폴백 링크 표시 |
| 3 | AuthenticatedImage | 언마운트 | revokeObjectURL 호출 |
| 4 | MarkdownRenderer | `![a](/api/v1/document-extractor/files/x)` | AuthenticatedImage 렌더; `![b](https://…)`는 기본 img |
| 5 | ConfigPanel | 모델 목록에 chat·image 혼재 | image·활성만 노출 |
| 6 | ConfigPanel | 모델 없음 | 안내 + 저장 비활성 |
| 7 | ConfigPanel | 크기·품질 선택 → 저장 | payload tool_configs 정확 |
| 8 | AgentBuilderPage | 도구 제거 | 설정 삭제 |
| 9 | 관리자 폼 | 종류 image 선택 | 장당 단가 입력 표시, 토큰 단가 숨김, 저장 payload |
| 10 | 에이전트 설정 탭 모델 드롭다운 | image 모델 포함 목록 | 미노출 |

### 8.4 L3: E2E Scenario (수동)

| # | 시나리오 | 성공 기준 |
|---|---|---|
| 1 | 관리자 gpt-image-1 등록(단가 0.04) → 에이전트 도구 부착 → "가을 특판 배너 만들어 줘" | 답변에 이미지 인라인, 클릭 다운로드, 파일 1024×1024 |
| 2 | 이미지 첨부 + "배경을 흰색으로" | 편집 결과 표시, 본문에 폴백 문구 없음 |
| 3 | 첨부 없이 "이 이미지 배경 바꿔 줘" | 생성 폴백 + 안내 문구 |
| 4 | 같은 턴 5회 생성 유도 | 5번째는 상한 안내, 실행 실패 없음 |
| 5 | ai_run 상세·사용량 | 호출 행 purpose image_generation, cost 0.04×건수 합산 |
| 6 | 히스토리 재진입 | 이미지 재표시. 토큰 만료 상태에서 폴백 링크 |
| 7 | 서브에이전트(이미지 도구 보유)에 위임 | 상한 절반 적용, 부모 답변에 이미지 포함 |
| 8 | 승인 게이트 에이전트 | 승인 후 재개 답변에도 이미지 포함, 스냅샷에 base64 없음 |

### 8.5 Seed Data Requirements

| Entity | 조건 |
|---|---|
| `llm_model` | `model_kind=image` 활성 1종(OPENAI_API_KEY), chat 1종 |
| `agent` | 이미지 도구 부착 에이전트, 서브에이전트 보유 에이전트, 승인 게이트 에이전트 |
| 픽스처 | 1×1 PNG 바이트(PIL 생성), AsyncOpenAI 모킹 응답(b64_json) |

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Layer | 파일 | 책임 | 금지 |
|---|---|---|---|
| domain | `image_generation/{value_objects,policies,tool_config,schemas,interfaces,exceptions}.py`, `agent_builder/tool_registry.py`(등록), `agent_run/value_objects.py`(purpose), `llm_model/entity.py`(필드) | 규칙·VO·포트·LLM 출력 스키마 | openai·PIL·LangChain |
| application | `image_generation/{use_case,registries}.py`, `agent_builder/workflow_compiler.py`(노드·서브 전달), `agent_builder/{supervisor_state,supervisor_nodes}.py`(채널), `agent_builder/run_agent_use_case.py`(수집·후처리), `llm_model/*`(CRUD 필드·kind 검증), `agent_builder/*create/update*`(tool_config 검증) | 흐름·조립 | provider 파라미터 |
| infrastructure | `image_generation/openai_image_generator.py`, `llm_model/{models,llm_model_repository}.py`, `db/migration/V081` | SDK 호출·매핑·영속 | 비즈니스 규칙 |
| interfaces | `api/routes/llm_model_router.py`(필드), `api/main.py`(DI), 에이전트 라우터 422 | 스키마·DI | 로직 |

---

## 10. Coding Convention Reference

### 10.3 Environment Variables

```
IMAGE_GENERATION_MAX_PER_TURN=4
IMAGE_GENERATION_DEFAULT_SIZE=1024x1024
IMAGE_GENERATION_TIMEOUT_SEC=60
IMAGE_GENERATION_MAX_PROMPT_CHARS=2000
```
`config.py` 동일 이름 소문자 4종, `.env.example` 반영.

### 10.4 This Feature's Conventions

- 파일 상단 `# Design Ref: image-generation-tool §n`, 핵심 로직 `# Plan SC:`.
- 함수 40줄: 노드는 `_check_cap`, `_draft_request`, `_resolve_source`, `_render_image_summary`로 분리.
- 로깅: `file_id, model_name, size, mode, elapsed_ms, cost_usd`만. 프롬프트는 앞 80자.
- 프론트 상수는 `types/imageGeneration.ts`의 `as const`. 컴포넌트 파일 런타임 상수 export 금지.
- DDL: 전 컬럼 COMMENT, 콤마 금지.

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/image_generation/            (N) value_objects, policies, tool_config, schemas, interfaces, exceptions
├── domain/agent_builder/tool_registry.py           (M) image_generate 등록
├── domain/agent_run/value_objects.py               (M) RunPurpose.IMAGE_GENERATION
├── domain/llm_model/entity.py                      (M) model_kind, price_per_image_usd
├── application/image_generation/                   (N) use_case.py, registries.py
├── application/llm_model/{schemas,create,update,...}.py (M) 필드·kind 검증, 채팅/비전 후보 필터
├── application/agent_builder/workflow_compiler.py  (M) 분기·노드·서브 전달
├── application/agent_builder/supervisor_state.py   (M) generated_images, generated_image_count, image_generation_max_per_turn
├── application/agent_builder/supervisor_nodes.py   (M) build_initial_state 기본값
├── application/agent_builder/run_agent_use_case.py (M) 수집·_append_generated_images
├── application/agent_builder/(에이전트 생성·수정 UseCase) (M) tool_config 검증
├── infrastructure/image_generation/openai_image_generator.py (N)
├── infrastructure/llm_model/{models,llm_model_repository,seed}.py (M)
├── api/routes/llm_model_router.py (M), api/main.py (M), config.py (M), .env.example (M), pyproject.toml (M openai 명시)
└── db/migration/V081__add_model_kind_and_image_price_to_llm_model.sql (N)
idt/tests/ … §8.2 대응 (domain/image_generation, application/image_generation, application/agent_builder/test_image_generate_node.py,
            test_run_agent_generated_images.py, infrastructure/image_generation, api/test_llm_model_router(M), db COMMENT)
idt_front/src/
├── types/imageGeneration.ts (N), types/llmModel.ts (M)
├── services/documentExtractorService.ts (M fetchGeneratedFileBlob)
├── components/chat/AuthenticatedImage.tsx (N) + test, components/chat/MarkdownRenderer.tsx (M) + test
├── components/agent-builder/ImageGenerationConfigPanel.tsx (N) + Modal + tests
├── pages/AgentBuilderPage/index.tsx (M), pages/AdminLlmModelsPage/index.tsx (M) + tests
├── (에이전트 설정 탭·멀티모달 설정 폼 모델 드롭다운) (M) kind 필터
└── __tests__/mocks/handlers.ts (M)
```

### 11.2 Implementation Order

1. [ ] V081 + LlmModel 필드(엔티티·ORM·레포·스키마·CRUD·시드) + 채팅/비전 후보 kind 필터 (+테스트 12·14·15)
2. [ ] domain/image_generation 전부 (+테스트 1·2·3)
3. [ ] 레지스트리 + OpenAI 어댑터 (+테스트 4·5), `openai` 명시 의존
4. [ ] `GenerateImageUseCase` + purpose + 원장 기록 (+테스트 6·16)
5. [ ] 상태 채널·노드·compile 분기·서브 전달 + TOOL_REGISTRY (+테스트 7·8·9)
6. [ ] RunAgentUseCase 수집·후처리 (+테스트 10·11), 설정 4종·DI·.env.example
7. [ ] 에이전트 저장 tool_config 검증 422 (+테스트 13)
8. [ ] 프론트 타입·서비스·AuthenticatedImage·MarkdownRenderer (+L2 1~4)
9. [ ] 프론트 ConfigPanel·빌더 배선·관리자 폼·드롭다운 필터·MSW (+L2 5~10)
10. [ ] 회귀 전량·verify 스킬·수동 E2E·SOT/wiki 보고

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 모델 레지스트리 | `module-1` | 순서 1: V081, LlmModel 필드, CRUD, kind 필터 | 25-35 |
| 생성 코어 | `module-2` | 순서 2~4: domain, 레지스트리·OpenAI 어댑터, UseCase·원장 | 35-45 |
| 그래프 통합 | `module-3` | 순서 5~7: 상태 채널·노드·분기·서브·후처리·저장 검증 | 35-45 |
| 프론트 | `module-4` | 순서 8~9 | 40-50 |
| 통합 검증 | `module-5` | 순서 10 | 15-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 60-80 |
| Session 3 | Do | `--scope module-3` | 35-45 |
| Session 4 | Do | `--scope module-4` | 40-50 |
| Session 5 | Do + Check | `--scope module-5` → `/pdca analyze` | 30-40 |

의존: module-2는 module-1(모델 필드) 선행, module-3은 1·2 선행, module-4는 module-1(응답 필드)만 선행하면 module-3과 병행 가능.

---

## 12. 설계 결정 기록

| ID | 결정 | 근거 |
|----|------|------|
| D-01 | 전용 합성 노드(ToolFactory 미경유) | 구조화 출력·저장·상한·원장 기록을 한 노드가 완결. 문서 생성 워커와 동형 |
| D-02 | 산출물은 DOCUMENT 저장소 + 기존 다운로드 라우터 | 소유자 검증·프론트 링크 처리 재사용. 새 API 없음 |
| D-03 | `generated_images` 상태 채널 + 종료 시 본문 후처리 | final_answer 재작성으로 링크가 유실될 위험을 결정적으로 제거. 텍스트에 남아 히스토리도 동작 |
| D-04 | 비용 = LLM 호출 행(토큰 0, cost=단가, purpose image_generation) | 원장·집계·사용량 화면 변경 없이 합산 |
| D-05 | `llm_model.model_kind` + `price_per_image_usd` | 관리자 화면·api_key_env·base_url 재사용. 채팅/비전 후보는 kind=chat만 |
| D-06 | 어댑터 레지스트리(provider 키), OpenAI·OpenAI 호환만 구현 | 사용자 결정. 비전 어댑터와 같은 확장 지점 |
| D-07 | 정책 VO는 추상 size/quality, 어댑터가 모델명으로 번역 | gpt-image(low/medium/high)·dall-e-3(standard/hd) 차이 흡수 |
| D-08 | 편집 입력 = 이번 턴 첨부만, 없으면 generate 폴백 + 명시 | 첨부 수명(턴 종료 삭제)과 일치, 사용자 결정 |
| D-09 | 서브 그래프 상한 = 부모의 절반(하한 1), 결과 채널 부모 합산 | 반복 한도 규칙과 동형, 우회 방지 |
| D-10 | 인라인 표시는 프론트 인증 fetch → object URL | 토큰 URL 노출 금지. 실패 시 다운로드 링크 폴백 |
| D-11 | 첨부 이미지를 프롬프트 작성 LLM에 별도 전달하지 않음 | 상태 messages에 이미 실려 비전 지원 모델은 자동으로 봄(chat-image-attachment D-01) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | Initial draft (Option C) | 배상규 |
| 0.2 | 2026-10-31 | Do module-3 정정: 도구 설정은 `image_generation` 전용 요청 필드(발표자료 설정 동형), 노드 owner 는 auth_ctx 없으면 subject_user_id | 배상규 |
