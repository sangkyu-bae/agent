# chat-image-attachment Design Document

> **Summary**: 에이전트 채팅에 이미지(png/jpg/webp, 최대 5장)를 첨부하면 이번 턴의 사용자 메시지를 "텍스트 + 이미지 블록" 다중 콘텐츠로 조립해 에이전트에 연결된 비전 LLM이 직접 본다. 기존 엑셀 첨부 계약을 확장하고, 상태 메시지의 문자열 가정은 텍스트 추출 헬퍼와 계약 테스트로 고정한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-10-30
> **Status**: Draft
> **Planning Doc**: [chat-image-attachment.plan.md](../../01-plan/features/chat-image-attachment.plan.md)
> **Selected Architecture**: Option C — 실용 절충 (Checkpoint 3, 2026-10-30)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema — DB 변경 없음 | N/A |
| Phase 4 | API Spec — 본 문서 §4 | ✅ |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 채팅에서 이미지를 보고 묻는 요청을 받을 수 없다. 비전 호출 코드는 있으나 채팅 경로에 연결되어 있지 않다. |
| **WHO** | P1 일반 사용자(에이전트 채팅 이용자). 관리자는 모델의 supports_vision 플래그만 관리한다. |
| **RISK** | 상태 메시지 content가 문자열이라는 가정이 agent_builder 전반(요약·검색결과 판정·마지막 지시 추출·재주입 판정)에 퍼져 있어 list content 도입 시 조용한 오동작 가능. |
| **SUCCESS** | 비전 모델 에이전트에 이미지 5장+질문 → 이미지 내용을 근거로 한 답변 수신. 미지원 모델은 프론트 버튼 비활성 + 서버 명시 거부. 턴 종료 후 파일 삭제, 기록에는 마커만. 기존 엑셀 첨부·일반 채팅 회귀 0. |
| **SCOPE** | 에이전트 경로(WS subscribe)만. 일반 채팅·백그라운드 잡·웹훅·스케줄 경로, 다음 턴 이미지 참조, 관리자 비전 모델로의 텍스트 변환 폴백은 제외. |

---

## 1. Overview

### 1.1 Design Goals

1. 이미지가 supervisor 판단·워커·final_answer 등 모든 LLM 소비자에게 **추가 배선 없이** 전달된다 (상태 HumanMessage에 싣는다).
2. 상태 메시지 content가 `str | list`가 되어도 기존 문자열 처리 지점이 **깨지지 않고 누락되지도 않는다** (헬퍼 + 계약 테스트).
3. 이미지 바이트가 DB·요약·실행 이력·로그에 **남지 않는다** (마커 저장 + 축약 필터).
4. 기존 엑셀 첨부·일반 채팅·백그라운드 경로의 **동작 바이트가 변하지 않는다** (이미지 없는 턴은 기존 코드 경로 그대로).

### 1.2 Design Principles

- 첨부 전달 채널·저장소·cleanup·TTL은 `ws-agent-excel-attachment` 계약을 그대로 쓴다. 새 엔드포인트·새 WS 메시지 타입을 만들지 않는다.
- 벤더별 이미지 블록 포맷은 한 곳(`ImageBlockBuilder`)에만 둔다. 기존 비전 어댑터의 `build_image_block`은 그대로 두되 같은 포맷을 쓴다.
- 비전 지원 판정의 단일 소스는 `LlmModel.supports_vision`이다. 프론트는 안내용으로만 읽고, 권위 있는 거부는 서버가 한다.
- 이미지가 없는 턴은 `content`가 `str`로 유지된다. 헬퍼는 `str`을 그대로 돌려준다(하위 호환).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 항목 | A. 최소 변경 | B. 경계 주입(클린) | **C. 실용 절충 (선택)** |
|---|---|---|---|
| 이미지 위치 | 상태 HumanMessage list content | 상태는 텍스트, LLM 호출 직전 주입 | 상태 HumanMessage list content |
| 문자열 가정 지점 | 지점마다 인라인 분기 | 변경 불필요 | `message_text()` 헬퍼 + 계약 테스트 |
| 서브에이전트 | 항상 마커 | 주입기가 비전 여부로 전달 | 입력 조립 시 비전 여부로 전달/마커 |
| 누출 방지 | 없음 | 구조적 | `redact_image_blocks()` 축약 필터 |
| LLM 호출 지점 배선 | 0 | 4곳 이상 + 누락 위험 | 0 |
| 복잡도/공수 | 낮음 | 높음 | 중간 |

선택 이유: 호출 지점 배선 누락 위험(B)을 피하면서, 사용자 결정(워커별 치환·누출 방지)을 충족한다(A는 미충족).

### 2.1 Component Diagram

```
[idt_front]                                  [idt]
ChatInput ──paste/drop/pick──▶ ChatPage      POST /api/v1/agent/attachments
  │ (썸네일 칩, 장수·크기 검증)   │  ┌───────▶  agent_attachment_router
  │                             │  │            └─ UploadAttachmentUseCase
  │ uploadImage(file) ──────────┘  │                 ├─ AttachmentPolicy.validate (ext·size·magic)
  │                                │                 ├─ ImageNormalizerPort.normalize (PIL, infra)
  │ useLlmModels + agent.llm_model_id                └─ AgentAttachmentStore.save → file_id
  │   → supports_vision (안내용)
  ▼
useAgentRunStream.subscribe{attachments:[{type:"image",file_id}...]}
                                   │
                                   ▼
                               ws_router.ws_agent_run
                                 ├─ _resolve_ws_attachments (소유자 검증, 장수 상한)
                                 ├─ use_case.precheck_attachments → VISION_NOT_SUPPORTED
                                 └─ use_case.stream(request.attachments=[{type:"image", file_path, mime, file_name, user_id}])
                                       │
                                       ▼
                                 RunAgentUseCase
                                   ├─ llm_model 해석 (supports_vision 확인)
                                   ├─ _save_user_message(query + 마커)      ← DB엔 마커만
                                   ├─ _build_messages(...)  이번 턴 user content =
                                   │     [{"type":"text","text":query}, ImageBlockBuilder.build(provider, image)...]
                                   └─ build_initial_state(messages, attachments)
                                         │
                                         ▼
                                   Supervisor Graph (state.messages 에 list content 1건)
                                     ├─ supervisor_decision   (첨부 인지 블록: "이미지 N장")
                                     ├─ worker react agents   (같은 LLM → 그대로 봄)
                                     ├─ final_answer / QG     (message_text() 로 텍스트만 사용)
                                     ├─ search pipeline       (message_text() — 이미지 미전달)
                                     └─ _wrap_sub_agent       (서브 모델 supports_vision ? 이미지 전달 : 마커)
                                   step_tracking input_summary ← redact_image_blocks()
                                   finally: attachment_resolver.cleanup(file_ids)
```

### 2.2 Data Flow

1. 사용자가 이미지를 고르거나 붙여넣거나 드롭한다 → 프론트가 형식·장수·크기를 사전 검증하고 업로드 → `file_id`·`width`·`height` 수신 → 썸네일 칩 표시.
2. 전송 시 subscribe에 `attachments: [{type:"excel"|"image", file_id}]` 배열을 싣는다.
3. 서버가 소유자 검증 → 이미지 장수 상한 검사 → 에이전트 실효 모델의 `supports_vision` 사전 검사(거부 시 subscribe 거절, 실행 미시작).
4. `RunAgentUseCase`가 모델을 해석한 뒤 메시지를 조립한다. 이번 턴 user 메시지만 list content. DB 저장 content는 `query + "\n[이미지 첨부: a.png, b.png]"`.
5. 그래프 전 구간이 상태 messages를 그대로 소비한다. 텍스트가 필요한 지점은 `message_text()`를 쓴다.
6. 서브에이전트 위임 시 서브 모델이 비전 지원이면 입력 마지막 user 블록에 이미지 블록을 덧붙이고, 아니면 마커 문장을 덧붙인다.
7. 턴 종료(정상·예외·끊김) 시 `cleanup`으로 파일 삭제.

### 2.3 Dependencies

| 의존 | 상태 | 비고 |
|------|------|------|
| `pillow` | 설치됨(12.3.0, 전이 의존) | `pyproject.toml`에 명시 추가 |
| LangChain 벤더 블록 포맷 | 기존 비전 어댑터에서 검증됨 | OpenAI·OpenAI 호환·Ollama: `image_url` data URL / Anthropic: `image`+`base64` |
| `LlmModel.supports_vision` (V064) | 존재 | DB 변경 없음 |
| `useLlmModels` (GET `/api/v1/llm-models`, 로그인 사용자) | 존재 | 프론트 비전 여부 안내 |

---

## 3. Data Model

### 3.1 Entity Definition

DB 스키마 변경 없음. 런타임 값 객체만 확장한다.

```python
# domain/agent_attachment/value_objects.py
class AttachmentType(str, Enum):
    EXCEL = "excel"
    DOCUMENT = "document"
    IMAGE = "image"            # 신규

@dataclass(frozen=True)
class ImageDimensions:         # 신규 — normalizer 결과
    width: int
    height: int
    mime: str                  # "image/png" | "image/jpeg" | "image/webp"

@dataclass(frozen=True)
class StoredAttachment:        # 기존 + 옵셔널 2필드(additive)
    file_id: str
    type: AttachmentType
    filename: str
    size: int
    owner_user_id: str
    file_path: str
    width: int | None = None
    height: int | None = None
```

```python
# domain/agent_attachment/interfaces.py — 신규 포트 2종
class ImageNormalizerPort(Protocol):
    def normalize(self, data: bytes, *, max_edge_px: int, jpeg_quality: int) -> tuple[bytes, ImageDimensions]: ...

class ImageBlockBuilderPort(Protocol):
    def build(self, provider: str, *, mime: str, data: bytes, detail: str) -> dict: ...
    def build_from_path(self, provider: str, *, mime: str, path: str, detail: str) -> dict: ...  # v0.2: 파일 I/O 는 인프라
    def supports(self, provider: str) -> bool: ...
```

```python
# domain/agent_attachment/policies.py — 추가 규칙
class AttachmentPolicy:
    ALLOWED_EXT[AttachmentType.IMAGE] = frozenset({".png", ".jpg", ".jpeg", ".webp"})
    IMAGE_MAGIC = {  # 매직 넘버 → mime
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
        # webp: b"RIFF" + 4바이트 + b"WEBP"
    }
    @classmethod
    def sniff_image_mime(cls, head: bytes) -> str | None
    @classmethod
    def validate_image_bytes(cls, filename: str, head: bytes) -> str   # ext↔magic 불일치 → InvalidAttachmentError

class ImageAttachmentPolicy:     # 신규 — 턴 단위 규칙(순수)
    @staticmethod
    def validate_count(n: int, max_count: int) -> None   # 초과 → TooManyImagesError
    @staticmethod
    def marker(file_names: list[str]) -> str             # "[이미지 첨부: a.png, b.png]"
    @staticmethod
    def unsupported_marker(file_names: list[str]) -> str # "[이미지 첨부: a.png (이 모델은 이미지를 볼 수 없음)]"
```

```python
# domain/agent_attachment/exceptions.py — 추가
class TooManyImagesError(Exception)
class VisionNotSupportedError(Exception)   # (model_display_name)
```

### 3.2 Entity Relationships

- `RunAgentRequest.attachments[i]` (이미지): `{"type": "image", "file_path": str, "mime": str, "file_name": str, "width": int|None, "height": int|None, "user_id": str}` — 엑셀 dict와 같은 리스트에 섞인다 (v0.2: width/height 추가). 기존 `type == "excel"` 필터는 이미지 dict를 무시한다.
- 상태 `SupervisorState.attachments`는 위 dict를 그대로 보관한다(바이트 없음). 이미지 바이트는 `state.messages[-1].content`의 블록에만 base64로 존재한다.

### 3.3 메시지 콘텐츠 계약

```python
# 이번 턴 user 메시지 (이미지 있을 때만 list)
{"role": "user", "content": [
    {"type": "text", "text": "<query>"},
    <ImageBlockBuilder.build(provider, ...)>,   # ×N (N ≤ max_count)
]}
```

| provider 키 | 블록 포맷 |
|---|---|
| `openai`, `openai_compatible`, `ollama` | `{"type":"image_url","image_url":{"url":"data:<mime>;base64,<b64>","detail":<detail>}}` (`openai_compatible`/`ollama`는 `detail` 생략) |
| `anthropic` | `{"type":"image","source":{"type":"base64","media_type":<mime>,"data":<b64>}}` |
| 그 외 | `ImageBlockBuilder.supports()==False` → precheck에서 `VisionNotSupportedError` |

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 | 설명 |
|--------|------|------|------|
| POST | `/api/v1/agent/attachments` | 응답 필드 추가 | 이미지도 수용. `type`은 서버 판별 |
| WS | `/ws/agent/{run_id}` subscribe | 검증·오류 코드 추가 | `attachments[]`에 `type:"image"` 다건 |
| GET | `/api/v1/agent/my` (my-agents) | 응답 필드 추가 (v0.2) | `MyAgentSummary.llm_model_id: str \| null` — 프론트 비전 여부 안내(D-09)용, additive |

### 4.2 Detailed Specification

**POST /api/v1/agent/attachments** (multipart `file`)

응답 201:
```json
{ "file_id": "…", "type": "image", "filename": "shot.png", "size": 184320, "width": 1568, "height": 882 }
```
`width`/`height`는 이미지일 때만, 엑셀은 `null`(additive, 프론트 옵셔널).

오류:
| Status | code | 조건 |
|---|---|---|
| 400 | `INVALID_ATTACHMENT` | 미허용 확장자, 빈 파일, 확장자↔매직 넘버 불일치, 디코딩 실패 |
| 413 | `ATTACHMENT_TOO_LARGE` | 원본 크기 > `agent_attachment_max_bytes` |
| 401 | — | 미인증 |

**WS subscribe**
```json
{ "type":"subscribe", "agent_id":"…", "query":"이 표에서 3분기 값은?", "session_id":"…",
  "attachments":[ {"type":"image","file_id":"…"}, {"type":"image","file_id":"…"}, {"type":"excel","file_id":"…"} ] }
```
거절(실행 미시작, 기존 `_reject_subscribe` 경로):
| code | 조건 |
|---|---|
| `ATTACHMENT_NOT_FOUND` / `ATTACHMENT_ACCESS_DENIED` | 기존 |
| `ATTACHMENT_LIMIT_EXCEEDED` | 이미지 장수 > `agent_attachment_image_max_count` |
| `VISION_NOT_SUPPORTED` | 실효 모델 `supports_vision=false` 또는 provider 블록 미지원. message: `"'{display_name}' 모델은 이미지 입력을 지원하지 않습니다. 관리자 > LLM 모델에서 비전 지원을 켜거나 다른 모델의 에이전트를 사용하세요."` |

### 4.3 서버 내부 계약

```python
# RunAgentUseCase — 신규 공개 메서드 (ws_router가 stream 전에 호출)
async def precheck_attachments(self, agent_id: str, attachments: list[dict] | None,
                               request_id: str, viewer_user_id: str, viewer_department_ids: list[str]) -> None:
    """이미지가 없으면 즉시 반환. 있으면 에이전트 로드·권한 확인 후 실효 모델의
    supports_vision 과 ImageBlockBuilder.supports(provider) 를 검사. 실패 → VisionNotSupportedError."""
```

`_prepare_graph` 순서 변경(v0.2 정정): 모델 해석(`llm_model`)을 `_build_messages`보다 **앞**으로 당긴다. 저장(`_save_user_message`)은 마커에 모델 정보가 필요 없어 기존 위치를 유지한다. 저장 content는 `ImageAttachmentPolicy.marker()`를 덧붙인 문자열, 조립은 `_attach_turn_images()`가 마지막 user content를 list로 바꾼다.

사전 검사 위치(v0.2 정정): 이미지 장수 상한은 `precheck_attachments` 안에서 검사하고, ws_router 는 이미지 첨부가 있을 때만 precheck 를 호출한다(이미지 없는 턴은 기존 경로와 바이트 동일). precheck 는 `llm_model_id_override` 를 받아 실행과 같은 실효 모델로 판정한다.

---

## 5. UI/UX Design

### 5.1 Screen Layout (ChatInput, agent 모드)

```
┌──────────────────────────────────────────────────────────┐
│ [📎 sales.xlsx ✕]  [🖼 shot1.png ✕] [🖼 shot2.jpg ✕] [업로드 중…] │  ← 칩 행 (썸네일 40px)
│ ┌──────────────────────────────────────────────────────┐ │
│ │ 메시지 입력… (이미지를 붙여넣거나 끌어다 놓을 수 있음)   │ │  ← 드래그 오버 시 점선 테두리 + "이미지를 놓으세요"
│ └──────────────────────────────────────────────────────┘ │
│ [문서 검색] [엑셀] [이미지]                [⏱] [전송]       │
└──────────────────────────────────────────────────────────┘
  ↳ 비전 미지원: [이미지] disabled + title "이 에이전트의 모델은 이미지 입력을 지원하지 않습니다"
```

### 5.2 User Flow

1. 에이전트 선택 → `useLlmModels` 결과에서 `selectedAgent.llm_model_id`의 `supports_vision` 조회 → 버튼 활성/비활성.
2. 이미지 입력(버튼·paste·drop) → 프론트 검증(형식·장수·장당 크기) → 실패 항목은 토스트로 사유 표시, 성공 항목만 업로드.
3. 업로드 완료 → 칩 추가. 칩 ✕로 개별 제거(서버 파일은 TTL로 회수, 별도 삭제 API 없음).
4. 전송 → subscribe attachments 배열 → 사용자 말풍선에 썸네일 표시(object URL, 세션 메모리).
5. 서버 거절 코드 수신 → 기존 오류 표시 경로에 메시지 매핑. 첨부 목록은 유지해 재시도 가능.

### 5.3 Component List

| 컴포넌트 | 변경 | 책임 |
|---|---|---|
| `ChatInput.tsx` | 수정 | 이미지 버튼, `onPaste`, `onDragOver/onDrop`, 칩 행을 배열 props로 |
| `AttachmentChip.tsx` (신규, `components/chat/`) | 신규 | 엑셀/이미지 칩 1개(썸네일·이름·제거) |
| `ChatPage/index.tsx` | 수정 | `pendingAttachments: PendingAttachment[]` 상태, 업로드 핸들러 통합, 비전 여부 계산, 오류 코드 매핑 |
| `MessageBubble`(사용자 말풍선) | 수정 | `imagePreviews?: string[]` 렌더 |
| `utils/imageAttachmentValidators.ts` (신규) | 신규 | 형식·장수·크기 순수 검증 |
| `services/agentAttachmentService.ts` | 수정 | `uploadImage(file)` (동일 엔드포인트), `uploadExcel` 유지 |
| `types/agentAttachment.ts` | 수정 | `AttachmentType = 'excel' \| 'image'`, 응답 `width?/height?`, `PendingAttachment` |
| `hooks/useAgentRunStream.ts` | 확인 | attachments 배열 전달은 이미 배열. 변경 없음 |
| `constants/api.ts` | 변경 없음 | 동일 엔드포인트 |

### 5.4 Page UI Checklist

- [ ] 이미지 버튼은 agent 모드에서만 보이고, 비전 미지원이면 disabled + title 안내
- [ ] paste: `clipboardData.files`에 이미지가 있을 때만 가로채고 텍스트 붙여넣기는 기본 동작 유지
- [ ] drop: 입력 카드 전체가 드롭존, 드래그 오버 시 시각 피드백, 비이미지 파일 드롭은 무시+토스트
- [ ] 칩: 썸네일 40px, 파일명 truncate, ✕ `aria-label="첨부 제거: {name}"`
- [ ] 장수 초과(5장) 시 추가 입력 무시 + 토스트 "이미지는 최대 5장까지 첨부할 수 있습니다"
- [ ] 장당 10MiB 초과·미허용 형식은 업로드 전 토스트
- [ ] 업로드 중 전송 버튼 비활성(기존 `attachmentUploading` 규칙 유지)
- [ ] 전송 후 첨부 목록 비움, 말풍선에 썸네일
- [ ] 서버 거절(`VISION_NOT_SUPPORTED`·`ATTACHMENT_LIMIT_EXCEEDED`) 메시지 표시
- [ ] 히스토리 재조회 시 마커 텍스트만 표시(깨진 이미지 아이콘 없음)

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | 계층 | HTTP/WS | 메시지(사용자) | 처리 |
|------|------|---------|----------------|------|
| `INVALID_ATTACHMENT` | 업로드 | 400 | "지원하지 않는 이미지 형식입니다 (png/jpg/webp)" | 프론트 토스트 |
| `ATTACHMENT_TOO_LARGE` | 업로드 | 413 | "이미지가 너무 큽니다 (최대 10MB)" | 프론트 토스트 |
| `ATTACHMENT_LIMIT_EXCEEDED` | subscribe | WS reject | "이미지는 최대 5장까지 첨부할 수 있습니다" | 첨부 유지, 재시도 가능 |
| `VISION_NOT_SUPPORTED` | subscribe | WS reject | §4.2 문구 | 첨부 유지, 안내 |
| `ATTACHMENT_NOT_FOUND` / `ATTACHMENT_ACCESS_DENIED` | subscribe | WS reject | 기존 | 기존 |
| 벤더 400(이미지 거부 등) | 실행 중 | `RUN_FAILED` | 기존 실패 메시지 | 기존 경로. 서브에이전트 치환으로 발생 확률 최소화 |

### 6.2 Error Response Format

기존 형식 유지: HTTP `{"detail": {"code", "message"}}`, WS `{"type":"error","data":{"code","message"}}`.

### 6.3 서버 보수 동작

- 서브에이전트 모델 조회 결과가 None 이면 기존 컴파일 규칙대로 부모 모델을 쓰며, 그 모델의 supports_vision 으로 판정한다(v0.2 정정 — 서브 그래프도 같은 모델로 컴파일되므로 일관). 이미지 블록 재생성(파일 읽기) 실패 → 마커.
- 승인 게이트 재개 스냅샷(approval_request)은 `redact_messages()`로 이미지 블록을 마커로 바꾼 뒤 직렬화한다(v0.2, Analysis G-C1). 재개 시 이미지는 다시 전달되지 않는다.
- `ImageBlockBuilder.supports(provider)==False` → precheck 거부(실행 전).
- 리사이즈 중 예외 → 400 `INVALID_ATTACHMENT`(손상 파일로 취급), 스택 트레이스 로깅.
- cleanup 실패 → warning 로그, 응답 흐름 영향 없음(기존).

---

## 7. Security Considerations

| 항목 | 설계 |
|------|------|
| 위장 파일 | 확장자·MIME 헤더·매직 넘버 삼중 검증 + PIL `verify()` 후 재오픈 |
| 디코딩 폭탄 | `Image.MAX_IMAGE_PIXELS = 40_000_000`(설정값) 초과 → `DecompressionBombError` → 400 |
| 소유자 검증 | 기존 `AttachmentResolver.resolve`의 `owner_user_id == viewer` 그대로 |
| 경로 노출 | `_render_attachment_block`은 `file_name`만 표기(기존 규칙). 이미지 dict의 `file_path`는 프롬프트에 넣지 않는다 |
| 바이트 누출 | DB·요약 입력·벡터 DB·실행 이력(step input/output summary)·로그에 base64 금지. `redact_image_blocks()`를 step_tracking과 로거 직렬화 전에 적용. 계약 테스트로 `"data:image"` 문자열이 저장 경로에 등장하지 않음을 검사 |
| 프롬프트 가드 | 텍스트(query)만 검사(기존). 이미지 내 텍스트는 검사 대상 아님 — 문서에 명시 |
| EXIF | 리사이즈 시 EXIF 방향만 반영하고 메타데이터는 제거(재인코딩) |
| 메모리 | 리사이즈는 `asyncio.to_thread`로 실행, 업로드는 1파일/요청(기존) |

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: 단위 | 정책·헬퍼·normalizer·block builder·메시지 조립·서브에이전트 치환·축약 필터 | pytest | Do |
| L1: API | 업로드 라우터(이미지 201/400/413), WS subscribe 거절 코드 2종 | pytest TestClient | Do |
| L2: UI | ChatInput paste/drop/pick, 비활성, 칩 제거, 장수 초과 | Vitest + RTL + MSW | Do |
| L3: E2E(수동) | 비전 에이전트 2종(OpenAI·Anthropic) 이미지 2장 질의, 미지원 에이전트 거부, 엑셀+이미지 동시, 서브에이전트 위임 | 실서버 + 브라우저 | Check |
| 계약 | `agent_builder`·`agent_run`에서 `.content`를 문자열로 직접 쓰는 지점 금지 | pytest(AST/grep) | Do |

### 8.2 L0/L1 시나리오 (백엔드)

| # | 대상 | 테스트 | 기대 |
|---|------|--------|------|
| 1 | `AttachmentPolicy` | `.png/.jpg/.jpeg/.webp` → IMAGE, `.gif/.svg` → InvalidAttachmentError | 타입 판별 |
| 2 | `AttachmentPolicy.validate_image_bytes` | 확장자 png + jpeg 매직 | InvalidAttachmentError |
| 3 | `ImageNormalizer` | 3000×1000 png → 1568×523, 알파 유지, EXIF 회전 jpg → 회전 반영, 작은 이미지 → 원본 바이트 그대로 | 크기·모드 |
| 4 | `ImageNormalizer` | 결과가 원본보다 크면 원본 유지 | 바이트 동일 |
| 5 | `ImageBlockBuilder` | provider 4종 포맷, `detail` 포함/생략, 미지원 provider `supports()==False` | 블록 dict |
| 6 | `message_text()` | str → 그대로, list(text+image) → text만 join, dict/BaseMessage 양쪽 | 문자열 |
| 7 | `redact_image_blocks()` / `redact_messages()` | list content의 image 블록 → `"[image:<mime>]"` 치환(블록엔 치수가 없어 mime 만), str은 그대로. messages 단위 복사본 | base64 부재 |
| 8 | `UploadAttachmentUseCase` | 이미지: normalizer 호출 후 저장, width/height 반환. 엑셀: normalizer 미호출 | 호출 여부 |
| 9 | 업로드 라우터 | png 201 + width/height, gif 400, 11MiB 413 | 상태·코드 |
| 10 | `_resolve_ws_attachments` | 이미지 6장 → `ATTACHMENT_LIMIT_EXCEEDED`, 5장 OK, 이미지 dict에 mime/file_name 포함 | 코드·dict |
| 11 | `precheck_attachments` | supports_vision=false → VisionNotSupportedError, true → 통과, 이미지 없음 → 즉시 반환(에이전트 미조회) | 예외 |
| 12 | ws_router | precheck 예외 → `VISION_NOT_SUPPORTED` reject, stream 미호출, cleanup 호출됨 | 이벤트·호출 |
| 13 | `_build_messages` | 이미지 2장 → 마지막 user content가 list(text+2 blocks), 이전 턴 str 유지. 이미지 없음 → 기존과 바이트 동일 | 구조 |
| 14 | `_save_user_message` | 저장 content = query + 마커, base64 없음 | DB 문자열 |
| 15 | `_render_attachment_block` | 이미지 2장 + 엑셀 1 → 문구에 "이미지 2장" 포함, 강제 라우팅은 엑셀만 | 문자열·훅 |
| 16 | `AttachmentRoutingHooks` | 이미지만 첨부 → `force_worker` 없음 | None |
| 17 | `_wrap_sub_agent` | 서브 모델 supports_vision=true → 입력 마지막 user 블록 list에 이미지 포함, false → 마커 문장, 조회 실패 → 마커 | 입력 구조 |
| 18 | 검색 파이프라인/요약 입력 | list content 턴이 있어도 텍스트만 전달(base64 부재) | 문자열 |
| 19 | step_tracking | list content → input_summary에 `data:image` 부재 | 문자열 |
| 20 | 계약 테스트 | `src/application/agent_builder/**`, `src/application/agent_run/**`에서 `getattr(m, "content", "")`·`.content` 직접 문자열 연산 0건(허용 목록: 헬퍼 모듈 자체) | 0건 |
| 21 | 회귀 | 기존 `test_supervisor_attachment.py`, `test_ws_agent_router.py`, `test_upload_and_resolver.py`, `test_store.py` 전량 | pass |

### 8.3 L2: UI Action Test Scenarios

| # | 컴포넌트 | 액션 | 기대 |
|---|---|---|---|
| 1 | ChatInput | 이미지 버튼 클릭 → png 선택 | `onAttachFiles([file])` 호출 |
| 2 | ChatInput | textarea paste(clipboard files=png) | `onAttachFiles` 호출, 텍스트 미삽입 |
| 3 | ChatInput | textarea paste(텍스트만) | 기본 붙여넣기, `onAttachFiles` 미호출 |
| 4 | ChatInput | drop(png, txt) | png만 전달, txt 토스트 |
| 5 | ChatInput | `visionSupported=false` | 버튼 disabled, paste/drop 무시 |
| 6 | ChatInput | 칩 ✕ | `onRemoveAttachment(id)` |
| 7 | validators | 6번째 이미지 / 11MiB / gif | 각 사유 반환 |
| 8 | ChatPage | 업로드 성공 2건 + 엑셀 1건 → 전송 | subscribe attachments 길이 3, type 조합 정확 |
| 9 | ChatPage | 서버 `VISION_NOT_SUPPORTED` | 오류 메시지 표시, 첨부 유지 |
| 10 | 말풍선 | 전송 후 | 썸네일 2개 렌더 |

### 8.4 L3: E2E Scenario (수동, Check 단계)

| # | 시나리오 | 성공 기준 |
|---|---|---|
| 1 | OpenAI 비전 에이전트: 표 캡처 2장 + "3분기 값은?" | 답변이 이미지의 수치를 인용 |
| 2 | Anthropic 비전 에이전트: 동일 | 동일 |
| 3 | 비전 미지원 에이전트 | 버튼 비활성, 강제 전송 시 `VISION_NOT_SUPPORTED` |
| 4 | 엑셀 + 이미지 동시 | 엑셀 분석 워커 강제 라우팅 유지, 이미지도 답변에 반영 |
| 5 | 비전 미지원 서브에이전트에 위임되는 질문 | 실행 실패 없음, 서브 답변에 "이미지를 볼 수 없음" 반영 |
| 6 | 턴 종료 후 | 업로드 디렉터리 비어 있음, DB content에 마커만, ai_run_step input_summary에 base64 없음 |
| 7 | 다음 턴 "그럼 2분기는?" | 이미지 미전달(모델이 이전 답변 텍스트만 참조) |

### 8.5 Seed Data Requirements

| Entity | 조건 |
|---|---|
| `llm_model` | supports_vision=true 모델 2종(openai·anthropic), false 모델 1종, API 키 env 존재 |
| `agent` | 위 모델 각각을 연결한 에이전트 3개, 그중 1개는 비전 미지원 서브에이전트 포함 |
| 테스트 이미지 | `tests/fixtures/images/` png(알파), jpg(EXIF 회전), webp, 3000px png, 위장 파일(gif→.png) — 코드로 생성(PIL), 바이너리 커밋 최소화 |

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Layer | 파일 | 책임 | 금지 |
|---|---|---|---|
| domain | `agent_attachment/value_objects.py`, `policies.py`, `exceptions.py`, `interfaces.py` | IMAGE 타입·확장자·매직 넘버·장수·마커 규칙·포트 2종 | PIL·LangChain·파일 I/O |
| application | `agent_attachment/upload_use_case.py`, `resolver.py`; `agent_builder/message_content.py`(신규 헬퍼), `run_agent_use_case.py`, `workflow_compiler.py`, `supervisor_nodes.py`, `sub_agent_context.py`; `agent_run/step_tracking.py` | 흐름 제어·메시지 조립·치환·축약 | 벤더 포맷 하드코딩(포트 경유) |
| infrastructure | `agent_attachment/image_normalizer.py`(신규), `agent_attachment/image_block_builder.py`(신규) | PIL 리사이즈, 벤더 블록 포맷 | 비즈니스 규칙 |
| interfaces | `api/routes/agent_attachment_router.py`, `ws_router.py`, `main.py`(DI) | 응답 필드, 사전 검증·거절 코드, 주입 | 비즈니스 로직 |

`message_content.py`는 application 계층 순수 함수 모듈(LangChain `BaseMessage` 속성 접근만, 벤더 포맷 무지).

---

## 10. Coding Convention Reference

### 10.3 Environment Variables

```
AGENT_ATTACHMENT_IMAGE_MAX_COUNT=5
AGENT_ATTACHMENT_IMAGE_MAX_EDGE_PX=1568
AGENT_ATTACHMENT_IMAGE_JPEG_QUALITY=90
AGENT_ATTACHMENT_IMAGE_MAX_PIXELS=40000000
AGENT_ATTACHMENT_IMAGE_DETAIL=high        # openai detail (high|low|auto)
```
`config.py`에 동일 이름 소문자 필드 5종 추가, `.env.example` 갱신.

### 10.4 This Feature's Conventions

- 파일·모듈 상단 `# Design Ref: chat-image-attachment §n` 주석, 핵심 로직에 `# Plan SC:`.
- 함수 40줄·if 중첩 2단계 준수. `_build_messages`는 이미지 조립을 `_compose_user_content()`로 분리.
- 로깅: 이미지 업로드/조립 로그에 `file_id`, `mime`, `width`, `height`, `bytes`만. base64·경로 금지.
- 프론트: 런타임 상수는 `src/types/agentAttachment.ts`의 `as const`(컴포넌트 파일 export 금지 규칙).

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/agent_attachment/
│   ├── value_objects.py        (M) IMAGE, ImageDimensions, StoredAttachment.width/height
│   ├── policies.py             (M) ALLOWED_EXT[IMAGE], sniff/validate_image_bytes, ImageAttachmentPolicy
│   ├── exceptions.py           (M) TooManyImagesError, VisionNotSupportedError
│   └── interfaces.py           (M) ImageNormalizerPort, ImageBlockBuilderPort
├── application/
│   ├── agent_attachment/upload_use_case.py   (M) 이미지 분기 → normalizer
│   ├── agent_attachment/resolver.py          (M) 이미지 dict에 mime/file_name
│   ├── agent_builder/message_content.py      (N) message_text, redact_image_blocks, is_multimodal
│   ├── agent_builder/run_agent_use_case.py   (M) precheck_attachments, 모델 해석 선행, _compose_user_content, 마커 저장
│   ├── agent_builder/supervisor_nodes.py     (M) _render_attachment_block 이미지 문구
│   ├── agent_builder/workflow_compiler.py    (M) 문자열 지점 헬퍼 치환, _wrap_sub_agent 이미지 전달/마커
│   ├── agent_builder/sub_agent_context.py    (M) views content → message_text
│   ├── agent_builder/action_pipeline.py      (M) 헬퍼 치환
│   └── agent_run/step_tracking.py            (M) _extract_content → redact + message_text
├── infrastructure/agent_attachment/
│   ├── image_normalizer.py     (N) PilImageNormalizer
│   └── image_block_builder.py  (N) VendorImageBlockBuilder
├── api/routes/agent_attachment_router.py     (M) width/height
├── api/routes/ws_router.py                   (M) 장수 검증, precheck, 코드 2종
├── api/main.py                               (M) DI: normalizer, block builder, config
└── config.py                                 (M) 설정 5종
idt/tests/
├── domain/agent_attachment/test_attachment_policy.py        (M) + test_image_policy.py (N)
├── application/agent_attachment/test_upload_and_resolver.py (M)
├── application/agent_builder/test_message_content.py        (N)
├── application/agent_builder/test_message_content_contract.py (N, AST 계약)
├── application/agent_builder/test_build_messages_image.py   (N)
├── application/agent_builder/test_sub_agent_image_forward.py (N)
├── application/agent_builder/test_supervisor_attachment.py  (M)
├── application/agent_run/test_step_tracking_redact.py       (N)
├── infrastructure/agent_attachment/test_image_normalizer.py (N)
├── infrastructure/agent_attachment/test_image_block_builder.py (N)
├── api/test_agent_attachment_router.py                      (M)
└── api/test_ws_agent_router.py                              (M)
idt_front/src/
├── types/agentAttachment.ts                  (M)
├── utils/imageAttachmentValidators.ts        (N) + .test.ts
├── services/agentAttachmentService.ts        (M) uploadImage
├── components/chat/AttachmentChip.tsx        (N) + .test.tsx
├── components/chat/ChatInput.tsx             (M) + ChatInput.image.test.tsx (N)
├── pages/ChatPage/index.tsx                  (M) + 기존 테스트 보강
├── components/chat/(사용자 말풍선)            (M) imagePreviews
└── __tests__/mocks/handlers.ts               (M)
```

### 11.2 Implementation Order

1. [ ] **domain**: 타입·정책·예외·포트 (+ 테스트 1, 2)
2. [ ] **infra**: `PilImageNormalizer`, `VendorImageBlockBuilder` (+ 테스트 3, 4, 5), `pillow` 명시
3. [ ] **config/DI**: 설정 5종, `main.py` 주입, `.env.example`
4. [ ] **업로드 경로**: `UploadAttachmentUseCase` 이미지 분기, 라우터 응답 (+ 테스트 8, 9)
5. [ ] **헬퍼**: `message_content.py` + 계약 테스트 (+ 테스트 6, 7, 20) → 기존 문자열 지점 치환(`workflow_compiler` 5곳, `run_agent_use_case` 3곳, `action_pipeline` 1곳, `sub_agent_context` 2곳, `step_tracking`) (+ 테스트 18, 19)
6. [ ] **실행 경로**: `resolver` 이미지 dict, `ws_router` 장수·precheck·코드, `RunAgentUseCase.precheck_attachments`·모델 해석 선행·`_compose_user_content`·마커 저장 (+ 테스트 10~14)
7. [ ] **그래프**: `_render_attachment_block` 문구, `_wrap_sub_agent` 이미지 전달/마커 (+ 테스트 15, 16, 17)
8. [ ] **프론트 타입·서비스·검증기** (+ 테스트 7)
9. [ ] **프론트 UI**: `AttachmentChip`, `ChatInput` paste/drop/pick/비활성, `ChatPage` 배열 상태·비전 여부·오류 매핑, 말풍선 썸네일 (+ 테스트 1~6, 8~10)
10. [ ] 회귀 전량(테스트 21) + `verify-architecture`·`verify-logging`·`verify-tdd`
11. [ ] 수동 E2E(§8.4) 및 SOT·wiki 어긋남 보고

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 첨부 도메인·인프라·업로드 | `module-1` | 순서 1~4: IMAGE 타입, 정책, normalizer, block builder, 설정/DI, 업로드 API | 30-40 |
| 메시지 콘텐츠 헬퍼·치환 | `module-2` | 순서 5: `message_content.py`, 계약 테스트, 기존 지점 치환, step_tracking 축약 | 25-35 |
| 실행 경로·그래프 | `module-3` | 순서 6~7: resolver, ws_router 검증·코드, RunAgentUseCase 조립·precheck, supervisor 문구, 서브에이전트 전달 | 35-45 |
| 프론트 | `module-4` | 순서 8~9: 타입·서비스·검증기·칩·ChatInput·ChatPage·말풍선 | 40-50 |
| 통합 검증 | `module-5` | 순서 10~11: 회귀·verify 스킬·수동 E2E·보고 | 15-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 55-75 |
| Session 3 | Do | `--scope module-3` | 35-45 |
| Session 4 | Do | `--scope module-4` | 40-50 |
| Session 5 | Do + Check | `--scope module-5` → `/pdca analyze` | 30-40 |

의존: module-3은 module-1·2 선행. module-4는 module-1(업로드 응답 계약)만 선행하면 되어 module-3과 병행 가능.

---

## 12. 설계 결정 기록

| ID | 결정 | 근거 |
|----|------|------|
| D-01 | 이미지 블록은 상태 HumanMessage에 싣는다 | 모든 LLM 소비자(supervisor 판단·워커·final_answer·FINISH 단락)가 배선 없이 본다. 같은 에이전트 내 워커는 전부 같은 LLM을 쓰므로 안전 |
| D-02 | `message_text()` 단일 헬퍼 + AST 계약 테스트 | 치환 누락이 조용한 오동작으로 이어지는 최대 위험을 테스트로 차단 |
| D-03 | 서브에이전트만 비전 여부 분기 | 모델이 달라지는 유일한 지점. 입력이 텍스트 블록으로 재조립되므로 "전달 여부"를 명시적으로 결정해야 함 |
| D-04 | 검색 파이프라인·요약·QG·근거 판정에는 텍스트만 | 파이프라인 전용 모델은 비전 미보장. 이미지는 답변 생성 모델만 본다 |
| D-05 | 비전 사전 검사는 `RunAgentUseCase.precheck_attachments`에서, 호출은 ws_router | 모델 해석 로직이 UseCase에 있고, 실행 시작 전(RUN_STARTED 전) 거절해야 함 |
| D-06 | 모델 해석을 메시지 저장·조립보다 앞으로 이동 | provider별 블록 생성과 마커 저장에 모델 정보가 필요 |
| D-07 | 리사이즈는 업로드 시 서버 | 저장 용량·state 크기·토큰 동시 절감. 결과가 더 크면 원본 유지 |
| D-08 | `ImageBlockBuilder`를 새 인프라 모듈로, 기존 비전 어댑터는 무변경 | 어댑터는 LLM 인스턴스를 생성하는 무거운 객체. 포맷만 필요하므로 가벼운 빌더 분리(포맷 중복 2곳은 테스트로 동치 고정) |
| D-09 | 프론트 비전 여부는 LLM 모델 목록 + 에이전트 llm_model_id로 계산 | 추가 API 없이 기존 응답으로 충분. 권위는 서버 precheck |
| D-10 | 칩 제거 시 서버 삭제 API 없음 | 기존 TTL(1시간) 회수로 충분. 범위 최소화 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | Initial draft (Option C) | 배상규 |
| 0.2 | 2026-10-30 | Act-1 정정: `build_from_path` 포트, resolver 치수, my-agents `llm_model_id`, precheck 위치·override, 서브 모델 조회 실패 동작, 승인 스냅샷 축약, 마커 형식 | 배상규 |
