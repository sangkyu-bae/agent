# wizard-template-request Planning Document

> **Summary**: 채팅 위저드에서 확정 도구에 문서추출기가 포함되면, 에이전트 의도에 맞춘 "양식 파일을 올려주세요" 요청 카드를 띄우고, 첨부 즉시 추출·슬롯 추천을 돌려 추천 슬롯 확인 한 번으로 양식 템플릿까지 에이전트에 매핑한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | "ㅇㅇ데이터로 ㅇㅇ문서를 만들어 주는 에이전트"를 채팅 위저드로 만들면 도구 추천까지는 자동이지만, 양식 파일은 스튜디오의 문서추출기 패널에서만 올릴 수 있다. 위저드는 양식이 필요하다는 사실을 알려주지 않으므로, 비개발자는 에이전트를 만들고도 양식 없는 추출기를 그대로 두거나 스튜디오에서 어느 패널에 무엇을 올려야 하는지 찾지 못한다. |
| **Solution** | 도구 확정 결과에 문서추출기가 있으면 위저드 문서 단계에 "양식 요청 카드"를 띄운다. 요청 문구는 에이전트 의도(목적 슬롯)를 반영해 구체화한다. 사용자가 파일을 첨부하면 기존 추출 API를 바로 호출해 추천 슬롯을 보여주고, "이대로 사용" 한 번으로 템플릿이 확정되어 생성 요청에 실린다. 건너뛰면 도구는 유지되고 스튜디오 패널에 같은 요청 문구가 남는다. |
| **Function/UX Effect** | 사용자는 "어떤 파일을 올릴지"를 묻는 카드에 파일을 드롭하고 슬롯 목록을 확인하는 두 동작만 한다. 스튜디오 진입 없이 양식 채우기 에이전트가 완성되고, 기존 참고 문서(KB) 블록은 같은 화면에 그대로 남는다. |
| **Core Value** | S3(정형 문서 작성 보조)의 시작점인 "양식 등록"을 P2가 채팅 흐름 안에서 끝낸다. 도구가 필요로 하는 입력을 시스템이 먼저 묻는 구조라, 이후 다른 도구(참고 문서·예시 문서)로 같은 카드 모델을 넓힐 수 있다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 위저드는 문서추출기를 추천하지만 양식을 받지 않아, 비개발자가 양식 없는 에이전트를 만들거나 스튜디오에서 올릴 곳을 못 찾는다. |
| **WHO** | P2 부서 담당자(비개발자). 양식 파일(PDF/DOCX)은 가지고 있지만 "문서추출기 패널"이라는 개념은 모른다. |
| **RISK** | 추출(MCP 변환+슬롯 추천)은 수 초~수십 초 걸리고 실패 유형이 5종이다. 위저드가 이 실패를 삼키면 양식 없는 에이전트가 "완료"로 보인다. 추천 슬롯을 그대로 확정하므로 틀린 슬롯이 저장될 수 있다. |
| **SUCCESS** | 신규 사용자가 "여신심의서 작성 에이전트" 요청 → 양식 첨부 → 슬롯 확인 → 생성까지 스튜디오 진입 0회로 완주하고, 생성된 에이전트 상세에 템플릿·슬롯이 저장되어 있다. 기존 위저드(추출기 미선택)·스튜디오 추출기 패널 회귀 0건. |
| **SCOPE** | M1 파이프라인 요청에 템플릿 동봉(백엔드) → M2 양식 요청 카드·첨부·추출·슬롯 확인(프론트 위저드) → M3 건너뛰기 핸드오프·스튜디오 "양식 미등록" 안내(프론트 스튜디오) |

---

## 1. Overview

### 1.1 Purpose

채팅 위저드가 "이 에이전트는 양식이 필요하다"는 사실을 스스로 알리고, 그 자리에서 양식을 받아 추출·슬롯 추천·확정까지 끝낸다. 사용자는 스튜디오의 도구 패널 구조를 몰라도 양식 채우기 에이전트를 완성한다.

### 1.2 Background

사용자 질문 "채팅으로 만들 때 세부 컨트롤 페이지에서 올리기 어려울 것 같은데, 어떤 문서를 올릴지 LLM이 바로 유도하고 첨부하면 그때 분석하게 할 수 있을까"에서 출발했다. 코드 대조 결과는 다음과 같다.

| 구간 | 현재 상태 | 근거 |
|------|----------|------|
| 위저드 단계 | 설명 → 의도 되묻기 → 도구 확정 → 참고 문서(KB, 항상 노출·건너뛰기 가능) → 프롬프트 → 생성. 서버 파이프라인은 5단계(intent·tools·prompt·create·bind) | `idt_front/src/pages/AgentCreateEntryPage/index.tsx:36`, `idt/src/application/agent_create_pipeline/use_case.py` |
| 도구 추천 | 도구 추천 LLM이 의도를 보고 카탈로그에서 고른다. 문서추출기(`internal:document_extractor`)도 후보 | `idt/src/domain/agent_create_pipeline/policies.py:742`, `idt_front/src/types/documentExtractor.ts:68` |
| 문서를 받는 도구 | RAG(참고 문서 N개 → KB), 문서추출기(양식 1개 → HTML+슬롯), 문서생성기(파일 없음, 섹션 수기), 발표자료생성기(관리자 블루프린트) | `idt_front/src/components/agent-builder/*ConfigPanel.tsx` |
| 양식 추출 API | `POST /extract`(multipart) → `html`·`preview_html`·`suggested_slots`·MCP 도구 id 에코. 에러 400/413/502 5종. 세션 없음(stateless) | `idt/src/api/routes/document_extractor_router.py:65` |
| 양식 확정 | 프론트가 `tokenizeHtml`로 `{{key}}` 토큰화 → `DocumentTemplateRequest`를 에이전트 생성 요청의 `document_template` 필드에 동봉. 백엔드는 `build_document_template_plan`이 검증·워커 `tool_config` 주입 | `idt_front/src/utils/documentTemplate.ts`, `idt/src/application/agent_builder/document_template_binding.py` |
| 파이프라인 생성 요청 | `AgentPipelineRequest`에 `kb_id`는 있으나 `document_template`은 없다. CREATE 단계가 `CreateAgentRequest`를 만들 때 템플릿을 싣지 않는다 | `idt/src/interfaces/schemas/agent_pipeline.py:64`, `use_case.py:326-345` |
| 위저드 → 스튜디오 핸드오프 | `WizardResult.kbId`로 RAG 프리필. 추출기 드래프트는 `agentFormPrefill`이 도구 선택 여부에 따라 유지/삭제만 한다 | `idt_front/src/store/agentDraftStore.ts:25`, `idt_front/src/utils/agentFormPrefill.ts:64` |
| 스튜디오 추출기 패널 | 파일 입력 → 추출 → 슬롯 편집·재추천 → 확정. 도구만 있고 템플릿이 없을 때의 안내 문구 없음 | `idt_front/src/components/agent-builder/DocumentExtractorConfigPanel.tsx:106` |
| 에이전트 생성 시 템플릿 부재 | `document_template`은 optional이라 추출기 도구만 있고 템플릿이 없어도 생성된다 | `idt/src/application/agent_builder/schemas.py:138` |

사용자 확인 사항(2026-11-05):

- 대상 도구: **문서추출기 양식만**. 문서생성기 예시 문서·발표자료 블루프린트는 이번 범위 밖.
- 판단 트리거: **확정 도구에 문서추출기가 있으면** 양식 요청. 별도 LLM 판정을 두지 않는다. 도구 추천 LLM이 의도("ㅇㅇ데이터로 ㅇㅇ문서 작성")를 보고 추출기를 고른 결과가 곧 "양식이 필요하다"는 판단이다.
- 요청 문구: 에이전트 의도를 반영해 구체화한다("여신심의서 양식 파일(PDF/DOCX)을 올려주세요").
- 슬롯 처리: 추천 슬롯 목록을 보여주고 **확인 1클릭**으로 확정. 세부 수정은 스튜디오.
- 건너뛰기: **도구 유지 + 스튜디오 추출기 패널에 "양식 미등록" 안내**. 에이전트는 생성된다.
- 기존 KB 단계: **그대로 두고 같은 문서 단계 화면에 양식 카드를 추가**. 단계 수 불변.
- UI 위치: 위저드 안 요청 카드. 첨부 즉시 분석.

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` S3 ("양식 등록 → 채팅으로 슬롯 채움 → 근거 없는 슬롯은 공란"), P2 주인공
- 선행 사이클: `docs/archive/2026-11/agent-kb-quick-setup/` (위저드 문서 단계·`kb_id` additive 전달·G1~G5 핸드오프 적용례), `idt/docs/archive/2026-08/document-template-extractor/` (추출 API·슬롯 정책·D1 preview/D2 토큰화/D7 sessionStorage 제외)
- 위키: `docs/wiki/frontend/screens/agent-screens.md`, `docs/wiki/backend/db/erd-document-tooling.md`(워커당 active 템플릿 1개는 UseCase 보장), `docs/wiki/frontend/patterns/common-card-components.md`(ProgressCard·question-card 재사용), `docs/wiki/frontend/patterns/cross-route-draft-handoff.md`(G1~G5), `docs/wiki/backend/patterns/stateless-hitl-clarification.md`(클라 신고값 서버 재검증), `docs/wiki/backend/patterns/declared-slot-elicitation.md`(요청은 선언된 축의 함수), `docs/wiki/conventions/additive-contract-extension.md`, `docs/wiki/conventions/false-green-quality-gates.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 파이프라인 요청에 양식 템플릿 동봉 (백엔드)**
  - `AgentPipelineRequest`에 `document_template: DocumentTemplateRequest | None` 추가(additive, 기존 스키마 동형 재사용)
  - CREATE 단계가 `CreateAgentRequest.document_template`로 그대로 전달. 검증·저장은 기존 `build_document_template_plan`/`persist_document_template` 경로 재사용(우회 금지)
  - 확정 도구에 문서추출기가 없는데 템플릿이 오면 기존 `ValueError`(워커 부재)가 422로 노출되도록 라우터 매핑 확인
  - `tools_proposed` 응답에 `document_requests: [{tool_id, kind, message, accept}]` 추가. kind는 `form_template` 하나로 시작. message는 의도 purpose 슬롯을 끼운 결정적 템플릿 문구(LLM 호출 없음)
- [ ] **M2 양식 요청 카드 (프론트 위저드)**
  - 문서 단계 화면 상단에 `document_requests`가 있을 때만 "양식 요청 카드" 렌더. 기존 참고 문서 블록은 그 아래 유지
  - 카드: 요청 문구 + 파일 입력(PDF/DOCX) → 즉시 `documentExtractorService.extract` 호출 → 진행 표시 → 추천 슬롯 목록(이름·설명) + [이대로 사용] / [다시 올리기]
  - [이대로 사용] 시 `tokenizeHtml`로 `DocumentTemplateRequest` 생성해 위저드 상태에 보관. 이후 PROMPT/CREATE 요청에 `document_template` 동봉(`kb_id`와 같은 방식)
  - 추출 실패(400/413/502)는 카드 안에 사유 문구로 표시하고 재시도 가능. 실패 상태로는 [계속] 불가, [건너뛰기]는 가능
  - 프롬프트 단계 진입 후 카드는 읽기 전용 이력("✓ 양식 등록: {파일명}, 슬롯 n개" / "✓ 건너뜀")
- [ ] **M3 건너뛰기 핸드오프 + 스튜디오 안내 (프론트 스튜디오)**
  - `WizardResult`에 `documentTemplate?: DocumentTemplateRequest | null`과 `documentRequests` 추가. "직접 만들기" 핸드오프 시 스튜디오 추출기 드래프트로 프리필(G1~G5)
  - 스튜디오 추출기 패널: 도구는 있는데 템플릿이 없으면 패널 상단에 같은 요청 문구("양식 미등록 — {message}")를 띄운다. 위저드에서 생성 후 `?edit` 진입 시에도 동일
- [ ] API 계약 동기화 (`idt_front/src/types/agentPipeline.ts`, `services`, `hooks`)
- [ ] 기존 테스트 회귀 0건 증명(정렬된 FAILED 목록 diff)

### 2.2 Out of Scope

- 문서생성기 예시 문서 → 섹션 아웃라인 자동 추출(신규 분석 기능). 후속 사이클 후보
- 발표자료생성기 블루프린트 요청(관리자 자산)
- 도구 선택과 별개의 "양식 필요 여부" LLM 판정
- 요청 문구의 LLM 생성. 결정적 템플릿 + purpose 슬롯으로 시작하고, 어색하면 후속에서 LLM 문구로 교체(degraded 폴백은 이 템플릿)
- 위저드 안 슬롯 편집·재추천(refine). 스튜디오 패널 기능 그대로
- 추출 비동기 잡 전환(현재 동기 호출 유지)
- 양식 여러 개 첨부(워커당 active 템플릿 1개 계약 유지)
- 위저드 진행 상태 영속(새로고침 시 유실은 정의된 동작 — A-6)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `stop_after=tools` 응답(`tools_proposed`)에 `document_requests` 배열을 추가한다. 확정 후보 `final_tool_ids`에 `internal:document_extractor`가 있으면 `{tool_id, kind: "form_template", message, accept: ["pdf","docx"]}` 1건, 없으면 빈 배열. 기존 소비자는 필드를 무시해도 동작한다 | High | Pending |
| FR-02 | 요청 `message`는 결정적 템플릿이다. purpose 슬롯이 있으면 "{purpose}에 쓸 양식 파일(PDF/DOCX)을 올려주세요. 양식의 빈칸을 자동으로 찾아 채움 항목으로 만듭니다", 없으면 purpose 없는 일반 문구. degraded 의도의 슬롯은 쓰지 않는다 | High | Pending |
| FR-03 | 사용자가 도구 단계에서 추출기를 추가·제거하면 `tools_confirmed` 재호출 응답의 `document_requests`가 그에 맞게 바뀐다(선언 기반, 추천 결과가 아니라 확정 목록 기준) | High | Pending |
| FR-04 | `AgentPipelineRequest`에 `document_template`(optional)을 추가하고 CREATE 단계가 `CreateAgentRequest.document_template`로 전달한다. 검증·저장은 기존 템플릿 바인딩 경로를 그대로 거친다 | High | Pending |
| FR-05 | 확정 도구에 추출기가 없는데 `document_template`이 오면 422와 사유를 돌려준다. 조용히 버리지 않는다 | High | Pending |
| FR-06 | 위저드 문서 단계에 `document_requests`가 1건 이상이면 요청 카드를 참고 문서 블록 위에 렌더한다. 0건이면 기존 화면과 동일 | High | Pending |
| FR-07 | 카드에서 파일을 고르면 즉시 추출 API를 호출하고 진행 상태를 표시한다. 성공 시 추천 슬롯 목록(label·description)과 [이대로 사용]·[다시 올리기]를 보여준다 | High | Pending |
| FR-08 | [이대로 사용]은 `tokenizeHtml` 결과로 `DocumentTemplateRequest`를 만들어 위저드 상태에 보관하고, 이후 PROMPT·CREATE 요청에 동봉한다. 템플릿 이름은 파일명(확장자 제거) | High | Pending |
| FR-09 | 추출 실패는 카드 안에 에러 코드별 안내(형식 오류·용량 초과·변환 도구 미설정·변환 실패·슬롯 추출 실패)로 표시하고 재시도할 수 있다. 실패 상태에서 [계속]은 비활성, [건너뛰기]는 가능 | High | Pending |
| FR-10 | 건너뛰면 추출기 도구는 유지된 채 핸드오프된다(생성은 스튜디오 [저장]). 핸드오프·스튜디오 패널에 "양식 미등록" 상태가 남는다. *(Act-1 정정: "에이전트가 생성된다" → 위저드 무저장 계약 반영)* | High | Pending |
| FR-11 | 프롬프트 단계 진입 후 카드는 읽기 전용 이력으로 바뀐다("✓ 양식 등록: {파일명}·슬롯 n개" 또는 "✓ 건너뜀"). 뒤로 가면 다시 편집 가능 | Medium | Pending |
| FR-12 | "직접 만들기" 핸드오프 `WizardResult`에 `documentTemplate`을 실어, 스튜디오 추출기 드래프트가 확정 상태(`confirmed=true`, skeleton·slots 채움)로 프리필된다 | Medium | Pending |
| FR-13 | 스튜디오 추출기 패널은 도구가 선택됐고 템플릿 드래프트가 비어 있으면 상단에 "양식 미등록 — {message}" 안내를 띄운다. 위저드 건너뛰기·`?edit` 진입·스튜디오 직접 추가 세 경로 모두 동일 | Medium | Pending |
| FR-14 | 참고 문서(KB) 블록·건너뛰기·계속 버튼의 기존 동작은 바뀌지 않는다. 양식 카드가 있어도 KB 없이 [계속] 가능 조건은 "양식 확정 또는 KB 연결 중 하나" | High | Pending |
| FR-15 | 양식 카드 첨부 중(추출 진행 중)에는 [건너뛰기]·[계속]을 비활성화해 미완료 추출이 버려지지 않게 한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 추출기 미선택 위저드 흐름·스튜디오 추출기 패널·에이전트 생성 API 회귀 0건 | 백엔드·프론트 회귀는 정렬된 `FAILED` 목록 diff (`false-green-quality-gates`) |
| 계약 | API 변경은 전부 additive(optional 요청 필드·응답 필드 추가). 기존 요청 본문으로 기존 응답 동일 | 기존 요청 → 응답 동등 단언 테스트 |
| 신뢰 경계 | `document_template`은 클라이언트 생성 입력이다. 서버는 기존 `SlotPolicy`·`TemplateTokenPolicy` 검증을 반드시 거친다(stateless-hitl "클라 신고값 재검증") | 바인딩 경로 우회 금지 AST 계약 테스트 |
| 실패 경계 | 추출 실패는 카드에 노출(degraded 아님, 사용자 재시도). 템플릿 검증 실패는 생성 요청 전체 422(전파) | 라우터 에러 매핑 테스트 |
| 성능 | 추출 호출은 기존 API 그대로(추가 지연 없음). 요청 문구 생성은 LLM 호출 0회 | 파이프라인 LLM 호출 횟수 단언 |
| 접근성 | 파일 입력은 label 연결, 슬롯 목록은 list 시맨틱, 상태 변화는 aria-live | RTL 쿼리(`getByLabelText`, `getByRole('list')`) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 신규 사용자가 "여신심의서를 자동으로 작성해 주는 에이전트" 입력 → 도구 확정(추출기 포함) → 양식 카드에 DOCX 첨부 → 슬롯 확인 → 프롬프트 → [스튜디오로 보내기] → 스튜디오 [저장] 1회로 완주. **추출기 패널 탐색 0회**(스튜디오는 확정 템플릿이 프리필된 상태로 열린다). 저장된 에이전트 상세의 추출기 워커에 `template_id`가 있다. *(Act-1 정정: 위저드는 무저장 계약이라 생성은 스튜디오 [저장]에서 일어난다. 원문 "스튜디오 진입 0회"는 성립하지 않아 "패널 탐색 0회, 스튜디오 저장 1회"로 고쳤다 — Analysis G1)*
- [ ] SC-2: 추출기가 확정 목록에 없으면 문서 단계 화면이 현재와 바이트 단위로 동일(스냅샷)하고 `document_requests`는 빈 배열
- [ ] SC-3: 추출 실패 5종 각각이 카드 안 안내로 보이고, 재시도 성공 시 정상 진행
- [ ] SC-4: 건너뛰기 → 생성된 에이전트를 `?edit`으로 열면 추출기 패널에 "양식 미등록" 안내가 보이고, 거기서 올리면 기존 경로로 저장된다
- [ ] SC-5: "직접 만들기" 핸드오프 후 스튜디오 추출기 패널이 확정 상태(슬롯 목록·미리보기)로 열린다
- [ ] SC-6: 추출기 없이 `document_template`을 실은 요청은 422
- [ ] 백엔드 `uv run python -m pytest`·프론트 `vitest --no-file-parallelism` 회귀 FAILED 목록 diff 0건, `tsc -b`·lint 통과
- [ ] API 계약 동기화(`types`·`services`·`hooks`) 완료

### 4.2 Quality Criteria

- [ ] TDD: 각 모듈 테스트 선작성(Red → Green)
- [ ] 신규 백엔드 코드 함수 40줄·if 중첩 2단계 준수
- [ ] 컴포넌트 파일 런타임 상수 export 금지(`types/`로 분리)
- [ ] 뮤테이션 버튼은 `LoadingButton` 사용

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 추출이 수십 초 걸려 사용자가 이탈·새로고침 → 위저드 상태 유실 | Medium | Medium | 카드에 진행 상태·예상 안내 표시, 첨부 중 버튼 비활성(FR-15), 이탈 경고는 기존 beforeunload 재사용. 영속은 비목표(A-6) |
| 추천 슬롯을 확인만 하고 확정 → 틀린 슬롯 저장 | Medium | Medium | 카드에 슬롯 label·description·sample_value를 보여 판단 근거 제공. "세부 수정은 스튜디오에서" 링크. S3 원칙상 런타임은 근거 없는 슬롯을 공란으로 두므로 피해는 "빈칸"에 그친다 |
| `document_template` 클라이언트 입력을 서버가 신뢰 | High | Low | 기존 바인딩 경로(`SlotPolicy`·`TemplateTokenPolicy`) 재사용을 AST 테스트로 고정. 파이프라인 내 별도 저장 경로 금지 |
| 도구 단계에서 추출기를 뺐는데 템플릿이 남아 422 | Medium | Medium | 프론트가 `document_requests` 빈 배열 수신 시 보관 템플릿을 버린다(FR-03 연동). 서버 422는 2차 방어선(FR-05) |
| `tools_proposed` 응답 확장이 기존 위저드 테스트(MSW 핸들러)를 깨뜨림 | Low | Medium | 필드 optional + 기본 빈 배열. 핸들러는 훅 select와 맞춰 수정(false-green 주의) |
| 요청 문구가 purpose 슬롯 문장과 어색하게 결합 | Low | High | 문구 템플릿 단일 상수 + 테스트 3케이스(purpose 있음/없음/degraded). 어색하면 후속에서 LLM 문구로 교체 가능하도록 `message`를 서버 소유로 둔다 |
| 스튜디오 추출기 드래프트가 sessionStorage 기반(D7)이라 핸드오프 프리필과 충돌 | Medium | Medium | 핸드오프는 G1~G5(1회성 consume) 우선, 적용 후 sessionStorage에 동일 드래프트 저장. 선례: `kb_id` 핸드오프 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `AgentPipelineRequest` (`idt/src/interfaces/schemas/agent_pipeline.py`) | API Schema | `document_template: DocumentTemplateRequest \| None` 추가(additive) |
| `AgentPipelineResponse` / `PipelineOutcome` | API Schema / DTO | `document_requests: list[DocumentRequestOut]` 추가(기본 빈 배열) |
| `AgentCreatePipelineUseCase._run_create` / `_Run` | Application | `document_template` 전달, `document_requests` 계산(Policy 순수 함수) |
| `PipelinePolicy` (`idt/src/domain/agent_create_pipeline/policies.py`) | Domain | `document_requests_for(tool_ids, intent)` 순수 함수 + 문구 상수 |
| `agent_pipeline_router` (동기·SSE) | Router | 템플릿 검증 `ValueError`/`InvalidSlotError`/`TemplateTokenMismatchError` → 422 매핑 확인 |
| `idt_front/src/types/agentPipeline.ts` | Type | 요청·응답 타입 동기화 |
| `AgentCreateEntryPage/index.tsx`, `components/DocumentsStep.tsx` | UI | 양식 요청 카드 조립, 상태(`documentTemplate`, `documentRequests`) 보관·동봉 |
| `components/FormTemplateRequestCard.tsx` (신규) | UI | 요청 문구·첨부·추출·슬롯 목록·확인 |
| `agentDraftStore.WizardResult`, `wizardResultToForm.ts` | Store / Util | `documentTemplate` 핸드오프·프리필 |
| `DocumentExtractorConfigPanel.tsx` | UI | "양식 미등록" 안내 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `AgentPipelineRequest` | CREATE | `AgentCreateEntryPage` → `agentPipelineService` → `/agent-pipeline` POST·SSE | None (optional 필드) |
| `AgentPipelineRequest` | CREATE | 외부 호출자(동기 POST, 위저드 외) | None (기존 본문 동일 응답) |
| `PipelineOutcome` | READ | 동기 라우터(마지막 outcome만)·SSE 라우터(final 이벤트) | Needs verification (직렬화 동일성 테스트에 신규 필드 포함) |
| `AgentCreatePipelineUseCase` | CALL | `agent_pipeline_router`, 파이프라인 테스트 | Needs verification (기본 인자 무변경) |
| `CreateAgentRequest.document_template` | CREATE | 스튜디오 저장(`AgentBuilderPage`) → `create_agent_use_case` | None (경로 재사용, 변경 없음) |
| `document_template_binding` | CREATE/UPDATE | `create_agent_use_case`, `update_agent_use_case` | None |
| `documentExtractorService.extract` | CALL | `DocumentExtractorConfigPanel` | None (호출자 추가만) |
| `WizardResult` | WRITE/READ | `AgentCreateEntryPage.goStudio` → `AgentBuilderPage` consume | Needs verification (G1~G5 테스트에 신규 필드) |
| `DocumentsStep` | RENDER | `AgentCreateEntryPage` | Needs verification (`document_requests` 0건 스냅샷 동일) |
| `DocumentExtractorConfigPanel` | RENDER | `LeftConfigPanel`, `DocumentExtractorConfigModal` | Needs verification (안내 문구 조건부, 기존 테스트 유지) |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 요청·기존 상태에서 응답·렌더 동일 단언
- [ ] 인증·권한 변경 없음(추출 API·생성 API 기존 가드 그대로)
- [ ] 필드 추가가 기존 MSW 핸들러·픽스처를 깨지 않음(FAILED diff)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | SaaS MVP | ☐ |
| **Enterprise** | Strict layer separation, DI | 기존 Thin DDD 백엔드 + React SPA | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 양식 필요 판단 | (a) 확정 도구에 추출기 포함 / (b) 별도 LLM 판정 | **(a)** | 도구 추천 LLM의 선택이 곧 판단. LLM 호출 0회 추가, 도구 단계 편집과 항상 일치(`declared-slot-elicitation`: 요청은 선언된 축의 함수) |
| 요청 문구 생성 | (a) 결정적 템플릿 + purpose / (b) LLM 생성 | **(a)**, 서버 소유 | degraded 없음, 테스트 가능. `message`를 서버가 내려주므로 후속에 (b)로 바꿔도 프론트 무변경 |
| 템플릿 전달 경로 | (a) 파이프라인 요청에 동봉 → CREATE에서 `CreateAgentRequest`로 / (b) 생성 후 별도 PATCH | **(a)** | `kb_id` 선례와 동형. 생성 1회로 끝나 고아 상태 없음. 검증은 기존 바인딩 경로 재사용 |
| 추출 호출 주체 | (a) 프론트가 기존 `/extract` 직접 호출 / (b) 파이프라인 단계 추가 | **(a)** | 5단계 고정 계약(`finalize_steps`) 불변. 추출은 stateless API라 세션 불필요. 스튜디오와 같은 코드 경로 |
| 슬롯 확정 | 추천 목록 확인 1클릭 | 확인 1클릭 | 사용자 확정. 편집은 스튜디오(비목표) |
| 건너뛰기 | 도구 유지 + 안내 | 도구 유지 + 안내 | 사용자 확정. 생성 자체를 막지 않는다 |
| 카드 컴포넌트 | 신규 `FormTemplateRequestCard` / `ProgressCard`·`question-card` 재사용 | 신규 카드 + 진행은 `ProgressCard` | 파일 첨부·슬롯 목록은 기존 공통 카드 형태가 아님. 진행 표시만 재사용(`common-card-components`) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 구조 유지)

백엔드 (idt/)
  domain/agent_create_pipeline/policies.py   ← document_requests_for (순수 함수·문구 상수)
  application/agent_create_pipeline/          ← _Run.document_template, events.PipelineOutcome.document_requests
  interfaces/schemas/agent_pipeline.py        ← 요청·응답 additive 필드
  api/routes/agent_pipeline_router.py         ← 422 매핑 확인

프론트 (idt_front/)
  types/agentPipeline.ts                      ← DocumentRequest, 요청 document_template
  pages/AgentCreateEntryPage/components/FormTemplateRequestCard.tsx (신규)
  pages/AgentCreateEntryPage/components/DocumentsStep.tsx            ← 카드 조립
  pages/AgentCreateEntryPage/index.tsx                               ← 상태·동봉
  utils/wizardTemplate.ts (신규)              ← 추출 응답 → DocumentTemplateRequest 변환(tokenizeHtml 재사용)
  store/agentDraftStore.ts, utils/wizardResultToForm.ts              ← 핸드오프
  components/agent-builder/DocumentExtractorConfigPanel.tsx          ← 미등록 안내
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙(루트·idt·idt_front)
- [x] ESLint / Prettier / TypeScript 설정(idt_front)
- [x] 백엔드 세부 규칙 `idt/docs/rules/*.md`
- [ ] `docs/01-plan/conventions.md` (없음, 불필요)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 문구 상수 위치 | 서버 Policy 상수 | `message` 템플릿은 `policies.py` 단일 출처, 프론트는 표시만 | High |
| 요청 kind 값 | 없음 | `form_template` StrEnum, VARCHAR 아닌 응답 전용(DB 없음) | High |
| 프론트 상수 export | `types/*.ts` | 카드 트리거·에러 코드 매핑은 `types/agentPipeline.ts` | High |
| 에러 코드 → 문구 | 스튜디오 패널에 산재 | 추출 에러 코드 5종 문구를 유틸 1곳으로 모아 패널·카드 공유 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | 추출 MCP 도구·상한은 기존 config 재사용 | — | ☐ |

### 8.4 Pipeline Integration

해당 없음(PDCA 단일 기능 사이클).

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`docs/02-design/features/wizard-template-request.design.md`) — 3안 비교 후 선택
2. [ ] Design에서 `document_requests` 응답 스키마·카드 상태 머신·핸드오프 필드 확정
3. [ ] 구현 순서: M1(백엔드) → M2(위저드 카드) → M3(핸드오프·스튜디오 안내)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — 사용자 확인 7항목 반영 | 배상규 |
