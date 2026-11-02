# chat-image-attachment Gap Analysis

> **Summary**: 에이전트 채팅 이미지 첨부의 설계(Design v0.1)와 구현(idt + idt_front)을 정적으로 대조했다. 서버를 띄우지 않아 런타임 검증은 하지 않았다.
>
> **Author**: gap-detector (bkit) — 저장은 메인 세션
> **Created**: 2026-10-30
> **Status**: Draft
> **Plan**: [chat-image-attachment.plan.md](../01-plan/features/chat-image-attachment.plan.md)
> **Design**: [chat-image-attachment.design.md](../02-design/features/chat-image-attachment.design.md)
> **PRD**: 없음

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

## 1. 분석 개요

| 항목 | 값 |
|------|----|
| 분석 대상 | chat-image-attachment |
| 설계 문서 | `idt/docs/02-design/features/chat-image-attachment.design.md` |
| 구현 경로 | `idt/src/{domain,application,infrastructure,api}/…agent_attachment…`, `idt/src/application/agent_builder/*`, `idt_front/src/{types,utils,services,components/chat,pages/ChatPage}` |
| 분석 방식 | 정적 분석(Read/Grep). **서버를 띄우지 않아 런타임 검증(L1~L3)은 하지 않음** |
| 미확인 범위 (gap-detector 기준) | 테스트 파일 본문과 실행 결과, `MessageBubble.tsx`, `types/agent.ts`·`agentSubscriptionService.ts`의 `llmModelId` 매핑, `__tests__/mocks/handlers.ts`, `useAgentRunStream.ts` 오류 매핑, `GET /api/v1/llm-models`가 일반 사용자에게 `supports_vision`을 내려주는지, 기존 비전 어댑터 무변경 여부 |

> 메인 세션 보충(Do 단계 기록): 테스트는 백엔드 1,502건(첨부·agent_builder·agent_run·WS 스위트)·프론트 38건(신규 7파일) 통과, 전체 회귀는 상시 실패 목록(백 53·프론트 9)과 동일. `MessageBubble.tsx`는 `imagePreviews` 썸네일 렌더 구현됨. `toAgentSummary`가 `llmModelId: agent.llm_model_id`로 매핑. `/api/v1/llm-models`는 `get_current_user` 인증(일반 사용자 접근 가능)이며 응답 `LlmModel.supports_vision` 옵셔널 필드 존재. 기존 비전 어댑터 무변경(동치 테스트 `test_image_block_builder.py::TestParityWithVisionAdapters`).

---

## 2. 점수

### 2.1 축별 점수

| 축 | 점수 | 상태 | 근거 요약 |
|----|:----:|:----:|-----------|
| Structural | 95% | ✅ | §11.1의 src 파일·DI·config·env·pyproject는 모두 확인했다. 테스트 파일명 1건이 다르고(`test_build_messages_image.py` → `test_run_agent_image_attachment.py`), MessageBubble·MSW 핸들러는 확인하지 못했다 |
| Functional | 84% | ⚠️ | §5.4 UI 체크리스트 80%(10개 중 완전 7, 부분 2, 미충족 1), 백엔드 로직 약 88%(리사이즈 비동기 미적용, 승인 스냅샷 누출, 실효 모델 미반영) |
| API Contract | 85% | ⚠️ | 5개 계약 중 완전 3, 부분 2(업로드 오류 코드 미매핑, 비전 정보 경로 일부 미확인) |

### 2.2 Match Rate (정적 공식)

```
Overall = Structural×0.2 + Functional×0.4 + Contract×0.4
        = 95×0.2 + 84×0.4 + 85×0.4
        = 19.0 + 33.6 + 34.0 = 86.6
```

**Overall Match Rate: 87%** (런타임 미실행, 정적 공식 적용)

---

## 3. Structural 대조 (설계 §11.1)

### 3.1 백엔드 src

| 설계 파일 | 구현 | 비고 |
|-----------|:----:|------|
| domain/agent_attachment/value_objects.py | ✅ | `IMAGE`(L20), `ImageDimensions`(L23-29), `StoredAttachment.width/height`(L56-57) |
| domain/agent_attachment/policies.py | ✅ | `ALLOWED_EXT[IMAGE]`(L32), `sniff_image_mime`(L63-72), `validate_image_bytes`(L74-86), `ImageAttachmentPolicy`(L93-126). 설계에 없던 `mime_for`가 추가됨 |
| domain/agent_attachment/exceptions.py | ✅ | `TooManyImagesError`(L24), `VisionNotSupportedError`(L28-36, 설계 §4.2 문구와 같음) |
| domain/agent_attachment/interfaces.py | ✅ | `ImageNormalizerPort`(L39), `ImageBlockBuilderPort`(L52). 설계에 없던 `build_from_path`가 추가됨 |
| application/agent_attachment/upload_use_case.py | ✅ | 이미지 분기(L55-56, L77-88) |
| application/agent_attachment/resolver.py | ✅ | 이미지 dict에 mime/file_name/width/height(L45-52) |
| application/agent_builder/message_content.py | ✅ | `message_text`, `is_multimodal`, `image_blocks`, `redact_image_blocks` |
| application/agent_builder/run_agent_use_case.py | ✅ | `precheck_attachments`(L686), `_attach_turn_images`(L726), 마커 저장(L160-169, L341-345), 모델 해석 선행(L848-863) |
| application/agent_builder/supervisor_nodes.py | ✅ | `_render_attachment_block` 이미지 문구(L30-51) |
| application/agent_builder/workflow_compiler.py | ✅ | `_forward_turn_images`(L2656), `_wrap_sub_agent`(L2694), 서브 모델 비전 여부 전달(L1371-1376) |
| application/agent_builder/sub_agent_context.py | ✅ | `message_text` 적용(L56, L64) |
| application/agent_builder/action_pipeline.py | ✅ | `message_text` 적용(L97, L111, L171, L174) |
| (추가) collect_pipeline.py / search_pipeline.py / supervisor_hooks.py | ✅ | `message_text` 적용 |
| application/agent_run/step_tracking.py | ✅ | `_content_for_summary` → `message_text(keep_image_markers=True)`(L56-61) |
| infrastructure/agent_attachment/image_normalizer.py | ✅ | `PilImageNormalizer` |
| infrastructure/agent_attachment/image_block_builder.py | ✅ | `VendorImageBlockBuilder` |
| api/routes/agent_attachment_router.py | ✅ | `width/height`(L34-35, L80-81) |
| api/routes/ws_router.py | ✅ | precheck 호출과 오류 코드 2종(L253-275) |
| api/main.py | ✅ | DI(L761, L1113-1126, L3061-3062, L3271-3273) |
| config.py | ✅ | 설정 5종(L210-214) |
| .env.example | ✅ | L59-63 |
| pyproject.toml | ✅ | `pillow>=10.0`(L34) |

### 3.2 백엔드 테스트

| 설계 | 구현 | 비고 |
|------|:----:|------|
| test_image_policy.py (N) | ✅ | |
| test_attachment_policy.py (M) | ✅ | `image.png` 케이스를 `image.gif`로 조정 |
| test_upload_and_resolver.py (M) | ✅ | |
| test_message_content.py (N) | ✅ | |
| test_message_content_contract.py (N) | ✅ | 범위가 설계보다 좁음(G-I4) |
| test_build_messages_image.py (N) | ⚠️ | `test_run_agent_image_attachment.py`로 대체(이름만 다름) |
| test_sub_agent_image_forward.py (N) | ✅ | |
| test_supervisor_attachment.py (M) | ✅ | |
| test_step_tracking_redact.py (N) | ✅ | |
| test_image_normalizer.py / test_image_block_builder.py (N) | ✅ | |
| test_agent_attachment_router.py / test_ws_agent_router.py (M) | ✅ | |

### 3.3 프론트

| 설계 | 구현 | 비고 |
|------|:----:|------|
| types/agentAttachment.ts | ✅ | `AttachmentType`, 응답 `width?/height?`, `PendingAttachment`, `as const` 상수 |
| utils/imageAttachmentValidators.ts (+test) | ✅ | |
| services/agentAttachmentService.ts | ✅ | `uploadImage`와 `uploadExcel`이 같은 함수 |
| components/chat/AttachmentChip.tsx (+test) | ✅ | |
| components/chat/ChatInput.tsx (+ChatInput.image.test) | ✅ | |
| pages/ChatPage/index.tsx (+imageAttachment.test) | ✅ | |
| 사용자 말풍선 imagePreviews | ✅ | `MessageBubble.tsx` `UserMessage`에 썸네일 렌더(메인 세션 확인) |
| `__tests__/mocks/handlers.ts` (M) | — | 서비스 테스트가 `server.use`로 핸들러를 직접 등록해 공용 핸들러 변경 불필요 |
| hooks/useAgentRunStream.ts | 변경 없음 (설계도 "확인"만 요구) | |
| (추가) types/agent.ts, types/chat.ts, services/agentSubscriptionService.ts | ✅ | D-09용 `llmModelId` 매핑, `Message.imagePreviews` |

---

## 4. Functional 대조

### 4.1 §5.4 Page UI Checklist

| # | 항목 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | 이미지 버튼은 agent 모드에서만 보이고, 비전 미지원이면 disabled + title | ✅ | ChatInput.tsx:194, 229-235 / ChatPage:549, 554-555 |
| 2 | paste는 이미지가 있을 때만 가로채고 텍스트는 기본 동작 | ✅ | ChatInput.tsx:75-81 |
| 3 | drop: 입력 카드 전체가 드롭존, 시각 피드백, 비이미지는 무시하고 토스트 | ⚠️ | 드롭존과 피드백은 있음(L132-146). 비이미지는 `imageFilesOf`가 조용히 걸러내 안내가 없음(L42-43, L93). 비전 미지원 상태에서는 dragover에서 `preventDefault`를 하지 않아 브라우저 기본 동작(파일 열기)이 일어남(L84) |
| 4 | 칩: 썸네일 40px, 파일명 truncate, ✕ aria-label | ✅ | AttachmentChip.tsx:20, 25, 30 |
| 5 | 6장째부터 무시하고 안내 | ✅ | validators.ts:51-53, ChatPage:346-348 (토스트 대신 인라인 안내. Plan FR-14가 인라인도 허용) |
| 6 | 10MiB 초과·미허용 형식은 업로드 전 안내 | ✅ | validators.ts:43-50 |
| 7 | 업로드 중 전송 버튼 비활성 | ❌ | ChatInput.tsx:111 `canSend`가 `attachmentUploading`을 보지 않고, ChatPage:546 `isLoading`에도 업로드 상태가 없음. 업로드 도중 전송하면 아직 업로드 중인 이미지가 빠진 채 전송됨 |
| 8 | 전송 후 첨부 목록 비움, 말풍선에 썸네일 | ✅ | 목록 비움(ChatPage:438), `imagePreviews` 전달(L405), MessageBubble 렌더(메인 세션 확인) |
| 9 | 서버 거절 메시지 표시 | ✅ | ChatPage:304-313, types/agentAttachment.ts:53-59 |
| 10 | 히스토리 재조회 시 마커 텍스트만 표시 | ✅ | 서버가 마커 문자열만 저장(run_agent_use_case.py:160-169). 프론트는 서버 메시지의 content를 그대로 표시 |

UI 체크리스트 점수: (7 + 0.5×2) / 10 = **80%** (gap-detector 판정 유지; #8 확인으로 실제는 85%)

### 4.2 백엔드 로직 완결성

| 영역 | 판정 | 근거 |
|------|:----:|------|
| 확장자·매직 넘버 검증 | ✅ | policies.py:74-86, upload_use_case.py:81 |
| 리사이즈·EXIF·알파·원본 유지·폭탄 차단 | ✅ | image_normalizer.py:27-82 |
| 리사이즈를 스레드풀에서 실행(§7 메모리, NFR 성능) | ❌ | router가 async 핸들러 안에서 `use_case.execute`를 동기로 호출함(agent_attachment_router.py:59) |
| 리사이즈 실패 시 400 + 스택 트레이스 로깅(§6.3) | ⚠️ | 400은 반환함. 로거 호출이 없음(router:64-68) |
| 장수 상한 → ATTACHMENT_LIMIT_EXCEEDED | ✅ | run_agent_use_case.py:705-707, ws_router.py:264-269 |
| 비전 사전 검사 → VISION_NOT_SUPPORTED | ⚠️ | run_agent_use_case.py:711-724. 실효 모델(override) 대신 `agent.llm_model_id`를 사용 |
| 이번 턴 list content 조립 | ✅ | run_agent_use_case.py:726-754 |
| DB에는 마커만 저장 | ⚠️ | conversation_message에는 마커만 저장됨. 승인 게이트 스냅샷에는 base64가 들어감(G-C1) |
| supervisor 인지 블록, 강제 라우팅 제외 | ✅ | supervisor_nodes.py:46-51, supervisor_hooks.py:59 |
| 서브에이전트 이미지 전달 또는 마커 | ✅ | workflow_compiler.py:2656-2692 (모델 조회 실패 시 동작은 설계와 다름, G-M4) |
| step_tracking에 base64 없음 | ✅ | step_tracking.py:56-61 |
| 턴 종료 시 cleanup | ✅ | ws_router.py:318-321 (거절 경로도 finally를 탐) |
| 플레이스홀더·TODO | 없음 | 확인한 src 범위 기준 |

백엔드 로직 점수 ≈ 88%. Functional = (80 + 88) / 2 = **84%**

---

## 5. API Contract 3-way 대조

| # | 계약 | Design | Server | Client | 판정 |
|---|------|:------:|:------:|:------:|:----:|
| 1 | POST /api/v1/agent/attachments 201 `{file_id,type,filename,size,width,height}` | §4.2 | router:28-35, 75-82 | agentAttachment.ts:12-19, service:10-23 | PASS |
| 2 | 업로드 오류 400 INVALID_ATTACHMENT / 413 ATTACHMENT_TOO_LARGE와 사용자 문구 | §4.2, §6.1 | router:64-73 | ChatPage:378-379가 코드와 무관하게 일반 문구 하나를 표시 | PARTIAL |
| 3 | WS subscribe `attachments:[{type:"image"|"excel", file_id}]` | §4.2 | ws_router:122-135 (스키마 변경 없음) | ChatPage:432-435, `AgentAttachmentRef` | PASS |
| 4 | WS 거절 `ATTACHMENT_LIMIT_EXCEEDED` / `VISION_NOT_SUPPORTED`, 형식 `{"type":"error","data":{code,message}}` | §4.2, §6.2 | ws_router:143-155, 264-275 | agentAttachment.ts:53-59, ChatPage:304-313 (`view.error.code` 매핑) | PASS |
| 5 | 비전 여부 안내 정보(D-09): 에이전트 `llm_model_id` + `/llm-models`의 `supports_vision` | §5.2, D-09 | `MyAgentSummary.llm_model_id`(schemas.py:389, list_my_agents_use_case.py:131) | ChatPage:140-144 `selectedAgent.llmModelId`, `toAgentSummary` 매핑(메인 세션 확인) | PASS(메인 세션 확인 후) |

Contract 점수: (1 + 0.5 + 1 + 1 + 0.75) / 5 = **85%** (gap-detector 판정 유지)

---

## 6. Plan 성공 기준

### 6.1 Definition of Done (§4.1)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| FR-01~FR-18 구현 및 테스트 통과 | ⚠️ | 구현은 대부분 확인(§6.3). 테스트는 Do 단계에서 통과(백엔드 1,502·프론트 38) |
| OpenAI·Anthropic 비전 에이전트 수동 E2E | 미실행(서버 필요) | 정적으로는 블록 포맷만 확인(image_block_builder.py:26-43) |
| 비전 미지원: 프론트 비활성 + 서버 VISION_NOT_SUPPORTED | ⚠️ | 정적 확인: ChatInput.tsx:229, run_agent_use_case.py:718-724, ws_router.py:270-275. E2E는 미실행. 실효 모델 미반영(G-I3) |
| 비전 미지원 워커 입력에 마커만(단위 테스트) | ✅ | workflow_compiler.py:2667-2674, test_sub_agent_image_forward.py |
| 턴 종료 후 파일 없음, DB에는 마커만 | ⚠️ | cleanup(ws_router.py:318-321)과 마커 저장(run_agent_use_case.py:160-169)은 확인. 승인 스냅샷 누출(G-C1). E2E는 미실행 |
| 엑셀 첨부 수동 E2E + pytest/Vitest 전체 회귀 | ⚠️ | 전체 회귀는 상시 실패 목록과 동일(Do 단계). 엑셀 수동 E2E 미실행 |
| verify-architecture·verify-logging·verify-tdd | ✅ | Do module-5에서 변경 파일 기준 통과 |
| .env.example·SOT 변경 보고 | ✅ | .env.example 반영(L59-63). SOT·wiki 어긋남 3건 보고(module-5) |

### 6.2 Quality Criteria (§4.2)

| 기준 | 판정 | 근거 |
|------|:----:|------|
| 신규 모듈 커버리지 80% | 미측정 | |
| ruff·eslint 0, tsc 통과 | ✅ | 변경 파일 기준 ruff 신규 0, eslint 0, tsc 210→209 |
| 문자열 content 가정 지점 치환 누락 0 (계약 테스트) | ⚠️ | test_message_content_contract.py:50-56은 `getattr(...,"content")`·`.get("content")`만 잡는다. `.content` 직접 접근 5곳이 남아 있음(G-I4) |

### 6.3 FR 상태 요약

| FR | 판정 | FR | 판정 |
|----|:----:|----|:----:|
| FR-01 | ✅ | FR-10 | ✅ |
| FR-02 | ✅ | FR-11 | ✅ |
| FR-03 | ✅ (스레드풀 미적용은 NFR, G-I1) | FR-12 | ✅ |
| FR-04 | ✅ | FR-13 | ✅ |
| FR-05 | ⚠️ (G-I3) | FR-14 | ⚠️ (G-I5) |
| FR-06 | ✅ (D-08에 따라 별도 빌더 사용) | FR-15 | ✅ |
| FR-07 | ✅ | FR-16 | ✅ |
| FR-08 | ⚠️ (G-I4) | FR-17 | ✅ |
| FR-09 | ⚠️ (G-C1) | FR-18 | ✅ |

---

## 7. 설계 결정 D-01~D-10 준수

| ID | 결정 | 판정 | 근거 |
|----|------|:----:|------|
| D-01 | 이미지 블록은 상태 HumanMessage에 싣는다 | ✅ | run_agent_use_case.py:751-754 |
| D-02 | `message_text()` 단일 헬퍼 + AST 계약 테스트 | ⚠️ | 헬퍼는 있음. 계약 테스트가 `.content` 속성 접근을 잡지 않음 |
| D-03 | 서브에이전트만 비전 여부로 분기 | ✅ | workflow_compiler.py:1371-1376, 2656-2692 (조회 실패 시 동작은 G-M4) |
| D-04 | 검색·요약·QG·근거 판정에는 텍스트만 | ✅ | sub_agent_context.py:56, search_pipeline/collect_pipeline/action_pipeline의 `message_text` |
| D-05 | precheck는 UseCase에 두고 ws_router가 호출 | ⚠️ | 구조는 일치(ws_router.py:255-263). 실효 모델 대신 `agent.llm_model_id` 사용(L711-712) |
| D-06 | 모델 해석을 메시지 저장·조립보다 앞으로 | ✅(부분 편차) | 조립보다는 앞섬(L848-863). 저장은 여전히 모델 해석 전(L342)이지만 마커에 모델 정보가 필요 없어 동작 영향 없음 |
| D-07 | 업로드 시 서버 리사이즈, 결과가 크면 원본 유지 | ✅ | image_normalizer.py:45-47, upload_use_case.py:84-88 |
| D-08 | `ImageBlockBuilder`를 새 인프라 모듈로, 기존 어댑터 무변경 | ✅ | image_block_builder.py, 동치 테스트 |
| D-09 | 프론트 비전 여부 = LLM 모델 목록 + 에이전트 llm_model_id | ✅ | ChatPage:140-144, schemas.py:389 (설계에 없던 `MyAgentSummary.llm_model_id` 추가로 지원) |
| D-10 | 칩 제거 시 서버 삭제 API 없음 | ✅ | ChatPage:385-391 |

---

## 8. Gap 목록

### 🔴 Critical

| ID | 파일:라인 | 내용 | 설계 근거 | 제안 |
|----|-----------|------|-----------|------|
| G-C1 | run_agent_use_case.py:1246-1248, infrastructure/approval/snapshot.py:35-38 | 승인 게이트가 걸린 런은 `state.final_state`(messages 포함)를 그대로 `approval_request` 스냅샷 JSON에 저장한다. 이미지 턴이면 user 메시지의 base64 블록이 DB에 남고, 재개 때 이미지가 다시 전달되어 "해당 턴만" 정책도 깨진다. 조건부 경로이지만 Plan 기준 위반이라 Critical로 분류 | Plan FR-09, Design §7 바이트 누출 | 스냅샷 직렬화 전에 messages의 content에 `redact_image_blocks()`를 적용하거나 이미지 블록을 마커로 바꾼다. "data:image가 저장 경로에 없음" 계약 테스트에 approval 경로를 추가한다 |

### 🟡 Important

| ID | 파일:라인 | 내용 | 설계 근거 | 제안 |
|----|-----------|------|-----------|------|
| G-I1 | api/routes/agent_attachment_router.py:59 | PIL 리사이즈(최대 10MiB, 4천만 픽셀)가 async 핸들러 안에서 동기로 실행되어 이벤트 루프를 막는다 | Design §7 "리사이즈는 `asyncio.to_thread`", Plan NFR Performance | `await asyncio.to_thread(use_case.execute, ...)` |
| G-I2 | components/chat/ChatInput.tsx:111, pages/ChatPage/index.tsx:546 | 업로드 중에도 전송 버튼이 활성이라, 업로드가 끝나지 않은 이미지가 빠진 채 전송될 수 있다 | Design §5.4 #7 | `canSend`에 `!attachmentUploading` 추가 |
| G-I3 | application/agent_builder/run_agent_use_case.py:711-712 | precheck가 `agent.llm_model_id`로 검사한다. 실행은 `_effective_model_id`(override 포함)를 써서 두 판정이 어긋날 수 있다. 현재 WS subscribe 페이로드에는 override 필드가 없어 잠재 결함 | Plan FR-05, Design §4.2 | precheck에 override id를 받아 `_effective_model_id` 재사용 |
| G-I4 | tests/application/agent_builder/test_message_content_contract.py:50-56 | 계약 테스트가 `getattr`/`.get("content")`만 금지한다. `.content` 직접 접근이 남아 있음: supervisor_nodes.py:622, workflow_compiler.py:1739, 2557, 2587, 2744. 모두 AI 응답이라 이미지 턴에서 바로 깨지지는 않지만 설계 #20의 "0건"과 다르다 | Design §8.2 #20, D-02 | `ast.Attribute(attr="content")`도 검사하고 남은 지점을 `message_text()`로 치환 |
| G-I5 | components/chat/ChatInput.tsx:42-43, 83-95 | (a) 이미지가 아닌 파일을 드롭하면 조용히 버려지고 안내가 없다. (b) 비전 미지원일 때 dragover에서 `preventDefault`를 하지 않아 드롭 시 브라우저가 파일을 연다 | Design §5.4 #3, §8.3 L2 #4·#5 | 걸러진 파일을 안내 콜백으로 알리고, 비활성 상태에서도 dragover/drop의 `preventDefault`는 호출 |
| G-I6 | pages/ChatPage/index.tsx:378-379 | 업로드 실패 시 400/413 코드와 무관하게 일반 문구 하나만 보여 준다 | Design §6.1 | `ApiError`의 code/status로 §6.1 문구에 매핑 |

### 🔵 Minor / 의도된 편차 판정

| ID | 파일:라인 | 내용 | 판정 | 제안 |
|----|-----------|------|------|------|
| G-M1 | domain/agent_attachment/interfaces.py:62-66, image_block_builder.py:45-48 | 설계 §3.1 `ImageBlockBuilderPort`에 없는 `build_from_path`가 추가됨 | **의도된 편차(타당)**: application이 파일 I/O를 하지 않게 infrastructure로 내린 것 | 설계 §3.1 포트 정의 갱신 |
| G-M2 | services/agentAttachmentService.ts:25-29 | `uploadImage`와 `uploadExcel`이 같은 함수 | **설계 부합**: §5.3이 "동일 엔드포인트"를 명시함 | 없음 |
| G-M3 | api/routes/ws_router.py:138-140, 256 | 이미지가 없으면 precheck 호출 자체를 건너뜀. 장수 검사도 `_resolve_ws_attachments`가 아니라 precheck 안에 있음 | **의도된 편차(동작 동등)** | 설계 §2.1·§8.2 #10 위치 기술 갱신 |
| G-M4 | application/agent_builder/workflow_compiler.py:1341-1347 | 서브 모델 조회 결과가 None이면 부모 모델(비전 여부 포함)을 그대로 쓰고, 조회 예외는 그대로 전파된다. 설계는 "조회 실패 → 마커"를 요구 | 부분 편차: 서브 그래프도 부모 모델로 컴파일되므로 결과는 일관적 | 설계를 현행 동작으로 갱신하거나 조회 실패 시 `supports_vision=False` 강제 |
| G-M5 | application/agent_builder/message_content.py:77-84 | `redact_image_blocks()`가 src 어디에서도 호출되지 않는다. 마커 형식이 `[image:<mime>]`로 설계 #7의 `<w>x<h>`가 빠짐 | 부분 편차 | G-C1 수정에 이 함수를 쓰면 해소. 마커 형식은 설계 갱신 |
| G-M6 | api/routes/agent_attachment_router.py:55-63 | `UploadFile.content_type`(MIME 헤더)을 검사하지 않는다 | Minor | 헤더 검사 추가 또는 설계 갱신 |
| G-M7 | api/routes/agent_attachment_router.py:64-68 | 리사이즈 실패(InvalidAttachmentError)를 로깅하지 않는다 | Design §6.3 | 400 반환 전에 `logger.warning(..., exception=e)` |
| G-M8 | application/agent_builder/run_agent_use_case.py:733-735 | 빌더가 주입되지 않으면 이미지를 조용히 버린다. stream은 호출자의 precheck에 의존 | Minor | stream에서 방어적 검사 |
| G-M9 | run_agent_use_case.py:737, workflow_compiler.py:2682 | `build_from_path`가 async 경로에서 동기 파일 읽기(리사이즈 후라 장당 수백 KB) | Minor | 필요 시 `to_thread` |
| G-M10 | pages/ChatPage/index.tsx:349-360, 378 | 여러 장 순차 업로드 중 하나가 실패하면 나머지가 중단 | Minor | 항목별 try/catch |
| G-M11 | components/chat/ChatInput.tsx:174 | placeholder에 붙여넣기·드래그 안내가 없음 | Design §5.1 | 문구 추가 |
| G-M12 | api/routes/ws_router.py:216-217 | docstring의 wire protocol이 `[{type:"excel"}]`만 표기 | Minor | 주석 갱신 |
| G-M13 | run_agent_use_case.py:726 | 설계의 `_compose_user_content()`가 `_attach_turn_images()`로 구현됨 | 이름만 다른 동등 구현 | 설계 갱신 |

### 🟢 추가 구현 (설계 X, 구현 O)

| 항목 | 위치 | 판단 |
|------|------|------|
| `MyAgentSummary.llm_model_id` | schemas.py:389, list_my_agents_use_case.py:131 | D-09 지원용 additive 필드. 설계 §4에 응답 필드로 명시 필요 |
| `ImageAttachmentPolicy.mime_for` | policies.py:120-126 | resolver용 확장자→MIME. 타당 |
| resolver 이미지 dict의 width/height | resolver.py:47-52 | additive. 설계 §3.2 갱신 |

---

## 9. 권장 조치

### 즉시 조치 (iterate)
1. G-C1: 승인 스냅샷 직렬화 전 이미지 블록 축약 + 계약 테스트
2. G-I1: 업로드 리사이즈를 `asyncio.to_thread`로
3. G-I2: 업로드 중 전송 비활성
4. G-I3: precheck에 실효 모델 반영
5. G-I4: 계약 테스트에 `.content` 속성 검사 추가 및 잔여 5곳 치환
6. G-I5, G-I6: 드롭 안내와 업로드 오류 코드 매핑

### 문서 갱신 필요
- 설계 §3.1 포트에 `build_from_path`, §3.2 resolver dict에 width/height, §4에 `MyAgentSummary.llm_model_id`, §8.2 #7 마커 형식, §2.1 장수 검사 위치, §6.3 서브 모델 조회 실패 동작

---

## 10. Runtime Verification Plan (실행하지 않음, 서버 필요)

전제: 백엔드 `uvicorn src.main:app --port 8000`, `$TOKEN`은 로그인 JWT, 픽스처 `shot.png`(3000×1000, 알파), `fake.png`(gif 바이트), `big.png`(11MiB), `a.gif`.

### L1: API

| # | 테스트 | 명령 | 기대 상태 | 기대 응답 |
|---|--------|------|:---------:|-----------|
| 1 | png 업로드 성공 + 리사이즈 | `curl -s -X POST http://localhost:8000/api/v1/agent/attachments -H "Authorization: Bearer $TOKEN" -F "file=@shot.png"` | 201 | `.type=="image"`, `.width==1568`, `.height==523` |
| 2 | 엑셀 업로드 시 치수 null | `… -F "file=@sales.xlsx"` | 201 | `.type=="excel"`, `.width==null` |
| 3 | 미허용 확장자 | `… -F "file=@a.gif"` | 400 | `.detail.code=="INVALID_ATTACHMENT"` |
| 4 | 위장 파일 | `… -F "file=@fake.png"` | 400 | `.detail.code=="INVALID_ATTACHMENT"` |
| 5 | 10MiB 초과 | `… -F "file=@big.png"` | 413 | `.detail.code=="ATTACHMENT_TOO_LARGE"` |
| 6 | 미인증 | `curl -s -X POST …/attachments -F "file=@shot.png"` | 401 | |
| 7 | WS 장수 초과 | subscribe에 이미지 6건 | reject | `code=="ATTACHMENT_LIMIT_EXCEEDED"`, RUN_STARTED 없음, 파일 삭제됨 |
| 8 | WS 비전 미지원 | 비전 미지원 에이전트에 이미지 1장 | reject | `code=="VISION_NOT_SUPPORTED"`, message에 모델 표시명, 파일 삭제됨 |
| 9 | WS 정상 | 비전 에이전트 + 이미지 2장 | 1000 | RUN_STARTED → ANSWER_COMPLETED → RUN_COMPLETED, 종료 후 파일 0개 |

### L2: UI (Playwright)

| # | 페이지 | 동작 | 기대 결과 | 기대 API 호출 |
|---|--------|------|-----------|----------------|
| 1 | /chat (비전 에이전트) | 이미지 버튼 → png 선택 | 40px 썸네일 칩 | POST /api/v1/agent/attachments |
| 2 | /chat | textarea에 이미지 클립보드 붙여넣기 | 칩 추가, 텍스트 미삽입 | POST 업로드 |
| 3 | /chat | 텍스트 붙여넣기 | 텍스트 입력, 업로드 없음 | 없음 |
| 4 | /chat | png + txt 드롭 | png 칩, txt 안내(G-I5) | POST 1회 |
| 5 | /chat (비전 미지원 에이전트) | 버튼 확인, 드롭 | 버튼 disabled + title, 드롭 무시(페이지 이탈 없음) | 없음 |
| 6 | /chat | 칩 ✕ 클릭 | 칩 제거 | 없음 |
| 7 | /chat | 6번째 이미지 추가 | "최대 5장" 안내 | 없음 |
| 8 | /chat | 이미지 2 + 엑셀 1 → 전송 | 말풍선 썸네일 2개, 칩 비움 | WS subscribe attachments 길이 3 |
| 9 | /chat | 서버 VISION_NOT_SUPPORTED | 안내 문구, 첨부 복원 | WS error |
| 10 | /chat | 업로드 진행 중 전송 버튼 | disabled (G-I2) | |

### L3: E2E (설계 §8.4)

| # | 시나리오 | 단계 | 성공 기준 |
|---|----------|------|-----------|
| 1 | OpenAI 비전 에이전트 | 표 캡처 2장 + "3분기 값은?" 전송 | 답변이 이미지 속 수치를 인용 |
| 2 | Anthropic 비전 에이전트 | 동일 | 동일 |
| 3 | 비전 미지원 에이전트 | 버튼 확인 → WS 직접 subscribe | 버튼 비활성, `VISION_NOT_SUPPORTED` |
| 4 | 엑셀 + 이미지 동시 | 엑셀 1 + 이미지 1 전송 | 엑셀 분석 워커 강제 라우팅 유지, 이미지도 답변에 반영 |
| 5 | 비전 미지원 서브에이전트 위임 | 위임 유도 질문 | 실행 실패 없음, 서브 답변에 "이미지를 볼 수 없음" 반영 |
| 6 | 턴 종료 후 | DB와 디렉터리 조회 | 업로드 디렉터리 비어 있음, `conversation_message.content`에 마커만, `ai_run_step.input_summary`에 `data:image` 없음 |
| 7 | 다음 턴 "그럼 2분기는?" | 같은 세션에서 후속 질문 | 이미지 미전달(이전 답변 텍스트만 참조) |
| 8 | (추가) 승인 게이트 + 이미지 턴 | 게이트 도구를 쓰는 에이전트에 이미지와 질문 | `approval_request` 스냅샷에 `data:image` 없음(G-C1 검증) |

Playwright 파일 제안: `idt_front/tests/e2e/chat-image-attachment.spec.ts`

---

---

## 11. Act-1 결과 (2026-10-30, 메인 세션)

Checkpoint 5 결정: "지금 모두 수정". Critical 1 + Important 6 을 수정하고 설계 문서를 v0.2 로 정정했다.

| ID | 조치 | 검증 |
|----|------|------|
| G-C1 | `message_content.redact_messages()` 신설, `_persist_approval_if_pending` 이 `_redact_state_images()` 를 거쳐 직렬화 | `TestApprovalSnapshotRedaction` 2건 (payload 에 `data:image` 부재, 원본 state 불변, 호출 경로 소스 검사) |
| G-I1 | 업로드 라우터가 `asyncio.to_thread(use_case.execute, ...)` 로 실행 | 기존 라우터 테스트 전량 통과 |
| G-I2 | `ChatInput.canSend` 에 `!attachmentUploading` | `업로드 중에는 전송 버튼이 비활성이다` |
| G-I3 | `precheck_attachments(llm_model_id_override=...)` 로 실효 모델 판정 | `TestPrecheckOverride` |
| G-I4 | 계약 테스트가 `.content` 속성 읽기도 금지. 잔여 8곳(run_agent 2·sub_agent_context 1·supervisor_nodes 1·workflow_compiler 4) 을 `message_text()` 로 치환 | 계약 테스트 0건, agent_builder 스위트 통과 |
| G-I5 | 드롭은 첨부 가능 상태면 항상 `preventDefault`, 파일 전부를 페이지로 넘겨 분류·안내(비이미지·비전 미지원 사유) | ChatInput 2건, ChatPage `비이미지 파일을 드롭하면 안내한다` |
| G-I6 | `uploadErrorMessage()` 가 `ApiError` code/status(400·413)별 문구 | ChatPage `업로드가 413 으로 실패하면 크기 안내` |
| G-M7 | 업로드 거절 시 `_logger.warning(..., exception=e)` (바이트 없음) | — |
| G-M12 | ws_router docstring 갱신 | — |
| G-M1/M3/M4/M5/M13, 추가 구현 3건 | 설계 v0.2 로 정정 (§3.1 포트, §3.2 치수, §4.1 my-agents 필드, §4.3 precheck 위치·override, §6.3 서브 모델·승인 스냅샷, §8.2 #7 마커 형식) | — |

남은 Minor: G-M6(MIME 헤더 검사), G-M8(stream 방어 검사), G-M9(동기 파일 읽기), G-M10(항목별 try/catch), G-M11(placeholder 문구). 동작·보안에 영향이 작아 후속으로 둔다.

회귀: 백엔드 전체 53 실패(상시 실패 목록과 동일) · 프론트 전체 9 실패(상시 실패 목록과 동일). 변경 파일 ruff·eslint 신규 오류 0.

### 11.1 재산정 Match Rate (정적)

| 축 | 1차 | Act-1 후 | 근거 |
|----|:---:|:-------:|------|
| Structural | 95 | 100 | 미확인이던 MessageBubble·매핑 확인, 테스트 파일명 차이는 설계 갱신 |
| Functional | 84 | 97 | UI 체크리스트 10/10, 백엔드 로직은 Minor 5건만 잔존 |
| Contract | 85 | 100 | 업로드 오류 코드 매핑, D-09 경로 확인 |

```
Overall = 100×0.2 + 97×0.4 + 100×0.4 = 20 + 38.8 + 40 = 98.8
```

**Act-1 후 Match Rate: 98%** (정적. 수동 E2E §10 L3 는 서버 기동 후 별도 수행)

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | 초기 정적 분석 (Match 87%) | gap-detector / 메인 세션 보충 |
| 0.2 | 2026-10-30 | Act-1: Critical 1·Important 6 수정, 재산정 98% | 메인 세션 |
