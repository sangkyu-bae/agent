# chat-image-attachment Completion Report

> **Status**: Complete (코드 미커밋, 수동 E2E 미실행, 정적 Match 98%)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 기준 커밋 3578c1d + 워킹트리 (branch: feature/agent-run-turn-index-fix)
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-11-02
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 87% → Act-1 → 98%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | chat-image-attachment. 에이전트 채팅에 이미지(png·jpg·webp) 최대 5장을 첨부하면 에이전트 모델이 이미지를 직접 본다 |
| Start Date | 2026-10-30 (Plan·Design) |
| End Date | 2026-11-02 (보고서 작성) |
| Duration | 작업 기록상 Plan·Design·Do·Check·Act-1이 모두 2026-10-30에 기록되었다. 보고서는 2026-11-02에 작성했다 |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────────────┐
│  Static Match Rate: 98% (정적 공식, 런타임 미포함)           │
├──────────────────────────────────────────────────────────┤
│  FR 충족:            17 / 18  (FR-18 부분)                 │
│  Success Criteria:   충족 4, 부분 5, 미실행 1, 미측정 1 / 11 │
│  Check 발견 결함:    Critical 1, Important 6              │
│  Act-1 후 미해결:    Critical 0, Important 0              │
│  Minor 13건:         수정·정정 8, 의도 부합 1, 미해결 5      │
└──────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 채팅 첨부는 엑셀(.xlsx/.xls)만 허용했다. 화면 캡처와 표 사진을 보고 묻는 요청을 받을 수 없었고, 비전 호출 어댑터는 문서 추출 미리보기 전용이었다. |
| **Solution** | 첨부 타입에 `IMAGE`를 추가했다. 이번 턴 사용자 메시지를 `[text, image×N]` 다중 콘텐츠로 조립해 에이전트 LLM에 전달한다. 업로드·file_id·WS 참조·턴 종료 cleanup은 엑셀 계약을 그대로 쓴다. 상태 메시지의 문자열 가정은 `message_text()` 헬퍼로 치환하고 AST 계약 테스트로 고정했다. |
| **Function/UX Effect** | 입력창에서 파일 선택·붙여넣기·드래그로 최대 5장(장당 10MiB)을 올리고 썸네일로 확인한다. 비전 미지원 에이전트는 이미지 버튼이 비활성화되고, 서버는 `VISION_NOT_SUPPORTED`로 실행 전에 거부한다. 대화 기록에는 마커 텍스트만 남는다. 정적 Match 98%이며, 실서버 E2E와 응답 품질 확인은 실행하지 않았다. |
| **Core Value** | 사용자가 보고 있는 이미지를 에이전트에 그대로 보여줄 수 있다. DB 스키마 변경과 새 엔드포인트가 없고, 일반 채팅·백그라운드·웹훅 경로는 변경하지 않았다. |

---

## 1.4 Success Criteria Final Status

> Plan §4.1 Definition of Done 8건 + §4.2 Quality Criteria 3건. 충족 4, 부분 5, 미실행 1, 미측정 1, 전체 11건.

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-18 구현 및 테스트 통과 (TDD) | 부분 | FR 17/18 충족. FR-18의 공용 MSW 핸들러(`__tests__/mocks/handlers.ts`)는 변경하지 않았다. 서비스 테스트가 `server.use`로 직접 등록한다 |
| SC-2 | 비전 지원 에이전트 2종(OpenAI·Anthropic) 이미지 2장+질문 수동 E2E | 미실행 | 정적 확인: 블록 포맷 `image_block_builder.py:26-43`. 실서버 실행 없음 |
| SC-3 | 비전 미지원 에이전트: 프론트 버튼 비활성, 서버 `VISION_NOT_SUPPORTED` 거부 | 부분 | 정적 확인: `ChatInput.tsx:229`, `run_agent_use_case.py:718-724`, `ws_router.py:270-275`. E2E 미실행 |
| SC-4 | 비전 미지원 워커 입력에 이미지 블록 없음(마커만) | 충족 | `workflow_compiler.py:2667-2674`, `test_sub_agent_image_forward.py` |
| SC-5 | 턴 종료 후 업로드 디렉터리 비어 있음, DB `content`에 마커만 존재 | 부분 | cleanup `ws_router.py:318-321`, 마커 저장 `run_agent_use_case.py:160-169`, 승인 스냅샷 축약(Act-1). 디렉터리·DB 실측은 E2E 미실행 |
| SC-6 | 엑셀 첨부 수동 E2E 1회 + pytest/Vitest 전량 회귀 | 부분 | 회귀 결과는 기준선과 동일(§5.2). 엑셀 수동 E2E 미실행 |
| SC-7 | `verify-architecture`·`verify-logging`·`verify-tdd` 통과 | 충족 | 변경 범위 위반 0 |
| SC-8 | `.env.example`·SOT 변경 필요 항목 보고 | 충족 | `.env.example` 반영. SOT·wiki는 수정하지 않고 §4.3에 보고 |
| SC-9 | 신규 모듈 테스트 커버리지 80% 이상 | 미측정 | 커버리지 측정 기록 없음 |
| SC-10 | ruff·eslint 신규 오류 0, 프론트 tsc 통과 | 부분 | ruff·eslint 신규 오류 0. tsc는 기존 오류가 남아 있어 전체 통과는 아니다. 신규 오류는 추가되지 않았다(분석 문서 기준 210→209) |
| SC-11 | 문자열 content 가정 지점 치환 누락 0 (계약 테스트로 고정) | 충족 | Act-1 후 계약 테스트가 `getattr`·`.get("content")`·`.content` 속성 읽기를 모두 금지한다. 잔여 0 |

**Success Rate**: 4/11 met (36%). 부분 5건과 미실행 1건은 수동 E2E 실행 후 다시 판정해야 한다.

## 1.5 Key Decisions & Outcomes

> PRD는 없다. 결정 출처는 Plan §1.4(사용자 결정, 2026-10-30), Design §12(D-01~D-10), Design v0.2 정정(Act-1)이다.

### 1.5.1 Plan 사용자 결정 (2026-10-30)

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 적용 경로는 에이전트 WebSocket 경로만 | 예 | 일반 채팅·백그라운드·웹훅·스케줄 경로 미변경 |
| [Plan] | 이미지는 에이전트에 연결된 모델이 직접 본다(관리자 멀티모달 비전 모델 미사용) | 예 | 실효 모델(`llm_model_id_override` 포함)의 `supports_vision`으로 판정. override 누락은 Act-1에서 수정(G-I3) |
| [Plan] | 대화 지속은 해당 턴만 | 예 | 기록에는 마커만 저장, 다음 턴에는 이미지 미전달. 다음 턴 동작은 E2E 미실행(L3 #7) |
| [Plan] | 입력 UX: 파일 선택·붙여넣기·드래그, 여러 장 | 예 | 세 경로가 같은 업로드 핸들러를 탄다. 실브라우저 확인은 미실행 |
| [Plan] | 에이전트 모델이 비전 미지원이면 전송 전 차단 | 예 | 프론트 비활성 + 서버 precheck 거부 |
| [Plan] | 워커 모델이 비전 미지원이면 그 워커 입력에서만 텍스트 마커로 치환 | 예 | `_wrap_sub_agent`에서 서브 모델 비전 여부로 분기. 단위 테스트 통과 |
| [Plan] | 제한값: png/jpg/webp, 턴당 5장, 장당 10MiB, 긴 변 1568px, 엑셀과 동시 허용 | 예 | 설정 5종은 `config.py:210-214`에 있다. 엑셀과 이미지 동시 첨부를 허용한다 |

### 1.5.2 Design D-01 ~ D-10

| ID | Decision | Followed? | Outcome |
|----|----------|:---------:|---------|
| D-01 | 이미지 블록은 상태 HumanMessage의 list content로 싣는다 | 예 | supervisor·워커·final_answer가 추가 배선 없이 이미지를 본다 |
| D-02 | `message_text()` 단일 헬퍼 + AST 계약 테스트 | 예 (편차 해소) | 초기 계약 테스트는 `getattr`·`.get`만 잡아 `.content` 직접 접근 지점이 남았다. Act-1에서 계약 범위를 넓히고 잔여 지점을 치환했다 |
| D-03 | 서브에이전트만 모델 비전 여부로 분기 | 예 | 모델 조회 결과가 없으면 부모 모델 기준으로 판정한다(v0.2 정정) |
| D-04 | 검색·요약·QG·근거 판정에는 텍스트만 전달 | 예 | `message_text()`로 텍스트만 사용 |
| D-05 | 비전 사전 검사는 `RunAgentUseCase.precheck_attachments`, 호출은 `ws_router` | 예 | 실행 시작 전 거부. override 반영은 Act-1 |
| D-06 | 모델 해석을 메시지 조립보다 앞으로 이동 | 예 (부분) | 조립 전에 모델을 해석한다. 저장은 마커만 쓰므로 기존 위치를 유지했다 |
| D-07 | 리사이즈는 업로드 시 서버에서 수행, 결과가 더 크면 원본 유지 | 예 | `image_normalizer.py:27-82` |
| D-08 | `ImageBlockBuilder`를 새 인프라 모듈로 두고 기존 비전 어댑터는 무변경 | 예 | 포맷 동치 테스트(`TestParityWithVisionAdapters`)로 기존 어댑터와 같은 블록을 만드는지 고정 |
| D-09 | 프론트 비전 여부는 LLM 모델 목록과 에이전트 `llm_model_id`로 계산 | 예 | `MyAgentSummary.llm_model_id` 추가(설계 v0.2 반영). 서버 precheck가 권위 있는 판정 |
| D-10 | 칩 제거 시 서버 삭제 API는 두지 않는다 | 예 | TTL 회수에 맡긴다 |

### 1.5.3 Design v0.2 정정 및 Act-1 편차

| Source | Correction | Followed? | Outcome |
|--------|-----------|:---------:|---------|
| [Design v0.2] | `ImageBlockBuilderPort`에 `build_from_path` 추가(파일 I/O를 infrastructure로 이동) | 예 | `interfaces.py`, `image_block_builder.py` 반영 |
| [Design v0.2] | resolver 이미지 dict에 width·height 추가 | 예 | `resolver.py:45-52` |
| [Design v0.2] | `MyAgentSummary.llm_model_id` 응답 필드 추가 | 예 | `schemas.py:389`, `list_my_agents_use_case.py:131` |
| [Design v0.2] | precheck 위치·override 반영, 이미지 없으면 precheck 호출 생략 | 예 | `ws_router.py:138-140`, `run_agent_use_case.py:686` |
| [Design v0.2] | 서브 모델 조회 결과 None이면 부모 모델 사용, 승인 스냅샷은 축약 후 직렬화 | 예 | 승인 스냅샷 축약은 Act-1 G-C1 수정과 연결 |
| [Design v0.2] | 마커 형식을 `[image:<mime>]`로 확정(치수 미포함) | 예 | 블록에 치수가 없어 mime만 표기 |

**설계 본문 잔여 드리프트**: §8.2 #17의 기대 결과 "조회 실패 → 마커"는 v0.2 §6.3의 "None이면 부모 모델"과 어긋난다. §11.1의 테스트 파일명(`test_build_messages_image.py`)은 실제로는 `test_run_agent_image_attachment.py`다. 두 항목은 정정 목록(분석 §11)에 없어 미정정 상태다.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [chat-image-attachment.plan.md](../01-plan/features/chat-image-attachment.plan.md) | Draft v0.1.0 (상태·체크박스 미갱신) |
| Design | [chat-image-attachment.design.md](../02-design/features/chat-image-attachment.design.md) | v0.2 (§8.2 #17 잔여 드리프트) |
| Check | [chat-image-attachment.analysis.md](../03-analysis/chat-image-attachment.analysis.md) | v0.2 (Match 87% → 98%) |
| Act | 현재 문서 | Complete |
| 선행 기능 | `idt/docs/archive/2026-08/multimodal-extractor/`, `idt/docs/archive/2026-06/ws-agent-excel-attachment/`, `idt/docs/archive/2026-06/supervisor-attachment-routing/` | 비전 어댑터 출처, 첨부 업로드·WS 계약 출처 (Plan §1.3 기재, 경로 존재는 미확인) |

---

## PDCA Cycle Summary

### Plan
- 문서: `idt/docs/01-plan/features/chat-image-attachment.plan.md` (2026-10-30)
- 목표: 에이전트 채팅에서 이미지를 첨부해 질문하면 에이전트 연결 비전 모델이 이미지를 보고 답하게 한다.
- 범위: 백엔드 첨부 도메인·인프라·업로드·WS 검증·메시지 조립·워커 치환·supervisor 문구, 프론트 입력 UX·비활성·오류 매핑·말풍선 썸네일. FR 18건, NFR 6건.
- 추정 기간: 명시하지 않음. Design §11.3의 세션 계획은 모듈 5개, 합계 145~195턴이다.

### Design
- 문서: `idt/docs/02-design/features/chat-image-attachment.design.md` (v0.1 2026-10-30, v0.2 2026-10-30)
- 선택: Option C (실용 절충). 이미지 블록을 상태 HumanMessage에 싣고, 텍스트가 필요한 지점은 헬퍼로 처리한다. 대안 B(경계 주입)는 호출 지점 4곳 이상의 배선 누락 위험 때문에 제외했다.
- 핵심 결정: §1.5 참조.

### Do
- 구현 범위:
  - 도메인: `src/domain/agent_attachment/` (value_objects, policies, exceptions, interfaces)
  - 애플리케이션: `upload_use_case.py`, `resolver.py`, `agent_builder/message_content.py`(신규), `run_agent_use_case.py`, `workflow_compiler.py`, `supervisor_nodes.py`, `sub_agent_context.py`, `action_pipeline.py`, `collect_pipeline.py`, `search_pipeline.py`, `supervisor_hooks.py`, `agent_run/step_tracking.py`
  - 인프라: `agent_attachment/image_normalizer.py`(PilImageNormalizer), `image_block_builder.py`(VendorImageBlockBuilder)
  - 인터페이스·설정: `agent_attachment_router.py`, `ws_router.py`, `api/main.py`(DI), `config.py`, `.env.example`, `pyproject.toml`(`pillow>=10.0` 명시)
  - 프론트: `types/agentAttachment.ts`, `utils/imageAttachmentValidators.ts`, `services/agentAttachmentService.ts`, `components/chat/AttachmentChip.tsx`(신규), `ChatInput.tsx`, `pages/ChatPage/index.tsx`, `MessageBubble`(imagePreviews), `types/agent.ts`, `types/chat.ts`, `services/agentSubscriptionService.ts`
- 실제 기간: 2026-10-30 기록. 구현, 검사, Act-1이 같은 날 기록되어 있다.
- Do 단계 테스트 기록: 백엔드 첨부·agent_builder·agent_run·WS 스위트 1,502건 통과. 프론트 신규 7개 파일 38건 통과.

### Check
- 문서: `idt/docs/03-analysis/chat-image-attachment.analysis.md` (v0.1 → v0.2)
- 1차 (gap-detector, 정적): 87% (Structural 95, Functional 84, Contract 85). gap-detector에는 파일 쓰기 도구가 없어 메인 세션이 분석 문서를 저장했다. 프론트 테스트 본문과 `MessageBubble`, `useAgentRunStream` 오류 매핑은 gap-detector가 확인하지 못해 메인 세션이 보충했다.
- 발견: Critical 1 (G-C1), Important 6 (G-I1~G-I6), Minor 13 (G-M1~G-M13).

### Act
- Act-1 (2026-10-30): Critical 1건과 Important 6건을 모두 수정하고 설계를 v0.2로 정정했다. 재채점 98%. 이터레이션 1회.
- Report (2026-11-02): 본 문서.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | `AttachmentType.IMAGE`, 허용 확장자 .png/.jpg/.jpeg/.webp, 확장자·매직 넘버 불일치 시 거부 | 충족 | `policies.py:32`, `:63-86`. 기존 테스트의 `image.png` 케이스는 `image.gif`로 조정 |
| FR-02 | 기존 `POST /api/v1/agent/attachments` 재사용, 서버가 타입 판별, 응답에 width·height 포함 | 충족 | `agent_attachment_router.py:34-35, 80-81`. 엑셀은 치수 null |
| FR-03 | 긴 변 1568px 초과 시 비율 유지 축소, EXIF 회전, 알파 보존, jpg 품질 설정, 결과가 크면 원본 유지 | 충족 | `image_normalizer.py:27-82`. 리사이즈는 `asyncio.to_thread`로 실행(G-I1 수정) |
| FR-04 | WS subscribe에 이미지 다건 허용, 장수 초과 시 `ATTACHMENT_LIMIT_EXCEEDED` | 충족 | `run_agent_use_case.py:705-707`, `ws_router.py:264-269` |
| FR-05 | 실효 모델 `supports_vision=false`면 `VISION_NOT_SUPPORTED`로 거부, 실행 미시작 | 충족 | `run_agent_use_case.py:711-724`. override 반영은 Act-1(G-I3) |
| FR-06 | 이번 턴 user 메시지를 `[text, image×N]`로 조립. 벤더별 블록 생성 | 충족 | `VendorImageBlockBuilder`. D-08에 따라 기존 어댑터 대신 경량 빌더를 새로 두었다. 포맷 동치 테스트로 고정 |
| FR-07 | 워커 모델이 비전 미지원이면 이미지 블록을 텍스트 마커로 치환 | 충족 | `workflow_compiler.py:2656-2692` |
| FR-08 | `message_text()` 헬퍼 도입, agent_builder 문자열 가정 지점 치환 | 충족 | Act-1에서 잔여 8곳 치환(run_agent 2, sub_agent_context 1, supervisor_nodes 1, workflow_compiler 4) |
| FR-09 | DB에는 질문 + `[이미지 첨부: …]` 마커만 저장. 바이트·base64·경로를 DB·요약·벡터 DB에 저장하지 않음 | 충족 | 마커 저장 `run_agent_use_case.py:160-169`. 승인 스냅샷 축약(G-C1, Act-1). 정적·단위 검증이며 E2E 미실행 |
| FR-10 | supervisor 첨부 인지 블록에 이미지 문구 추가, 강제 라우팅에는 포함하지 않음 | 충족 | `supervisor_nodes.py:30-51`, `supervisor_hooks.py:59` |
| FR-11 | 턴 종료(정상·오류·끊김) 시 cleanup, TTL 백업 정리 동일 적용 | 충족 | `ws_router.py:318-321`(거절 경로도 finally 수행) |
| FR-12 | 설정 5종(장수 5, 긴 변 1568, JPEG 품질 90, MAX_PIXELS, detail), `.env.example` 반영 | 충족 | `config.py:210-214`, `.env.example:59-63`. Plan은 3종이었고 설계에서 2종이 추가되었다 |
| FR-13 | 이미지 버튼(accept png/jpeg/webp), textarea 붙여넣기, 입력 영역 드래그 앤 드롭. 같은 업로드 핸들러 사용 | 충족 | `ChatInput.tsx:75-81`, `:83-95`. 실브라우저 확인은 미실행 |
| FR-14 | 썸네일 칩 표시, 개별 제거, 장수·크기·형식 초과 시 업로드 전 안내, 엑셀과 공존 | 충족 | `AttachmentChip.tsx`, `imageAttachmentValidators.ts:43-53`, `ChatPage/index.tsx:346-348`(인라인 안내). 항목별 실패 격리는 미구현(G-M10) |
| FR-15 | 실효 모델 `supports_vision=false`면 버튼 비활성, 붙여넣기·드롭 무시, 안내 문구 | 충족 | `ChatInput.tsx:194, 229-235`, `ChatPage/index.tsx:140-144`(`selectedAgent.llmModelId`) |
| FR-16 | subscribe `attachments`에 `{type:"image", file_id}` 배열 전송, 서버 거절 코드 메시지 표시 | 충족 | `ChatPage/index.tsx:304-313`. 업로드 400·413은 코드별 문구로 매핑(G-I6) |
| FR-17 | 전송된 말풍선에 썸네일 표시(세션 메모리), 히스토리 재조회 시 마커 텍스트만 표시 | 충족 | `MessageBubble` imagePreviews, `ChatPage/index.tsx:405` |
| FR-18 | API 계약 동기화: `'image'` 타입, 응답 필드, `uploadImage`, MSW 핸들러 갱신 | 부분 | 타입·서비스·`MyAgentSummary.llm_model_id` 반영. 공용 MSW 핸들러는 변경하지 않음 |

**FR 합계**: 17 충족, 1 부분(FR-18).

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Performance | 5장(각 10MiB 이하) 업로드+리사이즈 2초 이내(로컬) | 실측 없음. 리사이즈는 스레드풀에서 실행해 이벤트 루프를 막지 않는다 | 미측정 |
| Security | 확장자·MIME·매직 넘버 삼중 검증, 소유자 검증, 디코딩 폭탄 방지 | 기존 `owner_user_id` 검증 재사용. `Image.MAX_IMAGE_PIXELS` 설정 | 충족 (정적) |
| Privacy | 바이트를 DB·요약·벡터 DB·로그에 남기지 않음 | 로그는 file_id·MIME·크기만. 승인 스냅샷 축약 포함. 단위 테스트 통과 | 충족 (정적·단위) |
| Compatibility | 엑셀 E2E, 일반 채팅, 백그라운드, 웹훅 회귀 0 | 전체 pytest·Vitest가 기준선과 같다(§5.2). 엑셀 수동 E2E 미실행 | 부분 |
| Accessibility | 첨부 버튼·칩 제거 버튼 aria-label, 드롭존 대체 경로 | `AttachmentChip.tsx:30` aria-label 확인 | 충족 (정적) |
| Architecture | 레이어 규칙 준수, 함수 40줄 이하 | verify-architecture 변경 범위 위반 0 | 충족 |
| DDL | 스키마 변경 없음 | 해당 없음(Design §3.1) | 충족 |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 | `idt/src/domain/agent_attachment/` | 수정 완료 |
| 애플리케이션 (업로드·resolver) | `idt/src/application/agent_attachment/` | 수정 완료 |
| 애플리케이션 (메시지·실행) | `idt/src/application/agent_builder/message_content.py`(신규), `run_agent_use_case.py`, `workflow_compiler.py`, `supervisor_nodes.py`, `sub_agent_context.py`, `action_pipeline.py`, `collect_pipeline.py`, `search_pipeline.py`, `supervisor_hooks.py`, `idt/src/application/agent_run/step_tracking.py` | 수정 완료 |
| 인프라 | `idt/src/infrastructure/agent_attachment/image_normalizer.py`, `image_block_builder.py` | 신규 완료 |
| 인터페이스·설정 | `agent_attachment_router.py`, `ws_router.py`, `api/main.py`, `config.py`, `.env.example`, `pyproject.toml`, my-agents 응답 스키마 | 수정 완료 |
| 프론트 | `idt_front/src/types/agentAttachment.ts`, `utils/imageAttachmentValidators.ts`(신규), `services/agentAttachmentService.ts`, `components/chat/AttachmentChip.tsx`(신규), `ChatInput.tsx`, `pages/ChatPage/index.tsx`, `MessageBubble`, `types/agent.ts`, `types/chat.ts`, `services/agentSubscriptionService.ts` | 신규·수정 완료 |
| 백엔드 테스트 | `idt/tests/` 아래 domain·application·infrastructure·api 영역(정책, 정규화, 블록 빌더, 메시지 헬퍼, 계약, 서브 치환, 승인 스냅샷, WS 거절) | 완료 |
| 프론트 테스트 | `idt_front/src/` 아래 신규 파일 7개와 기존 파일 보강 | 완료 |
| 문서 | Plan v0.1, Design v0.2, Analysis v0.2, 본 Report | 완료 |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| 수동 E2E L1 (API 9건, 분석 §10) | 백엔드 서버와 비전 모델 API 키가 필요하다 | High |
| 수동 E2E L2 (UI 10건, 분석 §10) | 동일 | High |
| 수동 E2E L3 (시나리오 8건: 설계 §8.4의 7건 + 승인 게이트 턴 1건 추가) | 동일. OpenAI·Anthropic 비전 에이전트, 비전 미지원 에이전트, 서브에이전트 위임, 엑셀 동시 첨부 포함 | High |
| 커버리지 80% 측정 (SC-9) | 측정 기록 없음 | Medium |
| 코드 커밋·PR | 사용자 지시 없음. 같은 워킹트리에 image-generation-tool의 미커밋 변경이 있고, `run_agent_use_case.py`·`workflow_compiler.py`·`supervisor_nodes.py`를 두 기능이 함께 수정했다(두 보고서 기준). 커밋 시 파일별 분리가 필요하다 | High |
| 설계 본문 정정 (§8.2 #17, §11.1 테스트 파일명) | Act-1 정정 목록에서 빠졌다 | Low |
| Plan 상태와 체크박스 갱신 | Draft 상태, 체크박스 미체크 | Low |

### 4.2 Minor Gaps (분석 §8, Act-1 이후 상태)

| ID | 내용 | Act-1 후 상태 |
|----|------|---------------|
| G-M1 | `ImageBlockBuilderPort`에 `build_from_path` 추가 | 설계 v0.2로 정정 종결 |
| G-M2 | `uploadImage`와 `uploadExcel`이 같은 함수 | 설계 §5.3 "동일 엔드포인트"와 부합. 조치 없음 |
| G-M3 | 이미지 없으면 precheck 생략, 장수 검사는 precheck 안에 있음 | 설계 v0.2로 정정 종결(동작 동등) |
| G-M4 | 서브 모델 조회 None이면 부모 모델 사용 | 설계 v0.2로 정정 종결. 조회 예외 전파는 현행 유지 |
| G-M5 | `redact_image_blocks` 마커 형식이 설계와 다름 | 마커 형식 `[image:<mime>]`을 설계 v0.2에 반영. 승인 경로에서 사용 |
| G-M6 | 업로드 라우터가 `UploadFile.content_type`(MIME 헤더)을 검사하지 않음 | **미해결** (Low) |
| G-M7 | 리사이즈 실패 시 로깅 없음 | Act-1에서 `logger.warning` 추가 |
| G-M8 | 빌더 미주입 시 이미지를 조용히 버림. stream에 방어 검사 없음 | **미해결** (Low) |
| G-M9 | `build_from_path`가 async 경로에서 동기 파일 읽기 | **미해결** (Low, 장당 수백 KB) |
| G-M10 | 여러 장 순차 업로드 중 하나가 실패하면 나머지가 중단됨 | **미해결** (Low) |
| G-M11 | placeholder에 붙여넣기·드래그 안내 없음 | **미해결** (Low) |
| G-M12 | ws_router docstring의 wire protocol 표기가 엑셀만 있음 | Act-1에서 docstring 갱신 |
| G-M13 | `_compose_user_content`가 `_attach_turn_images`로 구현됨 | 설계 v0.2로 정정 종결(동등 구현) |

미해결 5건(G-M6, G-M8, G-M9, G-M10, G-M11)은 분석 §11에서 동작·보안 영향이 작다고 판정되었다.

### 4.3 SOT·wiki 어긋남 (보고만, 수정하지 않음)

| 문서 | 위치 | 어긋남 |
|------|------|--------|
| `docs/SOURCE-OF-TRUTH.md` | API·설정 항목 | WS 거절 코드 `VISION_NOT_SUPPORTED`·`ATTACHMENT_LIMIT_EXCEEDED`, 이미지 설정 5종, my-agents `llm_model_id` 필드가 없다 |
| `docs/wiki/backend/api/router-map.md` | 68행 | "엑셀 첨부 업로드" 문구. 이미지 타입과 응답 필드 설명이 없다 |
| `docs/wiki/frontend/screens/chat-screens.md` | 33행 | 이미지 첨부 UI, 썸네일, 비활성 동작 설명이 없다 |

위키 갱신은 사용자가 `/wiki update`를 명시 호출할 때만 한다.

---

## 5. Quality Metrics

### 5.1 Match Rate 변화

| Metric | Check 1차 (gap-detector) | Act-1 후 | Target |
|--------|:-----:|:-----:|:-----:|
| Structural | 95 | 100 | — |
| Functional | 84 | 97 | — |
| API Contract | 85 | 100 | — |
| **Overall (정적 공식)** | **87** (86.6) | **98** (98.8) | 90 |
| Critical 결함 | 1 | 0 | 0 |
| Important 결함 | 6 | 0 | 0 |
| Minor 결함 | 13 | 5 미해결 | — |

산식: Overall = Structural×0.2 + Functional×0.4 + Contract×0.4. Act-1 후 값은 100×0.2 + 97×0.4 + 100×0.4 = 98.8이다. 분석 문서는 이를 98%로 표기했고, 본 보고서도 같은 표기를 쓴다. 런타임 항목은 측정하지 않았으며, 런타임 포함 산식으로는 계산하지 않았다. 98%는 정적 기준이며 E2E 결과에 따라 달라질 수 있다.

### 5.2 Regression 기록

| 영역 | 결과 | 판정 |
|------|------|------|
| 백엔드 전체 pytest | 53 실패. master 상시 실패 목록과 동일 | 기준선 동일 |
| 백엔드 첨부·agent_builder·agent_run·WS 스위트 (Do 기록) | 1,502건 통과 | 통과 |
| 프론트 전체 Vitest | 9 실패. 상시 실패 목록과 동일 | 기준선 동일 |
| 프론트 신규 테스트 (Do 기록) | 7개 파일 38건 통과 | 통과 |
| ruff·eslint | 변경 파일 신규 오류 0 | 충족 |
| tsc | 신규 오류 없음(분석 문서 기준 210→209) | 부분 (기존 오류 존재) |
| verify-architecture / logging / tdd | 변경 범위 위반 0 | 충족 |

### 5.3 Gap Resolution (Act-1, 2026-10-30)

| Gap | 문제 | 수정 | 테스트 |
|-----|------|------|--------|
| G-C1 (Critical) | 승인 게이트 런의 `approval_request` 스냅샷에 이미지 base64가 저장되었고, 재개 때 이미지가 다시 전달되었다 | `message_content.redact_messages()` 신설, `_persist_approval_if_pending`이 `_redact_state_images()`를 거쳐 직렬화 | 스냅샷 payload에 `data:image` 없음, 원본 state 불변, 호출 경로 소스 검사 (2건) |
| G-I1 | PIL 리사이즈가 async 핸들러에서 동기 실행되어 이벤트 루프를 막음 | `asyncio.to_thread(use_case.execute, ...)` | 기존 라우터 테스트 전량 통과 |
| G-I2 | 업로드 중에도 전송 버튼이 활성화되어 미완료 이미지가 빠진 채 전송될 수 있었음 | `ChatInput.canSend`에 `!attachmentUploading` 추가 | "업로드 중에는 전송 버튼이 비활성이다" |
| G-I3 | precheck가 `agent.llm_model_id`로 판정해 override 실행 모델과 어긋날 수 있었음 | `precheck_attachments(llm_model_id_override=...)` | `TestPrecheckOverride` |
| G-I4 | 계약 테스트가 `getattr`·`.get`만 금지해 `.content` 직접 접근이 남아 있었음 | 계약 테스트가 속성 읽기도 금지. 잔여 지점 치환 | 계약 테스트 0건, agent_builder 스위트 통과 |
| G-I5 | 비이미지 파일 드롭이 조용히 버려졌고, 비전 미지원 상태에서 `preventDefault`가 없어 브라우저가 파일을 열었음 | 드롭은 첨부 가능 상태면 항상 `preventDefault`, 파일 전부를 페이지로 넘겨 사유별 안내 | ChatInput 2건, ChatPage "비이미지 파일을 드롭하면 안내한다" |
| G-I6 | 업로드 실패 시 코드와 무관하게 일반 문구 하나만 표시 | `uploadErrorMessage()`가 400·413을 코드별 문구로 매핑 | ChatPage "업로드가 413으로 실패하면 크기 안내" |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **문자열 가정을 헬퍼 하나로 모았다.** Plan의 최대 위험(상태 메시지 content가 list가 되면 agent_builder의 문자열 연산이 조용히 깨짐)을 `message_text()`와 AST 계약 테스트로 막았다. 이미지가 없는 턴은 content가 str로 유지된다.
- **기존 첨부 계약을 그대로 재사용했다.** 새 엔드포인트, 새 WS 메시지 타입, DB 마이그레이션 없이 업로드·file_id·cleanup·TTL을 이어 썼다.
- **Option C로 호출 지점 배선을 줄였다.** 이미지 블록을 상태 HumanMessage 하나에 싣자 supervisor·워커·final_answer가 추가 배선 없이 이미지를 봤다.
- **Check에서 Plan에 없던 경로를 찾았다.** 승인 게이트 스냅샷에 base64가 저장되는 경로(G-C1)는 Plan §6.2 영향 목록에 없었지만 정적 분석에서 Critical로 잡혔다. Act-1에서 함께 수정했다.

### 6.2 What Needs Improvement (Problem)

- **설계 체크리스트를 구현 완료 시점에 대조하지 않았다.** 설계에 명시된 항목이 구현에서 빠졌다. 업로드 `asyncio.to_thread`(설계 §7, G-I1), 업로드 중 전송 비활성(설계 §5.4 #7, G-I2), 실효 모델 판정(설계 §4.2, G-I3)이 그 예다. 모두 Check에서 발견되었다.
- **계약 테스트의 탐지 범위가 설계 의도보다 좁았다.** 초기 테스트는 `getattr`과 `.get("content")`만 금지했다. gap-detector는 `.content` 직접 접근 5곳을 찾았고, Act-1 재탐색에서 8곳(run_agent_use_case 2, sub_agent_context 1 포함)이 확인되었다. 탐지 패턴을 정할 때 속성 접근 형태를 함께 정해야 했다.
- **gap-detector 한계로 메인 세션 보충이 필요했다.** gap-detector는 파일 쓰기 도구가 없어 보고서를 메인 세션이 저장했고, 프론트 테스트 본문과 `MessageBubble`, `useAgentRunStream` 오류 매핑은 확인하지 못해 메인 세션이 보충했다. 1차 Functional 84%의 상당 부분이 이 미확인 항목에서 나왔다.
- **설계 정정 범위가 넓었다.** Act-1에서 v0.2로 정정한 항목 중 일부(§8.2 #17, §11.1 파일명)는 정정 목록에 빠졌다.

### 6.3 What to Try Next (Try)

- 설계 문서의 "구현 체크리스트"(§5.4, §7, §4.2)를 구현 완료 시점에 항목별로 대조하고, 대조 결과를 Analysis 전에 기록한다.
- 계약 테스트를 만들 때 탐지 대상 형태를 목록으로 먼저 적는다(`getattr`, `.get`, 속성 접근, 서브스크립트).
- 승인·재개·스냅샷처럼 저장 직렬화가 일어나는 경로를 Plan 영향 목록에 기본으로 넣는다.
- 설계 정정 시 용어를 grep해서 본문을 한 번에 고친다(예: `#17` 기대값, 파일명).
- Bash heredoc에 한글과 따옴표가 섞이면 실패하므로, 한글 텍스트 편집은 Edit 도구로 한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 영향 목록에 승인·재개 스냅샷 경로가 없었다 | 직렬화·저장되는 모든 경로를 영향 목록에 명시하는 항목을 추가한다 |
| Design | 체크리스트와 본문 기대값이 구현 후 어긋났다 | 구현 완료 시 체크리스트 대조 단계를 추가한다 |
| Do | 계약 테스트 범위가 설계 의도보다 좁았다 | 계약 테스트 설계 시 탐지 패턴 목록을 함께 적는다 |
| Check | 프론트 항목과 보고 저장을 메인 세션이 보충했다 | gap-detector에 파일 쓰기 권한을 주거나, 메인 세션이 저장을 맡는다는 절차를 고정한다 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| Testing | 비전 E2E용 로컬 서버와 vision 모델 키(OpenAI·Anthropic 각 1종)를 미리 준비 | 수동 E2E 27건 실행 가능 |
| Git | 두 기능이 같은 워킹트리에 미커밋 상태이므로 브랜치 또는 커밋 단위를 분리 | 커밋 시 파일 혼입 방지 |
| Performance | 리사이즈와 블록 생성 시간을 측정하는 스크립트 추가 | NFR Performance(2초) 판정 가능 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 수동 E2E L1 (API 9건, 분석 §10): 업로드 png 치수(1568×523 기대), 엑셀 치수 null, gif 400, 위장 파일 400, 11MiB 413, 미인증 401, WS 장수 초과, WS 비전 미지원 거절, WS 정상 턴(종료 후 파일 0개)
- [ ] 수동 E2E L2 (UI 10건, 분석 §10): 버튼 선택, 붙여넣기, 텍스트 붙여넣기 무업로드, 드롭(이미지+txt), 비전 미지원 비활성, 칩 제거, 6번째 안내, 이미지 2+엑셀 1 전송, 서버 거절 복원, 업로드 중 전송 비활성
- [ ] 수동 E2E L3 (시나리오 8건, 설계 §8.4 + 승인 게이트): OpenAI·Anthropic 답변이 이미지 수치를 인용하는지, 비전 미지원 거부, 엑셀+이미지 동시, 서브에이전트 위임 실패 없음, 턴 종료 후 DB·디렉터리·`ai_run_step.input_summary` 확인, 다음 턴에 이미지 미전달, 승인 스냅샷에 `data:image` 없음
- [ ] 커밋 및 PR: 같은 워킹트리의 image-generation-tool 변경과 파일을 분리한다. 브랜치 분리 여부를 먼저 결정한다
- [ ] `/pdca archive chat-image-attachment` (커밋 후)
- [ ] `/wiki update` 호출 시 §4.3의 어긋남 3건 반영
- [ ] 설계 §8.2 #17 기대값 정정, Plan 상태·체크박스 갱신

### 8.2 Follow-up (Minor, 미해결 5건)

| Item | Gap | Priority |
|------|-----|----------|
| 빌더 미주입 시 명시 오류 (stream 방어 검사) | G-M8 | Low |
| 업로드 실패를 항목별로 격리 | G-M10 | Low |
| `build_from_path`를 필요 시 스레드풀로 이동 | G-M9 | Low |
| 업로드 MIME 헤더 검사 추가 또는 설계에 제외 명시 | G-M6 | Low |
| placeholder에 붙여넣기·드래그 안내 추가 | G-M11 | Low |
| 신규 모듈 커버리지 80% 측정 | SC-9 | Medium |

### 8.3 Next PDCA Cycle

Plan §2.2의 제외 범위는 다음 사이클 후보로 남긴다. 아직 우선순위를 정하지 않았다.

| Item | Note |
|------|------|
| 일반 채팅(general_chat) 경로 이미지 첨부 | Plan 범위 밖 |
| 다음 턴에서 이전 이미지 참조 | 대화 기록 정책 변경이 필요하다(규칙 문서상 금지 항목) |
| 비전 미지원 에이전트의 관리자 비전 모델 텍스트 변환 폴백 | Plan 범위 밖 |

---

## 9. Changelog

### v1.0.0 (2026-11-02)

**Added:**
- 첨부 타입 `IMAGE`(png·jpg·jpeg·webp), 매직 넘버 검증, 장수 상한 정책
- `PilImageNormalizer`(리사이즈·EXIF·알파), `VendorImageBlockBuilder`(벤더별 이미지 블록)
- `agent_builder/message_content.py`: `message_text`, `image_blocks`, `redact_image_blocks`, `redact_messages`
- WS 거절 코드 `ATTACHMENT_LIMIT_EXCEEDED`, `VISION_NOT_SUPPORTED`
- 설정 5종(`AGENT_ATTACHMENT_IMAGE_*`), `pillow>=10.0` 명시 의존
- 프론트 `AttachmentChip`, `imageAttachmentValidators`, 이미지 업로드 `uploadImage`, 말풍선 썸네일
- `MyAgentSummary.llm_model_id` 응답 필드

**Changed:**
- 업로드 응답에 `width`·`height` 추가(엑셀은 null)
- WS subscribe `attachments`가 이미지 참조를 받는다
- 상태 메시지 문자열 처리 지점을 `message_text()`로 치환(agent_builder, agent_run 전체)
- 실행 시 모델 해석을 메시지 조립보다 앞으로 이동
- 프론트 `ChatInput` 첨부 props를 단일 값에서 배열로 변경

**Fixed (Act-1):**
- 승인 스냅샷에 이미지 base64가 저장되던 문제 (G-C1)
- 업로드 리사이즈가 이벤트 루프를 막던 문제 (G-I1)
- 업로드 중 전송 버튼 활성화 (G-I2)
- precheck가 override 모델을 보지 않던 문제 (G-I3)
- 계약 테스트 범위 부족 (G-I4)
- 비이미지 드롭 무안내, 비전 미지원 드롭 기본 동작 (G-I5)
- 업로드 오류 코드 미매핑 (G-I6)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-02 | Completion report (정적 Match 98%, 수동 E2E 미실행, 코드 미커밋) | 배상규 + Claude |
