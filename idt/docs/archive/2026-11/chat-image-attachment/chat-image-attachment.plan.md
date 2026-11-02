# chat-image-attachment Planning Document

> **Summary**: 에이전트 채팅에서 이미지(png/jpg/webp)를 최대 5장 첨부해 질문하면, 에이전트에 연결된 비전 LLM이 이미지를 직접 보고 답한다. 기존 엑셀 첨부 계약(업로드→file_id→WS subscribe 참조→턴 종료 후 삭제)을 그대로 확장한다.
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
| **Problem** | 채팅 첨부는 엑셀(.xlsx/.xls)만 허용한다. 화면 캡처·표 사진·차트 이미지를 보고 묻는 요청을 받을 길이 없고, 비전 호출 어댑터는 문서 추출 모듈(미리보기 전용)에만 존재한다. |
| **Solution** | 첨부 타입에 IMAGE를 추가하고, 이번 턴의 사용자 메시지를 "텍스트 + 이미지 블록" 다중 콘텐츠로 조립해 에이전트 LLM(supports_vision=true)에 직접 전달한다. 비전 미지원 에이전트는 전송 전에 차단하고, 비전 미지원 워커에는 이미지 블록을 텍스트 마커로 치환한다. |
| **Function/UX Effect** | 에이전트 모드 입력창에서 파일 선택·클립보드 붙여넣기·드래그로 이미지를 올리고 썸네일로 확인한 뒤 질문을 보낸다. 엑셀과 같은 턴에 동시 첨부할 수 있다. 응답 후 서버 파일은 삭제되고 대화 기록에는 텍스트 마커만 남는다. |
| **Core Value** | 사용자가 보고 있는 것을 그대로 에이전트에 보여줄 수 있다. 메모리 정책·그래프 구조·DB 스키마 변경 없이, 기존 첨부 인프라와 비전 어댑터를 재사용해 붙인다. |

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

### 1.1 Purpose

에이전트 채팅에서 이미지를 첨부해 질문하면 에이전트에 연결된 비전 LLM이 이미지를 직접 보고 답하게 한다.

### 1.2 Background

- `multimodal-extractor`(2026-08 아카이브)는 PDF의 그림·차트를 비전 모델로 해석하는 모듈이며, 플랜 §2.3에서 "채팅 입력 이미지 이해(첨부 멀티모달)는 별개 기능"으로 명시적으로 미뤘다. 본 기능이 그 이월분이다.
- 채팅 첨부 인프라는 `ws-agent-excel-attachment`(업로드 store·TTL·WS subscribe 참조·턴 종료 cleanup)와 `supervisor-attachment-routing`(첨부 인지 블록·강제 라우팅 훅)으로 이미 갖춰져 있다. 첨부 정책은 OCP 확장 지점(`AttachmentType` + `ALLOWED_EXT`)을 두고 있다.
- 벤더별 이미지 블록 생성(OpenAI `image_url`, Anthropic `image`, OpenAI 호환)은 `infrastructure/multimodal/vision/*`의 `build_image_block`에 이미 있다.
- `LlmModel.supports_vision`(V064)은 시드 모델 일부만 true이고 직접 등록 모델은 기본 false다.

### 1.3 Related Documents

- `idt/docs/archive/2026-08/multimodal-extractor/` (비전 어댑터·supports_vision 출처)
- `idt/docs/archive/2026-06/ws-agent-excel-attachment/` (첨부 업로드·WS 계약)
- `idt/docs/archive/2026-06/supervisor-attachment-routing/` (첨부 인지 블록·강제 라우팅)
- 위키: `docs/wiki/backend/patterns/supervisor-graph-contracts.md`, `docs/wiki/backend/db/erd-document-tooling.md`, `docs/wiki/frontend/screens/chat-screens.md`
- 규칙: `idt/docs/rules/conversation-memory.md`(대화 기록 정책 변경 금지)

### 1.4 사용자 결정 기록 (2026-10-30)

| 결정 항목 | 선택 |
|-----------|------|
| 적용 경로 | 에이전트 경로(supervisor 그래프)만 |
| 이미지 전달 방식 | 에이전트에 연결된 모델이 직접 봄 (관리자 멀티모달 설정의 비전 모델은 문서 추출 전용, 미사용) |
| 대화 지속 | 해당 턴만 (다음 턴에 이미지 미전달) |
| 입력 UX | 파일 선택 + 클립보드 붙여넣기 + 드래그 앤 드롭, 여러 장 |
| 에이전트 모델이 비전 미지원 | 전송 전 차단 (프론트 비활성 + 서버 명시 거부) |
| 워커(서브에이전트) 모델이 비전 미지원 | 그 워커 입력에서만 이미지 블록을 텍스트 마커로 치환 |
| 제한값 | png/jpg/webp, 턴당 최대 5장, 장당 10MiB, 서버 리사이즈(긴 변 1568px), 엑셀과 동시 첨부 허용 |

---

## 2. Scope

### 2.1 In Scope

- [ ] 백엔드: `AttachmentType.IMAGE` 추가, 허용 확장자(.png/.jpg/.jpeg/.webp)·MIME 스니핑·장당 크기 검증
- [ ] 백엔드: 업로드 API가 이미지를 받아 file_id 발급 (기존 엔드포인트 재사용, 타입은 서버가 판별)
- [ ] 백엔드: 서버 리사이즈(긴 변 1568px 초과 시 축소, EXIF 회전 반영, 알파 보존) 후 저장
- [ ] 백엔드: WS subscribe `attachments`에 이미지 참조 다건 허용, 턴당 이미지 장수 상한 검증
- [ ] 백엔드: 에이전트 LLM `supports_vision=false`이면 subscribe 단계에서 명시 오류 코드로 거부
- [ ] 백엔드: 이번 턴 사용자 메시지를 "텍스트 + 이미지 블록 N" 다중 콘텐츠로 조립(벤더별 블록은 기존 비전 어댑터의 `build_image_block` 재사용)
- [ ] 백엔드: 비전 미지원 모델을 쓰는 워커 입력 조립 시 이미지 블록을 텍스트 마커로 치환
- [ ] 백엔드: 상태 메시지 content가 list일 때를 위한 텍스트 추출 헬퍼 도입 및 문자열 가정 지점 치환
- [ ] 백엔드: 대화 기록(DB)에는 `"[이미지 첨부: a.png, b.png]"` 텍스트 마커만 저장, 요약 입력도 마커만
- [ ] 백엔드: supervisor 첨부 인지 블록에 이미지 타입 문구 추가(강제 라우팅 대상에서는 제외)
- [ ] 백엔드: 턴 종료 시 이미지 파일 삭제(기존 cleanup 경로), TTL 백업 정리 동일 적용
- [ ] 백엔드: config에 장수·긴 변·허용 MIME 상한 추가(.env.example 반영)
- [ ] 프론트: 에이전트 모드에서 이미지 첨부 버튼(accept 확장), 클립보드 붙여넣기, 드래그 앤 드롭
- [ ] 프론트: 다중 썸네일 미리보기·개별 제거·장수/크기 초과 안내, 엑셀과 공존
- [ ] 프론트: 선택된 에이전트 모델의 `supports_vision`이 false면 이미지 첨부 UI 비활성 + 안내 문구
- [ ] 프론트: WS subscribe attachments에 이미지 참조 배열 전송, 서버 거부 코드 메시지 표시
- [ ] 프론트: 사용자 메시지 말풍선에 첨부 이미지 썸네일 표시(해당 세션 내 클라이언트 보관, 새로고침 후에는 마커 텍스트)
- [ ] API 계약 동기화: 백엔드 스키마 변경분을 `idt_front/src/types/agentAttachment.ts`·서비스·훅에 반영
- [ ] 테스트: 백엔드 pytest(정책·리사이즈·메시지 조립·워커 치환·WS 거부·cleanup), 프론트 Vitest(입력 UX·비활성·전송 페이로드)

### 2.2 Out of Scope

- 일반 채팅(general_chat) 경로의 이미지 첨부
- 백그라운드 잡·웹훅·스케줄 실행 경로의 이미지 첨부
- 다음 턴에서 이전 이미지 참조(대화 기록에 이미지 보존)
- 비전 미지원 에이전트에 대한 관리자 비전 모델 텍스트 변환 폴백
- 관리자 멀티모달 설정(multimodal_setting)과의 연동·변경
- 이미지에서 추출한 내용의 KB 저장·색인
- gif·svg·heic·pdf 첨부, 이미지 편집(크롭·주석)
- 토큰 과금 정책 변경(기존 UsageCallback이 모델 응답 usage를 그대로 집계)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `AttachmentType.IMAGE` 추가. 허용 확장자 .png/.jpg/.jpeg/.webp. 확장자와 실제 바이트 시그니처(매직 넘버)가 불일치하면 `InvalidAttachmentError` | High | Pending |
| FR-02 | 업로드 API는 기존 `POST /api/v1/agent/attachments`를 재사용하고 서버가 타입을 판별해 `{file_id, type:"image", filename, size, width, height}`를 반환 | High | Pending |
| FR-03 | 저장 전 리사이즈: 긴 변이 설정값(기본 1568px) 초과 시 비율 유지 축소, EXIF 방향 반영, png/webp 알파 보존, jpg 품질 설정값(기본 90). 결과 바이트가 원본보다 크면 원본 유지 | High | Pending |
| FR-04 | WS subscribe `attachments`에 `type:"image"` 참조 다건 허용. 턴당 이미지 장수가 설정 상한(기본 5) 초과면 `ATTACHMENT_LIMIT_EXCEEDED`로 거부 | High | Pending |
| FR-05 | 에이전트에 연결된 LLM(`llm_model_id_override` 포함 실효 모델)의 `supports_vision=false`이면 subscribe 단계에서 `VISION_NOT_SUPPORTED`로 거부하고 실행을 시작하지 않는다 | High | Pending |
| FR-06 | 이번 턴 사용자 메시지를 `[{type:"text"}, 이미지 블록 ×N]` 다중 콘텐츠로 조립. 이미지 블록은 에이전트 모델 provider 키로 기존 비전 어댑터 레지스트리에서 `build_image_block`을 빌려 생성(OpenAI/Anthropic/OpenAI 호환·Ollama) | High | Pending |
| FR-07 | 워커 입력 조립(`workflow_compiler` 워커 메시지 빌드)에서 해당 워커 모델이 `supports_vision=false`이면 이미지 블록을 `"[이미지 첨부: name (이 모델은 이미지를 볼 수 없음)]"` 텍스트로 치환. 비전 지원 워커는 원본 블록 유지 | High | Pending |
| FR-08 | 메시지 content 텍스트 추출 헬퍼(`message_text(m) -> str`) 도입. `agent_builder` 안에서 `getattr(m, "content", "")`·`.content`를 문자열로 가정하는 지점(재주입 판정·검색결과 판정·마지막 사용자 지시 추출·QG 피드백·요약 입력)을 헬퍼로 치환 | High | Pending |
| FR-09 | 대화 기록(DB `conversation_message.content`)에는 질문 텍스트 + `"\n[이미지 첨부: a.png, b.png]"` 마커만 저장. 이미지 바이트·base64·경로는 DB·요약·벡터 DB 어디에도 저장하지 않는다 | High | Pending |
| FR-10 | supervisor 첨부 인지 블록에 이미지 타입 문구("사용자가 이미지 N장을 첨부했습니다. 질문과 함께 이미지를 직접 보고 판단하세요") 추가. `AttachmentRoutingHooks._ROUTABLE_TYPES`에는 포함하지 않는다(강제 라우팅 없음) | Medium | Pending |
| FR-11 | 턴 종료(정상·오류·연결 끊김) 시 기존 `attachment_resolver.cleanup`으로 이미지 파일 삭제. TTL 백업 정리는 기존 설정 그대로 적용 | High | Pending |
| FR-12 | 설정값: `agent_attachment_image_max_count`(5), `agent_attachment_image_max_edge_px`(1568), `agent_attachment_image_jpeg_quality`(90). 장당 크기는 기존 `agent_attachment_max_bytes`(10MiB) 재사용. `.env.example`에 추가 | Medium | Pending |
| FR-13 | 프론트: 에이전트 모드 입력창에 이미지 첨부 버튼(accept `image/png,image/jpeg,image/webp`), textarea 클립보드 `paste` 이미지 수신, 입력 영역 드래그 앤 드롭 수신. 세 경로 모두 같은 업로드 핸들러를 탄다 | High | Pending |
| FR-14 | 프론트: 첨부 대기 목록을 썸네일 칩으로 표시, 개별 제거, 장수·크기·형식 초과 시 업로드 전 안내(토스트/인라인). 엑셀 1건과 이미지 N장이 같은 턴에 공존 | High | Pending |
| FR-15 | 프론트: 선택 에이전트의 실효 모델 `supports_vision`이 false면 이미지 버튼 비활성·붙여넣기/드롭 무시·안내 문구. 모델 정보는 기존 에이전트 상세/LLM 모델 조회 응답을 사용한다 | High | Pending |
| FR-16 | 프론트: 전송 시 WS subscribe `attachments`에 `{type:"image", file_id}` 배열을 싣고, `VISION_NOT_SUPPORTED`·`ATTACHMENT_LIMIT_EXCEEDED`·기존 첨부 오류 코드를 사용자 메시지로 표시 | High | Pending |
| FR-17 | 프론트: 전송된 사용자 말풍선에 이미지 썸네일(object URL, 세션 내 메모리)을 함께 표시. 히스토리 재조회 시에는 저장된 마커 텍스트만 표시 | Medium | Pending |
| FR-18 | API 계약 동기화: `AttachmentType` 유니온에 `'image'` 추가, 업로드 응답 타입 확장, 서비스 함수(`uploadImage`) 추가, MSW 핸들러 갱신 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 5장(각 ≤10MiB) 업로드+리사이즈가 업로드 요청당 2초 이내(로컬 기준). 리사이즈는 스레드풀에서 실행해 이벤트 루프를 막지 않는다 | pytest 타이밍 + 수동 측정 |
| Security | 확장자·MIME·매직 넘버 삼중 검증, 소유자 검증(기존 `owner_user_id`), 경로 노출 금지(기존 `_render_attachment_block` 규칙), 디코딩 폭탄 방지(`Image.MAX_IMAGE_PIXELS` 설정) | pytest + 코드 리뷰 |
| Privacy | 이미지 바이트는 DB·요약·벡터 DB·로그에 남기지 않는다. 로그에는 file_id·크기·MIME만 | `verify-logging` + grep 검사 |
| Compatibility | 기존 엑셀 첨부 E2E, 일반 채팅, 백그라운드 잡, 웹훅 회귀 0. content가 str인 기존 메시지는 헬퍼가 그대로 반환 | 기존 pytest 전량 + 프론트 Vitest |
| Accessibility | 첨부 버튼·썸네일 제거 버튼에 aria-label, 드롭존 키보드 대체 경로(버튼) 유지 | 프론트 테스트 |
| Architecture | 레이어 규칙 준수(domain에 PIL·LangChain 금지, 리사이즈는 infrastructure, 조립은 application). 함수 40줄·if 중첩 2단계 | `verify-architecture` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-18 구현 및 테스트 통과(TDD: 테스트 선작성)
- [ ] 비전 지원 에이전트(OpenAI·Anthropic 각 1종)에서 이미지 2장+질문 수동 E2E: 답변이 이미지 내용을 근거로 함
- [ ] 비전 미지원 에이전트: 프론트 버튼 비활성, 서버 `VISION_NOT_SUPPORTED` 확인
- [ ] 비전 미지원 워커가 있는 에이전트: 해당 워커 입력에 이미지 블록 없음(마커만)을 단위 테스트로 확인
- [ ] 턴 종료 후 업로드 디렉터리에 이미지 파일 없음, DB `conversation_message.content`에 마커만 존재
- [ ] 기존 엑셀 첨부 수동 E2E 1회 + 기존 pytest/Vitest 전량 회귀 통과
- [ ] `verify-architecture`·`verify-logging`·`verify-tdd` 통과
- [ ] `.env.example`·`docs/SOURCE-OF-TRUTH.md` 변경 필요 항목을 보고(갱신은 사용자 지시 시)

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] lint(ruff·eslint) 오류 0, 프론트 `tsc` 통과
- [ ] 문자열 content 가정 지점 치환 누락 0 (grep 기반 계약 테스트로 고정)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 상태 메시지 content가 list가 되면서 `agent_builder`의 문자열 연산(재주입 판정·검색결과 판정·지시 추출·QG)이 예외 또는 오판 | High | High | FR-08 헬퍼 도입 + AST/grep 계약 테스트로 `.content`를 직접 문자열로 쓰는 지점을 금지. 이미지가 없는 턴은 기존처럼 str 유지(하위 호환) |
| 비전 미지원 워커에 이미지 블록이 전달되어 벤더 400 오류로 턴 실패 | High | Medium | FR-07 치환 + 단위 테스트. 워커 모델 조회 실패 시 보수적으로 치환 |
| LangChain 벤더별 이미지 블록 포맷 불일치(ChatAnthropic은 OpenAI식 `image_url`도 수용하지만 Ollama는 다름) | Medium | Medium | 기존 비전 어댑터의 `build_image_block`을 provider 키로 재사용(이미 3벤더 검증됨). 미등록 provider는 `UnsupportedVisionProviderError` → `VISION_NOT_SUPPORTED` |
| base64 이미지 5장이 state에 실려 LangGraph 체크포인트·로그·이벤트 스트림에 누출 | Medium | Medium | 리사이즈로 장당 수백 KB 수준 유지. 스트림 이벤트·로그 직렬화 지점에서 이미지 블록을 마커로 축약하는 필터 추가(Design에서 확정) |
| 디코딩 폭탄·위장 파일(확장자만 png) | High | Low | 매직 넘버 검증 + `Image.MAX_IMAGE_PIXELS` + PIL `verify()` 후 재오픈 |
| 직접 등록 모델은 `supports_vision=false` 기본이라 사용자가 "왜 안 되나" 혼란 | Medium | High | 프론트 안내 문구에 "관리자 > LLM 모델에서 비전 지원을 켜야 합니다" 명시. 관리자 화면은 이미 플래그 편집 가능(V064) |
| Pillow가 `pyproject.toml`에 직접 선언되지 않고 전이 의존으로만 설치됨 | Medium | Medium | `pillow` 명시 의존 추가(현재 12.3.0 설치 확인) |
| 토큰 비용 급증(고해상도 5장) | Medium | Medium | 서버 리사이즈 1568px + `detail` 기본값 `high` 유지하되 설정값으로 조정 가능. 기존 UsageCallback이 usage를 그대로 집계하므로 관측 가능 |
| 클립보드 붙여넣기가 텍스트 붙여넣기 UX를 깨뜨림 | Low | Medium | `paste` 이벤트에서 `clipboardData.files`에 이미지가 있을 때만 가로채고 텍스트는 기본 동작 유지 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/domain/agent_attachment/value_objects.py` `AttachmentType` | Domain VO | `IMAGE = "image"` 멤버 추가 |
| `src/domain/agent_attachment/policies.py` `AttachmentPolicy` | Domain Policy | `ALLOWED_EXT[IMAGE]` 추가, 매직 넘버 검증 규칙 추가 |
| `src/application/agent_attachment/upload_use_case.py` | UseCase | 이미지 타입 분기: 리사이즈 포트 호출 후 저장, 응답에 width/height |
| `src/infrastructure/agent_attachment/` (신규 `image_normalizer.py`) | Infra | PIL 기반 리사이즈·EXIF·알파 처리 |
| `src/api/routes/agent_attachment_router.py` `AttachmentUploadResponse` | API Schema | `width`, `height` 옵셔널 필드 추가(additive) |
| `src/api/routes/ws_schemas.py` `AttachmentRefPayload` | API Schema | 변경 없음(type 문자열 그대로). 장수 검증은 라우터/리졸버에서 |
| `src/api/routes/ws_router.py` `_resolve_ws_attachments` | Router | 이미지 장수 상한·비전 지원 사전 검증, 신규 오류 코드 2종 |
| `src/application/agent_attachment/resolver.py` | UseCase | 이미지 첨부 dict에 `mime`, `file_name`, `file_path` 포함 |
| `src/application/agent_builder/run_agent_use_case.py` `_build_messages` | UseCase | 이번 턴 user 메시지를 다중 콘텐츠로 조립, DB 저장 content는 마커 |
| `src/application/agent_builder/workflow_compiler.py` 워커 메시지 빌드 | UseCase | 워커 모델 비전 여부에 따른 이미지 블록 치환 |
| `src/application/agent_builder/supervisor_nodes.py` `_render_attachment_block` | UseCase | 이미지 타입 문구 |
| `src/application/agent_builder/` (신규 `message_text.py`) | UseCase 헬퍼 | list/str content 텍스트 추출 |
| `src/config.py` | Config | 이미지 장수·긴 변·JPEG 품질 설정 3종 |
| `pyproject.toml` | Deps | `pillow` 명시 |
| `idt_front/src/types/agentAttachment.ts` | FE Type | `AttachmentType` 유니온 확장, 업로드 응답 필드 |
| `idt_front/src/services/agentAttachmentService.ts` | FE Service | `uploadImage` 추가(동일 엔드포인트) |
| `idt_front/src/components/chat/ChatInput.tsx` | FE Component | 이미지 버튼·paste·drop·썸네일 칩 |
| `idt_front/src/pages/ChatPage/index.tsx` | FE Page | 첨부 상태를 단일 → 배열(엑셀 1 + 이미지 N), subscribe 페이로드, 오류 코드 메시지 |
| `idt_front/src/hooks/useAgentRunStream.ts` | FE Hook | attachments 배열 전달(이미 배열 타입이면 변경 없음), 신규 오류 코드 매핑 |
| `idt_front/src/__tests__/mocks/handlers.ts` | FE Mock | 업로드 응답 이미지 케이스 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `AttachmentType` | READ | `resolver.py`, `ws_router.py`, `upload_use_case.py`, `document_template_extractor`(DOCUMENT 타입) | None (멤버 추가) |
| `AttachmentPolicy.validate` | CALL | `upload_use_case.py` | Needs verification (이미지 분기 추가, 엑셀 경로 동일) |
| `AgentAttachmentStore.save/load/delete/purge_expired` | CRUD | `upload_use_case.py`, `resolver.py`, `ws_router.py` cleanup | None (바이트·확장자 무관) |
| `RunAgentRequest.attachments` (`list[dict]`) | READ | `run_agent_use_case.py:798,1386`, `supervisor_hooks.py:88`, `supervisor_nodes.py:460`, `workflow_compiler.py:2125,2414` | Needs verification (`type=="excel"` 필터는 그대로, 이미지 dict가 섞여도 무시되어야 함) |
| `_build_messages` 반환(`list[dict]` role/content) | READ | `build_initial_state` → LangGraph `messages` → supervisor/worker/QG/final_answer 노드 | **Breaking 가능** — content가 list인 메시지 등장. FR-08로 전 지점 치환 |
| `conversation_message.content` | CREATE/READ | `run_agent_use_case.py:1524,1542`(저장), `history_use_case.py`, `conversation/use_case.py:171,183`(요약 입력) | None (마커 문자열만 저장) |
| `UsageCallback` | READ | 모델 응답 usage 집계 | None |
| `AttachmentRoutingHooks._ROUTABLE_TYPES` | READ | `supervisor_hooks.py` | None (이미지 미포함) |
| `ws_router` 오류 코드 집합 | READ | `useAgentRunStream.ts` 오류 매핑 | Needs verification (신규 코드 2종 추가, 미지 코드 폴백 확인) |
| `ChatInput` props | READ | `ChatPage/index.tsx`, `ChatInput.background.test.tsx` | Needs verification (단일 첨부 props → 배열 props) |
| 백그라운드 잡·웹훅·스케줄 `RunAgentRequest` | CREATE | `background_job`, `agent_webhook`, `agent_schedule` | None (attachments 미사용, 이미지 dict 전달 경로 없음) |
| 프롬프트 가드 | READ | 그래프 생성 전 질문 텍스트 검사 | None (텍스트만 검사, 이미지는 검사 대상 아님 — Design에서 명시) |

### 6.3 Verification

- [ ] 위 소비자 전부가 이미지 dict·list content와 공존함을 테스트로 확인
- [ ] 인증·소유자 검증 경로 변경 없음(기존 `owner_user_id` 검증 재사용)
- [ ] 업로드 응답 필드 추가가 기존 프론트 타입(옵셔널)과 호환

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ (기존 Thin DDD 유지) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 이미지 전달 모델 | 에이전트 모델 직접 / 관리자 비전 모델 텍스트 변환 / 하이브리드 | 에이전트 모델 직접 | 질문 맥락과 이미지를 함께 봄. 관리자 멀티모달 설정은 문서 추출 전용으로 유지(사용자 결정) |
| 첨부 전달 채널 | 기존 업로드+file_id 참조 / WS 바이너리 프레임 / base64 인라인 | 기존 업로드+file_id | 엑셀 계약·cleanup·TTL 재사용, 프론트 변경 최소 |
| 이미지 블록 생성 | LangChain 표준 블록 직접 작성 / 기존 비전 어댑터 `build_image_block` 재사용 | 기존 어댑터 재사용 | 3벤더 검증 완료, 어댑터 1개 추가 = register 1줄 |
| 미지원 에이전트 처리 | 전송 전 차단 / 이미지 제거 후 경고 | 전송 전 차단 | 조용한 무시 방지(사용자 결정) |
| 미지원 워커 처리 | 워커별 치환 / 실행 전체 거부 | 워커별 치환 | 활용 범위 확보(사용자 결정) |
| 리사이즈 위치 | 업로드 시 서버 / 전송 직전 / 프론트 캔버스 | 업로드 시 서버 | 저장 용량·state 크기·토큰 동시 절감, 프론트 단순 |
| 대화 기록 | 마커만 / 이미지 보존 | 마커만 | 메모리 정책 변경 금지, 사용자 결정(해당 턴만) |
| 설정 관리 | 하드코딩 / config(.env) | config | CLAUDE.md 하드코딩 금지 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 Thin DDD 유지)

domain/agent_attachment/      AttachmentType.IMAGE, 확장자·매직넘버 규칙 (PIL 금지)
application/agent_attachment/ upload_use_case: 이미지 분기 → ImageNormalizerPort 호출
application/agent_builder/    message_text 헬퍼, _build_messages 다중 콘텐츠, 워커 치환
infrastructure/agent_attachment/ image_normalizer (PIL), store (변경 없음)
infrastructure/multimodal/vision/ build_image_block 재사용 (변경 없음)
interfaces(api/routes)/       upload 응답 필드, ws_router 사전 검증·오류 코드
```

---

## 8. 열린 질문 (Design 단계에서 확정)

1. 이미지 블록이 실린 state 메시지를 LangGraph 체크포인트·스트림 이벤트·로그에 어떻게 축약해 직렬화할지(마커 치환 필터 위치).
2. 워커 모델의 `supports_vision` 조회 시점(compile 시 1회 캐시 vs 호출 시) — 서브에이전트 모델 조회가 이미 `workflow_compiler.py:1330`에 있으므로 그 자리에서 함께 읽는 안이 유력.
3. 프론트에서 "실효 모델"의 `supports_vision`을 어느 응답에서 읽을지(에이전트 상세 응답에 모델 정보가 포함되는지 확인 필요).
4. OpenAI `detail` 파라미터 기본값(`high`/`auto`)을 설정값으로 둘지.
