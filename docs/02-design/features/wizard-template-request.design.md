# wizard-template-request Design Document

> **Summary**: 채팅 위저드가 확정 도구에 문서추출기가 있으면 서버가 내려준 "양식 요청"을 카드로 띄우고, 첨부 즉시 기존 추출 API로 슬롯을 추천받아 확인 1클릭으로 템플릿을 생성 요청에 동봉한다. 선택 설계: **Option C — 실용 균형**.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft
> **Plan**: `docs/01-plan/features/wizard-template-request.plan.md`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 위저드는 문서추출기를 추천하지만 양식을 받지 않아, 비개발자가 양식 없는 에이전트를 만들거나 스튜디오에서 올릴 곳을 못 찾는다. |
| **WHO** | P2 부서 담당자(비개발자). 양식 파일(PDF/DOCX)은 가지고 있지만 "문서추출기 패널"이라는 개념은 모른다. |
| **RISK** | 추출(MCP 변환+슬롯 추천)은 수 초~수십 초 걸리고 실패 유형이 5종이다. 위저드가 이 실패를 삼키면 양식 없는 에이전트가 "완료"로 보인다. 추천 슬롯을 그대로 확정하므로 틀린 슬롯이 저장될 수 있다. |
| **SUCCESS** | 신규 사용자가 "여신심의서 작성 에이전트" 요청 → 양식 첨부 → 슬롯 확인 → 생성까지 스튜디오 진입 0회로 완주하고, 생성된 에이전트 상세에 템플릿·슬롯이 저장되어 있다. 기존 위저드(추출기 미선택)·스튜디오 추출기 패널 회귀 0건. |
| **SCOPE** | M1 파이프라인 요청에 템플릿 동봉(백엔드) → M2 양식 요청 카드·첨부·추출·슬롯 확인(프론트 위저드) → M3 건너뛰기 핸드오프·스튜디오 "양식 미등록" 안내(프론트 스튜디오) |

---

## 1. Overview

### 1.1 Design Goals

1. 서버 파이프라인 5단계(intent·tools·prompt·create·bind)와 `finalize_steps` 고정 계약을 바꾸지 않는다. 추출은 프론트가 기존 stateless API를 직접 호출한다.
2. "양식이 필요하다"는 판단과 요청 문구는 서버가 소유한다(순수 함수, LLM 호출 0회). 프론트는 받은 `document_requests`를 표시만 한다.
3. 템플릿은 `kb_id`와 같은 방식으로 파이프라인 요청에 동봉해 CREATE 단계가 기존 `CreateAgentRequest.document_template` 경로로 넘긴다. 별도 저장 경로를 만들지 않는다.
4. 모든 API 변경은 additive다. 기존 요청 본문으로 기존 응답이 바이트 단위로 같다.
5. 위저드 카드는 "첨부 → 추천 슬롯 확인 → 이대로 사용"만 한다. 편집·재추천은 스튜디오 패널의 책임으로 남긴다.

### 1.2 Design Principles

- **선언된 축의 함수**: 요청은 확정 도구 목록의 함수다. 추천 결과가 아니라 사용자가 확정한 목록으로 계산한다(`declared-slot-elicitation`).
- **클라 신고값 재검증**: `document_template`은 클라이언트가 만든 입력이다. 기존 `SlotPolicy`·`TemplateTokenPolicy`를 반드시 거친다(`stateless-hitl-clarification`).
- **실패 경계**: 추출 실패는 카드에 노출하고 사용자가 재시도한다(degraded 아님). 템플릿 검증 실패는 요청 전체 422(전파). 저장 실패를 200으로 위장하지 않는다(`degradation-vs-failure-boundary`).
- **회귀 0 증명**: 정렬된 FAILED 목록 diff(`false-green-quality-gates`).
- **기존 드래프트 형태 재사용**: 위저드가 만든 템플릿은 스튜디오의 `DocumentExtractorDraft`와 같은 모양으로 보관해 핸드오프·sessionStorage 복원·저장 payload 변환을 전부 기존 유틸로 처리한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 항목 | A. 최소 변경 | B. 클린 분리 | **C. 실용 균형 (선택)** |
|---|---|---|---|
| 요청 판단·문구 | 프론트가 `selectedIds`로 판단, 문구도 프론트 상수 | 신규 domain 모듈 `document_request`(도구별 선언 레지스트리·kind enum·Policy) | `PipelinePolicy.document_requests_for()` 순수 함수 + 응답 DTO. kind enum 1값. 문구 서버 소유 |
| 템플릿 전달 | 파이프라인 요청 `document_template` 통과 + 422 매핑 | 동일 | 동일 |
| 프론트 카드 | 스튜디오 `DocumentExtractorConfigPanel`을 위저드에 그대로 삽입 | kind별 핸들러 레지스트리 + 범용 카드 | 전용 `FormTemplateRequestCard` 1개 + `wizardTemplate.ts` 유틸 |
| 핸드오프 | `WizardResult.documentExtractorDraft` | 동일 | 동일 |
| 복잡도 / 유지보수 / 공수 / 위험 | 낮음 / 낮음 / 1세션 / "확인 1클릭" 결정과 불일치 | 높음 / 높음 / 3세션+ / YAGNI·과도한 추상화 | 중간 / 중간 / 2~3세션 / 낮음 |

선택 사유: Plan §7.2 결정(서버 소유 문구·LLM 0회·확인 1클릭)을 전부 충족하면서, 후속 kind(예시 문서·KB)는 `kind` 필드와 카드 분기만으로 열어둔다. 사용자 확인(2026-11-05).

### 2.1 Component Diagram

```
┌──────────────────────────── idt_front (위저드) ─────────────────────────────┐
│ AgentCreateEntryPage/index.tsx                                                │
│   state: documentRequests · templateDraft · templateSkipped · templateBusy    │
│   ├─ ToolsStep (기존)                                                         │
│   ├─ DocumentsStep (수정)                                                     │
│   │    ├─ FormTemplateRequestCard (신규) ── useExtractDocument ──► POST /extract│
│   │    │     idle → extracting → review(slots) → confirmed │ error            │
│   │    │     confirm: wizardTemplate.ts (tokenizeHtml 재사용)                  │
│   │    └─ KnowledgeDocsBlock (기존, 무변경)                                   │
│   └─ PromptStep (기존)                                                        │
│   requestPrompt(): document_template = buildDocumentTemplateRequest(draft)    │
│   goStudio(): WizardResult.documentExtractorDraft = templateDraft             │
└───────────────────────────────────────┬───────────────────────────────────────┘
                                        │ POST /agent-pipeline (+SSE)
┌───────────────────────────────────────▼───────────────────────────────────────┐
│ idt (백엔드)                                                                   │
│ interfaces/schemas/agent_pipeline.py                                            │
│   AgentPipelineRequest.document_template (additive)                             │
│   AgentPipelineResponse.document_requests (additive, 기본 [])                   │
│ api/routes/agent_pipeline_router.py                                             │
│   _run_kwargs: document_template 전달 · DocumentExtractorError → 422            │
│ application/agent_create_pipeline/use_case.py                                   │
│   _Run.document_template · 모든 outcome 에 document_requests 계산               │
│   _run_create: 도구 정합 검증 → CreateAgentRequest.document_template 전달       │
│ domain/agent_create_pipeline/policies.py                                        │
│   DocumentRequest DTO · document_requests_for() · validate_template_tools()     │
│   FORM_TEMPLATE_MESSAGE 상수 (purpose 유/무 2종)                                 │
│ application/agent_builder/create_agent_use_case.py (무변경, 기존 바인딩 경로)    │
└─────────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────── idt_front (스튜디오) ───────────────────────────┐
│ utils/wizardResultToForm.ts: documentExtractorDraft 프리필 (1줄)               │
│ LeftConfigPanel → DocumentExtractorConfigPanel: 미등록 안내 문구 (prop 1개)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[도구 확정] tools_confirmed=true, stop_after=tools
  └─ 서버: final_tool_ids 에 internal:document_extractor 포함?
       ├─ 예 → document_requests=[{tool_id, kind:"form_template", message, accept}]
       └─ 아니오 → document_requests=[]  (프론트: templateDraft 를 버린다)
[문서 단계]
  카드 idle ─(파일 선택)─► extracting ─► POST /extract
       ├─ 200 → review: suggested_slots 나열 + [이대로 사용]/[다시 올리기]
       │        [이대로 사용] → tokenizeHtml(html, slots) → usedSlots≥1 ? confirmed : error
       └─ 4xx/5xx → error(code별 문구) + [다시 올리기]
  [계속] 활성 조건: templateDraft.confirmed || kbId      (FR-14)
  [건너뛰기]/[계속] 비활성: extracting 중                  (FR-15)
[프롬프트 요청] stop_after=prompt
  document_template = buildDocumentTemplateRequest(templateDraft, suggestedName)
[스튜디오로 보내기] (위저드는 무저장 계약 — 생성은 스튜디오 [저장]에서. Act-1 정정, Analysis G1)
  WizardResult.documentExtractorDraft → wizardResultToForm → form.documentExtractorDraft
  스튜디오 [저장] → POST /api/v1/agents (document_template 동봉) → 기존 바인딩·검증·저장
  → DocumentExtractorError 는 422 (Act-1 G2: agent_builder_router 생성·수정 핸들러 매핑)
[논스톱 생성 요청] (stop_after 없음 — 외부 동기 호출자 경로)
  서버 _run_create: validate_template_tools(tool_ids, has_template) ─실패→ ValueError → 422
                    CreateAgentRequest(document_template=…) → 기존 바인딩·검증·저장
```

### 2.3 Dependencies

| 의존 | 종류 | 비고 |
|---|---|---|
| `POST /api/document-extractor/extract` | 기존 API | 호출자 추가만. 타임아웃 180s 유지 |
| `tokenizeHtml`, `buildDocumentTemplateRequest`, `DocumentExtractorDraft` | 기존 프론트 유틸·타입 | 재사용. 신규 변환 로직 없음 |
| `build_document_template_plan` / `persist_document_template` | 기존 백엔드 | 무변경. 파이프라인은 `CreateAgentRequest`로만 전달 |
| `useExtractDocument` | 기존 훅 | 카드에서 사용 |
| `ProgressCard`, `LoadingButton` | 공통 컴포넌트 | 진행 표시·버튼 |
| 신규 패키지 | 없음 | — |

---

## 3. Data Model

### 3.1 Entity Definition

DB 변경 없음. 전부 요청·응답 DTO와 프론트 상태다.

**백엔드 (domain, frozen dataclass)**

```python
# src/domain/agent_create_pipeline/policies.py
class DocumentRequestKind(StrEnum):
    FORM_TEMPLATE = "form_template"

@dataclass(frozen=True)
class DocumentRequest:
    tool_id: str                      # "internal:document_extractor"
    kind: DocumentRequestKind
    message: str                      # 서버 소유 문구
    accept: tuple[str, ...] = ("pdf", "docx")
```

**프론트 상태 (`AgentCreateEntryPage` WizardState 추가 필드)**

| 필드 | 타입 | 의미 |
|---|---|---|
| `documentRequests` | `PipelineDocumentRequest[]` | 마지막 `tools_proposed`/`prompt_ready` 응답의 요청 목록 |
| `templateDraft` | `DocumentExtractorDraft \| null` | 추출 결과 + 확정 상태. 기존 스튜디오 드래프트와 같은 형태 |
| `templateSkipped` | `boolean` | 건너뛰기 이력 표시용(FR-11) |
| `templateBusy` | `boolean` | 추출 진행 중(버튼 비활성, FR-15) |

**카드 내부 상태 머신 (`FormTemplateRequestCard`)**

| 상태 | 진입 | 표시 | 전이 |
|---|---|---|---|
| `idle` | 초기 / [다시 올리기] | 요청 문구 + 파일 입력 | 파일 선택 → `extracting` |
| `extracting` | 파일 선택 | `ProgressCard`(양식 변환 → 채움 항목 추천) | 200 → `review`, 에러 → `error` |
| `review` | 추출 성공 | 슬롯 목록(label·description·sample_value) + [이대로 사용]/[다시 올리기] | 확인 → `confirmed`, usedSlots 0 → `error` |
| `confirmed` | tokenize 성공 | "✓ 양식 등록: {파일명} · 슬롯 n개" + [다시 올리기] | [다시 올리기] → `idle` |
| `error` | 추출 실패·토큰화 실패 | 코드별 문구 + [다시 올리기] | → `idle` |
| `locked` | 프롬프트 단계 진입 | 읽기 전용 이력 | 뒤로 가기 → 이전 상태 |

상태는 `templateDraft`에서 파생한다(`draft==null → idle`, `draft && !confirmed → review`, `confirmed → confirmed`). 카드가 자체 상태를 중복 보유하지 않는다. `extracting`·`error`만 카드 로컬.

### 3.2 Entity Relationships

```
AgentPipelineRequest.document_template ──(그대로)──► CreateAgentRequest.document_template
PipelineOutcome.document_requests ◄── document_requests_for(final_tool_ids, intent)
WizardState.templateDraft ──(buildDocumentTemplateRequest)──► document_template
WizardState.templateDraft ──(WizardResult)──► AgentBuilderFormData.documentExtractorDraft
```

### 3.3 Database Schema

해당 없음(마이그레이션 0건). 템플릿 저장은 기존 `document_template` 테이블·기존 UseCase.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 변경 | 설명 |
|---|---|---|---|
| POST | `/api/v1/agents/pipeline` | 요청·응답 additive | 동기 파이프라인 *(Act-1 경로 표기 정정 — G9)* |
| POST | `/api/v1/agents/pipeline/stream` | 동일 (final 이벤트 payload) | SSE |
| POST | `/api/v1/document-extractor/extract` | 무변경 | 위저드 카드가 호출 |
| POST / PATCH | `/api/v1/agents`, `/api/v1/agents/{id}` | `DocumentExtractorError` → 422 매핑 추가 *(Act-1 G2)* | 스튜디오 저장 — 위저드 템플릿의 실제 저장 경로 |

### 4.2 Detailed Specification

**요청 추가 필드** (`AgentPipelineRequest`)

```python
document_template: DocumentTemplateRequest | None = None
"""wizard-template-request §4.2 — 위저드 양식 카드가 확정한 템플릿.
CREATE 단계가 CreateAgentRequest.document_template 로 그대로 넘긴다.
검증·저장은 기존 document_template_binding 경로(우회 없음)."""
```

- `DocumentTemplateRequest`는 `application/agent_builder/schemas.py`의 기존 모델을 재사용한다(name≤200, slots≥1, source_format `pdf|docx`).
- `stop_after=prompt` 요청에도 실릴 수 있다. PROMPT 단계는 쓰지 않고 에코만 한다(프론트가 상태를 잃지 않도록 `document_template_attached: bool` 응답 필드로 확인 가능).

**응답 추가 필드** (`AgentPipelineResponse`)

```python
class DocumentRequestOut(BaseModel):
    tool_id: str
    kind: Literal["form_template"]
    message: str
    accept: list[str]

document_requests: list[DocumentRequestOut] = Field(default_factory=list)
"""확정 도구가 필요로 하는 문서 요청. 모든 status 에서 계산(need_input 은 빈 배열)."""
document_template_attached: bool = False
"""요청에 document_template 이 실려 있었는지 에코백."""
```

**문구 규칙** (`FORM_TEMPLATE_MESSAGE`, 서버 상수)

| 조건 | message |
|---|---|
| purpose 슬롯 있음(비 degraded) | `"{purpose}에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요. 양식의 빈칸을 찾아 채움 항목으로 만듭니다."` |
| purpose 없음 / degraded | `"이 에이전트가 채울 양식 파일(PDF 또는 DOCX)을 올려주세요. 양식의 빈칸을 찾아 채움 항목으로 만듭니다."` |

purpose는 `PipelinePolicy.SLOT_VALUE_MAX_CHARS`(200)로 이미 clamp된 값이며 공백 정규화 후 삽입한다.

**정합 검증** (`PipelinePolicy.validate_template_tools`)

```python
@staticmethod
def validate_template_tools(tool_ids: Sequence[str], has_template: bool) -> None:
    """템플릿이 왔는데 확정 도구에 추출기가 없으면 ValueError (FR-05)."""
    if has_template and EXTRACTOR_TOOL_ID not in tool_ids:
        raise ValueError("문서추출기 도구가 없는 에이전트에는 양식을 등록할 수 없습니다")
```

`_run_create`가 `CreateAgentRequest`를 만들기 **전에** 호출한다(저장 전 실패). `EXTRACTOR_TOOL_ID = "internal:document_extractor"`는 프론트 `DOCUMENT_EXTRACTOR_TOOL_ID`와 동일 문자열(`KNOWLEDGE_TOOL_ID` 선례).

**에러 매핑** (`agent_pipeline_router`)

| 예외 | HTTP | 비고 |
|---|---|---|
| `ValueError` | 422 | 기존. 정합 검증·워커 부재 포함 |
| `DocumentExtractorError`(`InvalidSlotError`, `TemplateTokenMismatchError`) | **422** (신규) | 동기·SSE 둘 다. 현재 어떤 라우터도 잡지 않아 500으로 샌다 — 스튜디오 `/api/agents` 경로의 동일 결함은 이번 범위 밖, 보고 항목 |
| 그 외 | 500 | 기존 |

SSE는 예외를 마지막 `stage_started` 기록으로 `stage_failed` 이벤트를 합성한다(기존). 합성 payload에 `detail` 문자열이 실리는지 L1 테스트로 고정한다.

**동일성 계약**: 동기 응답 = SSE final payload. `_to_response` 하나가 두 경로를 만든다(기존 직렬화 동일성 테스트에 신규 필드 2개 포함).

---

## 5. UI/UX Design

### 5.1 Screen Layout

문서 단계(`DocumentsStep`) — `document_requests`가 1건 이상일 때:

```
┌─ 참고할 문서가 있나요? ───────────────────────────── [✓ 양식 등록 · 슬롯 6개] ─┐
│ 양식 요청 카드 (FormTemplateRequestCard)                                       │
│  📄 여신심의서 작성에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요.                 │
│     양식의 빈칸을 찾아 채움 항목으로 만듭니다.                                   │
│  [ 파일 선택 ]  PDF, DOCX                                                       │
│  ── 추출 후 ──                                                                 │
│  채움 항목 6개를 찾았습니다                                                      │
│   • 회사명 — 여신 신청 법인명        (예: ㅇㅇ상사)                             │
│   • 여신금액 — 신청 금액(원)         (예: 500,000,000)                          │
│   • …                                                                          │
│  세부 수정은 생성 후 스튜디오의 문서추출기 패널에서 할 수 있습니다.               │
│                                              [다시 올리기]  [이대로 사용]       │
├────────────────────────────────────────────────────────────────────────────────┤
│ 참고 문서 블록 (KnowledgeDocsBlock, 기존 그대로)                                 │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                     [건너뛰기]      [계속]       │
└────────────────────────────────────────────────────────────────────────────────┘
```

`document_requests`가 0건이면 카드가 없고 화면은 현재와 동일(SC-2 스냅샷).

### 5.2 User Flow

1. 설명 입력 → 의도 되묻기(기존) → 도구 확정(기존, 추출기 포함)
2. 문서 단계: 카드에 파일 드롭 → 진행 카드("양식 변환 → 채움 항목 추천") → 슬롯 목록
3. [이대로 사용] → 카드 `confirmed` → [계속] 활성
4. 프롬프트 단계(기존) → [스튜디오로 보내기] → 스튜디오가 확정 템플릿 프리필 상태로 열림 → [저장] → 생성 완료(템플릿 저장됨). *(Act-1 정정: 위저드는 생성하지 않는다 — G1)*
5. 분기: 2에서 실패 → 코드별 안내 → [다시 올리기] / [건너뛰기]
6. 분기: [건너뛰기] → 프롬프트 → 생성. 스튜디오 `?edit` 진입 시 추출기 패널 상단 안내
7. 분기: 프롬프트 단계에서 [직접 만들기] → 스튜디오 추출기 패널이 확정 상태로 열림

### 5.3 Component List

| 컴포넌트 | 위치 | 신규/수정 | 책임 |
|---|---|---|---|
| `FormTemplateRequestCard` | `pages/AgentCreateEntryPage/components/` | 신규 | 요청 문구·첨부·추출 호출·슬롯 목록·확인·에러 |
| `DocumentsStep` | 동일 | 수정 | 카드 조립, [계속] 조건, busy 전파 |
| `AgentCreateEntryPage/index.tsx` | — | 수정 | 상태 4필드, 응답 동기화, 요청 동봉, 핸드오프 |
| `wizardTemplate.ts` | `utils/` | 신규 | `extractResponseToDraft(resp, file)`, `confirmDraft(draft)`(tokenize 래퍼), `templateNameFromFile` |
| `documentExtractorErrors.ts` | `utils/` | 신규 | 에러 코드 5종 → 문구. 카드와 스튜디오 패널 공유 |
| `DocumentExtractorConfigPanel` | `components/agent-builder/` | 수정 | `emptyNotice?: string` prop — 드래프트 없을 때 상단 안내 |
| `LeftConfigPanel` | 동일 | 수정 | 안내 상수 전달 |
| `wizardResultToForm.ts` | `utils/` | 수정 | `documentExtractorDraft` 프리필 |
| `types/agentPipeline.ts` | — | 수정 | `PipelineDocumentRequest`, 요청 `document_template`, 응답 2필드, `FORM_TEMPLATE_EMPTY_NOTICE` 상수 |

### 5.4 Page UI Checklist

| 항목 | 요구 |
|---|---|
| 파일 입력 | `<label>` 연결, `accept=".pdf,.docx"`, 선택 즉시 호출(별도 업로드 버튼 없음) |
| 진행 표시 | `ProgressCard` 2단계 고정(변환 → 추천). `aria-live="polite"` |
| 슬롯 목록 | `role="list"`, 항목당 label·description·sample_value. 20개 초과 시 "외 n개" 접기 |
| 확인 버튼 | `LoadingButton isPending={busy}`. `review` 상태에서만 노출 |
| 에러 | 코드별 문구 + 원문 detail 보조 표시. `role="alert"` |
| 잠금 이력 | `locked` 시 "✓ 양식 등록: {파일명} · 슬롯 n개" 또는 "✓ 건너뜀(양식)" |
| 버튼 가드 | `templateBusy`면 [건너뛰기]·[계속] 모두 disabled |
| [계속] 조건 | `templateDraft?.confirmed \|\| kbId` |
| 모바일 | 카드 폭 100%, 슬롯 목록 1열 |

---

## 6. Error Handling

### 6.1 Error Code Definition

| 코드 | 출처 | HTTP | 카드 문구 |
|---|---|---|---|
| `INVALID_DOCUMENT` | extract | 400 | PDF 또는 DOCX 파일만 올릴 수 있습니다 |
| `DOCUMENT_TOO_LARGE` | extract | 413 | 파일이 너무 큽니다. 상한을 확인해 주세요 |
| `MCP_TOOL_NOT_CONFIGURED` | extract | 400 | 문서 변환 도구가 설정되지 않았습니다. 관리자에게 문의하세요 |
| `MCP_CONVERSION_FAILED` | extract | 502 | 문서 변환에 실패했습니다. 다른 파일로 다시 시도해 주세요 |
| `SLOT_EXTRACTION_FAILED` | extract | 502 | 채움 항목을 찾지 못했습니다. 다시 시도해 주세요 |
| (프론트) `NO_USABLE_SLOTS` | tokenize | — | 확정할 수 있는 항목이 없습니다. 예시값이 문서에 있는 항목이 1개 이상 필요합니다 |
| `ValueError` 정합 | pipeline create | 422 | 문서추출기 도구가 없는 에이전트에는 양식을 등록할 수 없습니다 |
| `InvalidSlotError` / `TemplateTokenMismatchError` | pipeline create | 422 | 양식 항목 검증에 실패했습니다: {detail} |

### 6.2 Error Response Format

기존 `ApiError(message, status, code)` 인터셉터 그대로. extract 라우터는 `{detail: {code, message}}`, 파이프라인 라우터는 `{detail: str}`. 카드는 `err.code`가 있으면 코드 매핑, 없으면 message 원문.

---

## 7. Security Considerations

- 인증·권한 변경 없음. extract·pipeline·create 모두 기존 `get_current_user` 가드.
- `document_template`은 클라이언트 입력이다. 서버는 `SlotPolicy.validate`(슬롯 수·키 형식)·`TemplateTokenPolicy.validate`(skeleton 토큰 ↔ slots 일치)를 기존 바인딩 경로에서 그대로 수행한다. 파이프라인에 검증 우회 경로를 두지 않음을 AST 테스트로 고정(`persist_document_template`·`document_template_repo` 직접 참조 금지).
- `source_file_id`는 extract가 발급한 소유자 귀속 임시 id다. 기존 `persist_document_template`의 원본 승격(D3)이 소유자 검증을 수행하는지 Do 단계에서 확인하고, 아니면 보고한다.
- 추출 응답 `preview_html`은 저장·토큰화에 쓰지 않는다(기존 D1). 위저드 카드는 미리보기를 렌더하지 않으므로 iframe sandbox 이슈 없음.
- 요청 문구에 끼우는 purpose는 LLM 출력이지만 평문 텍스트로만 렌더(React 기본 이스케이프).

---

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 대상 | 도구 |
|---|---|---|
| Unit (백) | `document_requests_for`, 문구 2종, `validate_template_tools`, outcome 직렬화 동일성, AST 우회 금지 | pytest |
| Unit (프) | `wizardTemplate.ts` 변환, 에러 문구 매핑, `wizardResultToForm` 프리필, 카드 상태 전이 | Vitest + RTL + MSW |
| L1 | 파이프라인 요청·응답 additive, 422 매핑, SSE final payload | TestClient 실요청 |
| L2 | 카드 첨부 → 추출 → 확인 → [계속] 활성 | RTL + MSW(`formData()` 금지, `FormData` 직접 파싱 안 함 — 파일명만 단언) |
| L3 | 설명 → 생성까지 템플릿 저장 확인 | 로컬 TestClient 인프로세스 + 수동 화면 확인 |

### 8.2 L1: API Test Scenarios

| ID | 시나리오 | 기대 |
|---|---|---|
| L1-01 | `stop_after=tools`, 추천 결과에 추출기 포함 | `document_requests` 1건, kind `form_template`, accept `["pdf","docx"]`, message에 purpose 포함 |
| L1-02 | 동일, 추출기 미포함 | `document_requests == []` |
| L1-03 | `tools_confirmed=true, tool_ids`에 추출기 없음 (사용자 제거) | `[]` — 확정 목록 기준(FR-03) |
| L1-04 | degraded 의도 | purpose 없는 일반 문구 |
| L1-05 | 기존 요청 본문(신규 필드 없음) | 응답에 `document_requests: []`, `document_template_attached: false` 외 기존 필드 동일 |
| L1-06 | `document_template` 동봉 + 추출기 포함 + 논스톱 | `created`, `CreateAgentUseCase.execute`가 받은 request의 `document_template`이 동일 객체 |
| L1-07 | `document_template` 동봉 + 추출기 없음 | 422, 저장 UseCase 미호출 |
| L1-08 | 바인딩이 `InvalidSlotError` 발생 | 동기 422 / SSE `stage_failed`(stage=create, detail 포함) |
| L1-09 | `stop_after=prompt` + `document_template` | `prompt_ready`, `document_template_attached: true`, 저장 없음 |
| L1-10 | 동기 응답 == SSE final payload (신규 필드 포함) | 직렬화 동일 |

### 8.3 L2: UI Action Test Scenarios

| ID | 시나리오 | 기대 |
|---|---|---|
| L2-01 | `document_requests` 0건 | 카드 미렌더, DocumentsStep 스냅샷 기존과 동일 |
| L2-02 | 1건 → 파일 선택 | extract 호출(파일명 단언), ProgressCard 표시, [건너뛰기]·[계속] disabled |
| L2-03 | extract 200 | 슬롯 목록 n개, [이대로 사용] 노출 |
| L2-04 | [이대로 사용] | `templateDraft.confirmed=true`, [계속] enabled, 이력 "슬롯 n개" |
| L2-05 | extract 413 | 코드 문구 표시, [다시 올리기] → idle |
| L2-06 | 예시값 미발견으로 usedSlots 0 | NO_USABLE_SLOTS 문구, confirmed 아님 |
| L2-07 | [계속] → PROMPT 요청 | 본문에 `document_template` 포함(name=파일명 sans ext) |
| L2-08 | 도구 단계로 돌아가 추출기 제거 → 재확정 | `document_requests` [] 수신 시 `templateDraft=null` |
| L2-09 | [직접 만들기] | `WizardResult.documentExtractorDraft` 전달, 스튜디오 폼 `documentExtractorDraft.confirmed` |
| L2-10 | 스튜디오: 추출기 도구 선택 + 드래프트 없음 | 패널 상단 안내 문구 노출; 드래프트 있으면 미노출 |
| L2-11 | KB만 연결, 양식 미첨부 | [계속] enabled(FR-14) |

### 8.4 L3: E2E Scenario Test Scenarios

| ID | 시나리오 | 기대 |
|---|---|---|
| L3-01 | "여신심의서 자동 작성 에이전트" → 도구 확정(추출기) → DOCX 첨부 → 확인 → 프롬프트 → 생성 | `GET /api/agents/{id}` 상세에 `document_template.slots ≥ 1`, 스튜디오 진입 0회 |
| L3-02 | 건너뛰기 → 생성 → `/agent-builder?edit={id}` | 추출기 패널 안내 노출, 거기서 업로드·저장 정상 |
| L3-03 | 추출기 미추천 요청("날씨 알려주는 봇") | 문서 단계 화면 기존과 동일 |

### 8.5 Seed Data Requirements

- MCP 변환 도구(pdf→html, html→doc)가 등록된 로컬 DB. 없으면 L3-01은 `MCP_TOOL_NOT_CONFIGURED` 경로(L2-05 계열)로 대체 확인.
- 양식 픽스처: `idt/tests/fixtures/` 기존 DOCX 샘플 재사용(document-template-extractor 사이클).
- 도구 카탈로그에 `internal:document_extractor` 활성(V054 이후 sync).

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
idt/src/
  domain/agent_create_pipeline/policies.py      ← DocumentRequest·Kind·document_requests_for·validate_template_tools·문구 상수
  application/agent_create_pipeline/events.py   ← PipelineOutcome.document_requests·document_template_attached
  application/agent_create_pipeline/use_case.py ← _Run.document_template, _run_create 전달
  interfaces/schemas/agent_pipeline.py          ← DocumentRequestOut, 요청·응답 필드
  api/routes/agent_pipeline_router.py           ← _run_kwargs·_to_response·422 매핑
```

### 9.2 Dependency Rules

- domain은 `src.application.agent_builder.schemas`를 import하지 않는다. `document_template` 유무만 bool로 받는다(`validate_template_tools(tool_ids, has_template)`).
- application은 `DocumentTemplateRequest`를 그대로 들고 `CreateAgentRequest`에 꽂는다. 변환 없음.
- interfaces는 `DocumentTemplateRequest`(application 스키마)를 재사용한다 — 기존 `CreateAgentRequest`와 같은 위치의 모델이라 레이어 규칙 위반이 아니다(`kb_defaults` 선례).
- 라우터는 `DocumentExtractorError`를 domain에서 import해 매핑한다(기존 extract 라우터와 동일 방식).

### 9.3 File Import Rules

- 프론트 컴포넌트 파일에서 런타임 상수 export 금지. `FORM_TEMPLATE_EMPTY_NOTICE`·`DOCUMENT_REQUEST_KIND`는 `types/agentPipeline.ts`.
- `wizardTemplate.ts`는 `utils/documentTemplate.ts`만 import(순수 함수).

### 9.4 This Feature's Layer Assignment

| 변경 | 레이어 | 근거 |
|---|---|---|
| 요청 판단·문구 | domain | 순수 규칙. LLM·DB 없음 |
| 템플릿 전달 | application | 흐름 제어만 |
| 422 매핑 | interfaces/api | 에러 → HTTP |
| 카드·상태 | pages (프론트) | 화면 전용 |
| 변환 유틸 | utils (프론트) | 순수 함수, 테스트 용이 |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

- 백엔드 상수: `EXTRACTOR_TOOL_ID`, `FORM_TEMPLATE_MESSAGE_WITH_PURPOSE`, `FORM_TEMPLATE_MESSAGE_DEFAULT`
- wire 값: `form_template`(StrEnum value). 변경 시 프론트 계약 파괴
- 프론트 타입: `PipelineDocumentRequest`, 상태 필드 `templateDraft`/`templateSkipped`/`templateBusy`

### 10.2 Import Order

기존 프로젝트 규칙(ESLint import/order, 백엔드 isort) 준수.

### 10.3 Environment Variables

추가 없음. 추출 상한·MCP 도구는 기존 config.

### 10.4 This Feature's Conventions

- Design 참조 주석: 파일 상단 `# Design Ref: wizard-template-request §4.2 — ...`, 핵심 분기 `# Plan SC: SC-1`
- 함수 40줄·if 중첩 2단계 준수. `_run_create`가 길어지면 `_build_create_request(ctx)` 분리
- 뮤테이션 버튼 `LoadingButton`, `mutateAsync`는 try/catch
- MSW 핸들러에서 `request.formData()` 호출 금지(메모리: jsdom 미지원) — 파일명은 헤더·URL 또는 모킹된 서비스 호출 인자로 단언
- 회귀 증명: 백 `uv run python -m pytest`(uv run pytest 차단), 프 `vitest --no-file-parallelism`, FAILED 목록 diff

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  src/domain/agent_create_pipeline/policies.py                 [수정]
  src/application/agent_create_pipeline/events.py              [수정]
  src/application/agent_create_pipeline/use_case.py            [수정]
  src/interfaces/schemas/agent_pipeline.py                     [수정]
  src/api/routes/agent_pipeline_router.py                      [수정]
  tests/domain/agent_create_pipeline/test_document_requests.py [신규]
  tests/application/agent_create_pipeline/test_use_case_template.py [신규] (Act-1 실제 파일명으로 정정)
  tests/api/test_agent_pipeline_router_template.py             [신규] (Act-1 실제 파일명으로 정정)
  src/api/routes/agent_builder_router.py (+ tests/api/test_agent_builder_router.py) [Act-1 G2: DocumentExtractorError → 422]
idt_front/
  src/types/agentPipeline.ts                                   [수정]
  src/utils/wizardTemplate.ts (+ .test.ts)                     [신규]
  src/utils/documentExtractorErrors.ts (+ .test.ts)            [신규]
  src/pages/AgentCreateEntryPage/components/FormTemplateRequestCard.tsx (+ .test.tsx) [신규]
  src/pages/AgentCreateEntryPage/components/DocumentsStep.tsx  [수정]
  src/pages/AgentCreateEntryPage/index.tsx (+ 기존 테스트 보강) [수정]
  src/store/agentDraftStore.ts                                 [수정: WizardResult.documentExtractorDraft]
  src/utils/wizardResultToForm.ts (+ .test.ts)                 [수정]
  src/components/agent-builder/DocumentExtractorConfigPanel.tsx (+ .test.tsx) [수정: emptyNotice prop, 기본값 상수 — LeftConfigPanel 수정 불필요]
  src/components/agent-builder/DocumentExtractorConfigModal.tsx [Act-1 G3: emptyNotice 통과]
  src/components/agent-builder/LeftConfigPanel.tsx (+ .test.tsx) [Act-1 G3: savedTemplateId → "양식 등록됨" 배지·교체 안내]
  src/utils/agentDetailMapping.ts (+ .test.ts)                  [Act-1 G3: savedTemplateIdFromWorkers — 추출기 워커 tool_config.template_id 프라임]
  src/types/agentBuilder.ts                                    [Act-1 G3: AgentBuilderFormData.savedTemplateId (프라임 전용, 미전송)]
  src/types/agentPipeline.ts                                   [Act-1 G3: FORM_TEMPLATE_REPLACE_NOTICE]
```

### 11.2 Implementation Order

1. **백엔드 Policy** (TDD): `DocumentRequest`·`document_requests_for`·문구 2종·`validate_template_tools`
2. **백엔드 UseCase·DTO**: `_Run.document_template`, outcome 계산, `_run_create` 전달(정합 검증 선행)
3. **백엔드 스키마·라우터**: 필드 추가, `_run_kwargs`·`_to_response`, 422 매핑, 직렬화 동일성 테스트 갱신
4. **프론트 타입·유틸**: `agentPipeline.ts`, `wizardTemplate.ts`, `documentExtractorErrors.ts`
5. **카드 컴포넌트**: 상태 전이 테스트 → 구현
6. **DocumentsStep·index.tsx**: 상태 4필드, 응답 동기화(빈 배열 시 드래프트 폐기), 요청 동봉, busy 가드, [계속] 조건
7. **핸드오프·스튜디오**: `WizardResult`, `wizardResultToForm`, 패널 안내 prop, `LeftConfigPanel`
8. **회귀 증명**: FAILED diff, `tsc -b`, lint
9. **수동 E2E**: L3-01~03 (MCP 도구 등록된 로컬)

### 11.3 Session Guide

**Module Map**

| scope | 모듈 | 파일 | 선행 |
|---|---|---|---|
| `module-1` | 백엔드 요청 계산·템플릿 전달·422 | policies, events, use_case, schemas, router + 테스트 3 | — |
| `module-2` | 위저드 카드·문서 단계·요청 동봉 | types, wizardTemplate, documentExtractorErrors, FormTemplateRequestCard, DocumentsStep, index.tsx | module-1 (응답 계약) |
| `module-3` | 핸드오프·스튜디오 안내 | agentDraftStore, wizardResultToForm, DocumentExtractorConfigPanel, LeftConfigPanel | module-2 (드래프트 형태) |

**Recommended Session Plan**

| 세션 | scope | 산출 | 종료 조건 |
|---|---|---|---|
| 1 | `module-1` | 백엔드 전부 + L1-01~10 | pytest FAILED diff 0, 기존 파이프라인 테스트 통과 |
| 2 | `module-2` | 카드·문서 단계·요청 동봉 + L2-01~08, L2-11 | vitest FAILED diff 0, `tsc -b` |
| 3 | `module-3` + E2E | 핸드오프·패널 안내 + L2-09~10, L3 수동 | 화면 확인 메모, 보고 항목(스튜디오 500 결함·source_file_id 소유자 검증) 정리 |

```
/pdca do wizard-template-request --scope module-1
/pdca do wizard-template-request --scope module-2
/pdca do wizard-template-request --scope module-3
```

---

## 12. Decision Record

| ID | 결정 | 대안 | 사유 |
|---|---|---|---|
| D1 | 요청 계산은 모든 outcome에서 확정 목록 기준 | tools 정지 응답에만 | 프롬프트 단계 재요청·뒤로가기 후에도 프론트가 재동기화 가능. need_input은 빈 배열 |
| D2 | 위저드 템플릿은 `DocumentExtractorDraft` 형태로 보관 | 위저드 전용 경량 타입 | 핸드오프·sessionStorage 복원·payload 변환을 기존 유틸로 처리. 변환 로직 0 |
| D3 | 정합 검증을 파이프라인 `_run_create`에서 저장 전 수행 | `CreateAgentUseCase`의 워커 부재 ValueError에 의존 | 그 ValueError가 저장 트랜잭션 안에서 나는지 보장 없음. 저장 전 명시 실패가 안전 |
| D4 | `DocumentExtractorError` → 422는 파이프라인 라우터에만 | 전역 핸들러 추가 | 스튜디오 경로 500은 기존 결함. 전역 핸들러는 다른 라우터 응답을 바꿀 수 있어 보고 후 별도 사이클 |
| D5 | 스튜디오 "양식 미등록" 안내는 프론트 상수(일반 문구) | 위저드 서버 문구를 핸드오프로 전달 | 스튜디오 직접 추가·`?edit` 경로에는 서버 문구가 없다. 세 경로 동일 문구가 FR-13 |
| D6 | 카드는 미리보기 렌더 없음 | 스튜디오처럼 iframe 미리보기 | 확인 1클릭 결정. 슬롯 label·description·sample_value로 판단 근거 제공 |
| D7 | `document_template_attached` 에코백 추가 | 없음 | `stop_after=prompt` 응답에서 프론트가 동봉 성공을 확인. 템플릿 본문 에코는 payload 비대 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — Option C 선택, 템플릿 검증 예외 500 결함 발견·보고 | 배상규 |
