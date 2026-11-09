# extractor-template-preview Design Document

> **Summary**: 저장 양식 조회 API(`GET /api/v1/agents/{agent_id}/document-template`)와 빌더 설정 모달의 "저장된 양식 보기" 모드
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-08
> **Status**: Draft
> **Planning Doc**: [extractor-template-preview.plan.md](../../01-plan/features/extractor-template-preview.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 저장 후 양식이 "등록됨" 배지로만 남아 어떤 문서를 만드는 에이전트인지 확인할 수 없다 |
| **WHO** | 에이전트 소유자(P2). 포크로 양식을 물려받은 사용자 포함 |
| **RISK** | 슬롯 예시값(sample_value)에 원본 문서의 실명·금액이 들어 있고, 포크 에이전트는 원작자 양식을 공유한다 |
| **SUCCESS** | `?edit` 진입 시 배지에 양식 이름 표시, 모달에서 저장 양식 미리보기·슬롯 목록 표시, 양식 원작자가 아니면 응답에 예시값 없음 |
| **SCOPE** | 백엔드 조회 API 1개 + 프론트 서비스·훅·배지·모달 보기 모드. 스토어·채팅 노출과 저장 양식 직접 편집 제외 |

---

## 1. Overview

### 1.1 Design Goals

- 저장된 `document_template`을 읽기 전용으로 빌더에 되돌려 준다.
- 예시값 노출 판정은 서버에서 한다.
- 기존 업로드·확정·저장 흐름(위저드 포함)은 바꾸지 않는다.

### 1.2 Plan 대비 변경 (Design 조사 결과)

| Plan 가정 | 코드 사실 | Design 결정 |
|-----------|-----------|-------------|
| 편집자·관리자도 수정 화면에 들어온다 | `VisibilityPolicy.can_edit` = 소유자만 (`idt/src/domain/agent_builder/policies.py`). 관리자는 삭제만 가능 | 조회 권한 = `can_edit`(소유자). 관리자 예외는 두지 않는다(빌더 진입 자체가 불가) |
| 양식은 `(agent_id, worker_id)`로 찾는다 | 포크는 워커 `tool_config`를 그대로 복사(`fork_agent_use_case.py:146`)하고, 런타임은 `find_by_id(template_id)`로 찾는다(`workflow_compiler.py:2103`) | 조회 키 = 추출기 워커 `tool_config.template_id` |
| "다른 사람" = 공동 편집자 | 실제로는 포크 사용자 | 예시값 노출 = 뷰어가 **양식의 원 에이전트(`template.agent_id`) 소유자**일 때만 |

### 1.3 Design Principles

- 조회 결과는 `documentExtractorDraft`에 넣지 않는다(원본 파일 id 만료로 재저장 실패 — wizard-template-request G3).
- 기존 `DocumentExtractorConfigPanel`(위저드 공용)은 수정하지 않는다.
- 미리보기는 `buildPreviewHtml()`의 확정 skeleton 경로(`{{key}}` → 라벨 mark)를 재사용한다.

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | A: 상세 응답 포함 | B: 분리형 | C: 절충형 |
|----------|:-:|:-:|:-:|
| New / Modified Files | 0 / 6 | 5 / 9 | 3 / 7 |
| Complexity | Low | High | Medium |
| Risk | 상세 조회(스토어·채팅)에 LONGTEXT·읽기 권한 느슨 | 위저드 공용 패널 리팩터링 회귀 | 미리보기 폭 측정 ~15줄 중복 |

**Selected**: Option C — **Rationale**: 상세 응답을 무겁게 하지 않고 권한을 엔드포인트 단위로 막으며, 위저드 공용 패널을 건드리지 않는다.

### 2.1 Component Diagram

```
[LeftConfigPanel] ──useAgentDocumentTemplate(agentId)──▶ agentBuilderService.getDocumentTemplate
   │  ├─ ExtractorSummaryBadge (이름·슬롯 수·포맷)            │
   │  └─ DocumentExtractorConfigModal                          ▼
   │        ├─ mode=saved  → SavedTemplateView        GET /api/v1/agents/{id}/document-template
   │        └─ mode=upload → DocumentExtractorConfigPanel     │
   │                                                          ▼
   │                                  GetAgentDocumentTemplateUseCase
   │                                    ├─ AgentRepository.find_by_id(agent_id)        ─ 권한(can_edit)
   │                                    ├─ extractor worker tool_config.template_id
   │                                    ├─ DocumentTemplateRepository.find_by_id(tid)  ─ active 확인
   │                                    ├─ (template.agent_id ≠ agent_id) → 원 에이전트 owner 조회
   │                                    └─ TemplateSampleExposurePolicy → sample_value 마스킹
```

### 2.2 Data Flow

```
?edit 진입 → agentDetailMapping.savedTemplateId 설정
 → LeftConfigPanel: savedTemplateId && !draft && agentId → useQuery
 → 배지 갱신 / 모달 열기 시 saved 모드로 SavedTemplateView 렌더
 → "새 파일로 교체" → upload 모드 → 기존 업로드·확정 → 저장(기존 update 흐름)
 → update 성공 시 queryKeys.agentBuilder.all 무효화(기존) → 새 양식 재조회
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| GetAgentDocumentTemplateUseCase | AgentDefinitionRepositoryInterface, DocumentTemplateRepositoryInterface, VisibilityPolicy, TemplateSampleExposurePolicy | 조회·권한·마스킹 |
| SavedTemplateView | `buildPreviewHtml`, `extractPageWidthPt`, `ptToPx` | 미리보기 |
| useAgentDocumentTemplate | agentBuilderService, queryKeys | 서버 상태 |

---

## 3. Data Model

DB 변경 없음. `document_template`(V037) 읽기만.

### 3.1 응답 DTO (application)

```python
class SavedTemplateSlot(BaseModel):
    key: str
    label: str
    slot_type: Literal["value", "generated"]
    description: str = ""
    sample_value: str = ""          # 마스킹 시 ""

class AgentDocumentTemplateResponse(BaseModel):
    template_id: str
    name: str
    source_format: str              # "pdf" | "docx"
    html_skeleton: str              # {{key}} 토큰 포함
    slots: list[SavedTemplateSlot]
    samples_hidden: bool            # True면 예시값을 지운 응답
    is_inherited: bool              # 포크로 물려받은 양식 (template.agent_id != agent_id)
    updated_at: datetime
```

`fill_hint`는 내부 생성 지침이라 응답에서 뺀다. `source_file_ref`(서버 경로)도 노출하지 않는다.

### 3.2 프론트 타입 (`idt_front/src/types/documentExtractor.ts`)

```ts
export interface SavedTemplateSlot {
  key: string;
  label: string;
  slot_type: SlotType;
  description: string;
  sample_value: string;
}

export interface AgentDocumentTemplateResponse {
  template_id: string;
  name: string;
  source_format: 'pdf' | 'docx';
  html_skeleton: string;
  slots: SavedTemplateSlot[];
  samples_hidden: boolean;
  is_inherited: boolean;
  updated_at: string;
}
```

---

## 4. API Specification

### 4.1 Endpoint

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/agents/{agent_id}/document-template` | 에이전트 추출기 워커의 활성 양식 조회 | Required (JWT) |

라우터: `idt/src/api/routes/agent_builder_router.py` (`/{agent_id}/skills`와 같은 위치). DI는 `get_get_agent_document_template_use_case` placeholder + `main.py`의 `create_agent_document_template_factory()`로 override (기존 팩토리 튜플을 건드리지 않으려고 별도 함수로 분리).

### 4.2 처리 순서

1. `agent = agent_repo.find_by_id(agent_id)` → 없으면 **404** `Agent not found`
2. `VisibilityPolicy.can_edit(ctx)` 거짓 → **403** `양식 조회 권한이 없습니다`
3. 추출기 워커(`worker_type == "tool"` and `tool_id == "document_extractor"`)의 `tool_config.template_id` 없음 → **404** `Document template not found`
4. `template = template_repo.find_by_id(template_id)`; `None` 또는 `status != "active"` → **404** (같은 메시지)
5. 원작자 판정: `template.agent_id == agent.id`면 `origin_owner = agent.user_id`, 아니면 `origin = agent_repo.find_by_id(template.agent_id)`; 원 에이전트가 삭제됐으면 `origin_owner = None`
6. `TemplateSampleExposurePolicy.can_view_samples(viewer_user_id, origin_owner)` 거짓 → 모든 `sample_value = ""`, `samples_hidden = True`

### 4.3 Response (200)

```json
{
  "template_id": "7b1c…",
  "name": "여신 승인 신청서",
  "source_format": "docx",
  "html_skeleton": "<html>…{{borrower_name}}…</html>",
  "slots": [
    {"key": "borrower_name", "label": "차주명", "slot_type": "value", "description": "", "sample_value": "홍길동"}
  ],
  "samples_hidden": false,
  "is_inherited": false,
  "updated_at": "2026-11-07T09:12:00"
}
```

### 4.4 Error Responses

기존 agent_builder 라우터 관례(`HTTPException(detail=str)`)를 따른다.

| Status | detail | Cause |
|--------|--------|-------|
| 401 | (인증 공통) | 토큰 없음 |
| 403 | `양식 조회 권한이 없습니다` | 소유자 아님 |
| 404 | `Agent not found` | 에이전트 없음 |
| 404 | `Document template not found` | 추출기 워커 없음 / template_id 없음 / 삭제됨 |

---

## 5. UI/UX Design

### 5.1 Modal Layout (saved 모드)

```
┌ 문서추출기 — 양식 등록 ─────────────────────────────────┐
│ 저장된 양식                                              │
│ 여신 승인 신청서   [DOCX] [슬롯 6] [포크로 받은 양식]      │
│ 미리보기는 채울 위치 확인용이며 실제 서식과 다를 수 있습니다 │
│ ┌──────────── iframe (sandbox, 라벨 하이라이트) ───────┐ │
│ └──────────────────────────────────────────────────────┘ │
│ 자동화 슬롯 (6)                                          │
│  [값] 차주명      예: 홍길동                              │
│  [작성] 심사의견                                          │
│ (samples_hidden) 예시값은 양식을 만든 사용자에게만 보입니다 │
│ [새 파일로 교체]                                          │
├──────────────────────────────────────────────── [닫기] ┤
```

### 5.2 Modal 상태 전이

| 조건 | 초기 mode | 비고 |
|------|-----------|------|
| `draft` 있음 | upload | 드래프트 우선 (현재 동작) |
| `draft` 없음 + `savedTemplateId` 있음 | saved | 조회 로딩·오류는 SavedTemplateView가 표시 |
| 둘 다 없음 | upload | 기존 "양식 미등록" 안내 |

- saved → "새 파일로 교체" → upload (`FORM_TEMPLATE_REPLACE_NOTICE` 표시)
- upload + `draft` 없음 + `savedTemplateId` 있음 → "저장된 양식 보기" 버튼 → saved
- 모달을 닫으면 mode는 다음 열기 때 위 표로 다시 계산한다(모달이 `isOpen=false`에서 언마운트되므로 로컬 state 초기화로 충분).
- 조회 404·오류 시: SavedTemplateView에 "저장된 양식을 불러오지 못했습니다" + "새 파일로 교체" 버튼만 표시.

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `SavedTemplateView` (신규) | `idt_front/src/components/agent-builder/SavedTemplateView.tsx` | 이름·배지·안내·미리보기 iframe·슬롯 목록·교체 버튼. 데이터는 props로 받는다(쿼리는 상위) |
| `DocumentExtractorConfigModal` (수정) | 같은 폴더 | `savedTemplate` 쿼리 결과·mode state·전환 버튼, 제목은 기존 "문서추출기 — 양식 등록" 유지(기존 테스트·접근성 이름 보존) |
| `LeftConfigPanel` (수정) | 같은 폴더 | `useAgentDocumentTemplate` 호출, 배지·모달에 결과 전달 |
| `ExtractorSummaryBadge` (수정, LeftConfigPanel 내부) | 같은 파일 | 조회 성공 시 `✓ {name} · 슬롯 N · DOCX`, 아니면 기존 "✓ 양식 등록됨" |

쿼리는 LeftConfigPanel에서 한 번만 호출하고 결과를 배지·모달에 props로 내려 중복 요청을 막는다.

### 5.4 Page UI Checklist

#### 빌더 수정 화면 — 도구 목록

- [ ] Badge: 저장 양식 조회 성공 시 `✓ {양식 이름} · 슬롯 {N} · {DOCX|PDF}`
- [ ] Badge: 조회 중·실패 시 `✓ 양식 등록됨` (기존 문구)
- [ ] Badge: 드래프트가 있으면 기존 드래프트 배지(작성 중 / 확정됨) 우선

#### 문서추출기 설정 모달 — saved 모드

- [ ] Heading: "저장된 양식"
- [ ] Text: 양식 이름
- [ ] Badge: 포맷(DOCX/PDF), 슬롯 수, `is_inherited`일 때 "포크로 받은 양식"
- [ ] Notice: "미리보기는 채울 위치 확인용이며 실제 서식과 다를 수 있습니다"
- [ ] iframe: `title="저장된 양식 미리보기"`, `sandbox=""`, 슬롯 라벨 하이라이트, 컨테이너 폭 스케일
- [ ] List: 슬롯마다 유형 배지(값/작성)·라벨·예시값(있을 때만 `예: …`)
- [ ] Notice: `samples_hidden`일 때 "예시값은 양식을 만든 사용자에게만 보입니다"
- [ ] Button: "새 파일로 교체" → upload 모드
- [ ] Loading: "저장된 양식을 불러오는 중…"
- [ ] Error: "저장된 양식을 불러오지 못했습니다" + 교체 버튼

#### 문서추출기 설정 모달 — upload 모드 (저장 양식 있음)

- [ ] Notice: 기존 `FORM_TEMPLATE_REPLACE_NOTICE`
- [ ] Button: "저장된 양식 보기" (draft 없을 때만) → saved 모드

---

## 6. Error Handling

| 상황 | 백엔드 | 프론트 |
|------|--------|--------|
| 에이전트 없음 | 404 | 쿼리 오류 → 배지 폴백, 모달 오류 문구 |
| 소유자 아님 | 403 | 동일 (빌더 진입이 이미 막혀 정상 경로에선 발생 안 함) |
| 양식 없음·삭제 | 404 | 서비스가 404를 `null`로 변환 → 배지 폴백, 모달 오류 문구 |
| 원 에이전트 삭제(포크) | 200, 예시값 숨김 | 정상 표시 |

- 프론트 에러는 `authApiClient` 인터셉터가 던지는 `ApiError(message, status, code)`의 `status`로 판정한다(`err.response` 아님).
- `useQuery` `retry: false`(404 재시도 방지).
- 백엔드 로그: `request_id` 포함 start/done/fail (기존 유스케이스 관례).

---

## 7. Security Considerations

- [x] 권한: 엔드포인트에서 `VisibilityPolicy.can_edit` 검사 (읽기 권한이 느슨한 상세 조회와 분리)
- [x] 예시값: 양식 원작자가 아니면 서버에서 비운다. 프론트 숨김에 의존하지 않는다
- [x] `source_file_ref`(서버 경로)·`fill_hint` 비노출
- [x] 미리보기 HTML은 `sandbox=""` iframe으로만 렌더링 (스크립트·폼·동일 출처 차단)
- [ ] 잔여 위험(범위 밖): `tokenizeHtml`은 예시값의 **첫 출현만** 토큰화하므로, 같은 값이 원본에 두 번 이상 있으면 skeleton 본문에 원문이 남는다. 포크 사용자에게 skeleton 자체가 노출되므로 Report에 기록하고 별도 사이클 후보로 둔다

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | `TemplateSampleExposurePolicy` | pytest | Do |
| Unit | `GetAgentDocumentTemplateUseCase` (repo mock) | pytest | Do |
| API | 라우터 상태 코드·응답 형태 | pytest + TestClient (dependency override) | Do |
| Front Unit | service 404→null, hook enabled 조건 | Vitest + MSW | Do |
| Front Component | SavedTemplateView, Modal 모드 전환, 배지 | Vitest + RTL | Do |
| Manual | 실제 화면 확인 | Chrome DevTools MCP | Check |

### 8.2 Backend Test Scenarios

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| B1 | Policy | viewer == origin_owner | True |
| B2 | Policy | viewer != origin_owner / origin_owner None | False |
| B3 | UseCase | 소유자 + 자기 양식 | 200 데이터, sample 유지, `samples_hidden=False`, `is_inherited=False` |
| B4 | UseCase | 포크 소유자 + 원작자 양식 | sample 전부 "", `samples_hidden=True`, `is_inherited=True` |
| B5 | UseCase | 포크 + 원 에이전트 삭제 | sample 숨김, 정상 응답 |
| B6 | UseCase | 소유자 아님 | PermissionError |
| B7 | UseCase | 에이전트 없음 / 추출기 워커 없음 / template_id 없음 / status deleted | 각각 NotFound |
| B8 | UseCase | 응답에 `fill_hint`·`source_file_ref` 없음 | 필드 부재 |
| B9 | Router | 200 / 403 / 404 매핑, 인증 없음 401 | 상태 코드 |
| B10 | Router | 라우트 등록 확인 (`app.routes` 순회 금지 — wiki router-map 규칙, `url_path_for` 등 사용) | 등록됨 |

### 8.3 Frontend Test Scenarios

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| F1 | service | 200 응답 | 객체 반환 |
| F2 | service | 404 | `null` 반환 |
| F3 | hook | `agentId` 또는 `savedTemplateId` 없음, draft 있음 | 요청 안 함 |
| F4 | SavedTemplateView | 데이터 렌더 | 이름·포맷·슬롯 수·iframe title·슬롯 라벨 |
| F5 | SavedTemplateView | `samples_hidden` | 숨김 안내 표시, `예:` 없음 |
| F6 | SavedTemplateView | `is_inherited` | "포크로 받은 양식" 배지 |
| F7 | Modal | draft 없음 + saved | saved 모드 → 교체 클릭 → 업로드 input 표시 → "저장된 양식 보기"로 복귀 |
| F8 | Modal | draft 있음 | upload 모드(기존 패널) |
| F9 | Modal | 조회 오류 | 오류 문구 + 교체 버튼 |
| F10 | LeftConfigPanel | saved 조회 성공 | 배지 `✓ 이름 · 슬롯 N · DOCX` |
| F11 | 회귀 | 기존 `DocumentExtractorConfigModal.test.tsx`, `DocumentExtractorConfigPanel.test.tsx`, `LeftConfigPanel.test.tsx`, `DocumentsStep.test.tsx` | 통과 |

### 8.4 Manual Check

로컬 DB에 양식 등록된 에이전트로 `?edit` 진입 → 배지·모달 확인. 포크 계정으로 같은 확인(예시값 숨김). 화면 폭 375 / 1440.

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `TemplateSampleExposurePolicy` | Domain | `idt/src/domain/document_extractor/policies.py` (기존 파일에 추가) |
| `GetAgentDocumentTemplateUseCase` | Application | `idt/src/application/agent_builder/get_agent_document_template_use_case.py` (신규) |
| `AgentDocumentTemplateResponse`, `SavedTemplateSlot` | Application | `idt/src/application/agent_builder/schemas.py` |
| `TemplateNotFoundError` 등 예외 | Application | 유스케이스 파일 내 또는 기존 예외 모듈 (Do에서 기존 관례 확인) |
| 라우트 + DI placeholder | Interface | `idt/src/api/routes/agent_builder_router.py` |
| DI 배선 | Interface | `idt/src/api/main.py` (`create_agent_document_template_factory`) |
| 엔드포인트 상수 | Front infra | `idt_front/src/constants/api.ts` `AGENT_DOCUMENT_TEMPLATE` |
| 타입 | Front domain | `idt_front/src/types/documentExtractor.ts` |
| 서비스 | Front app | `idt_front/src/services/agentBuilderService.ts` `getDocumentTemplate` |
| 쿼리 키 | Front lib | `idt_front/src/lib/queryKeys.ts` `agentBuilder.documentTemplate(agentId)` |
| 훅 | Front app | `idt_front/src/hooks/useAgentBuilder.ts` `useAgentDocumentTemplate` |
| UI | Presentation | `SavedTemplateView.tsx`(신규), `DocumentExtractorConfigModal.tsx`, `LeftConfigPanel.tsx` |

쿼리 키를 `agentBuilder.all` 아래 두므로 기존 update 성공 시 무효화(`useAgentBuilder.ts`)로 교체 후 재조회가 자동으로 일어난다.

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 백엔드 레이어 | domain → application → api, 도메인은 외부 의존 금지 |
| 백엔드 로깅 | `request_id` 포함 start/done/fail |
| 프론트 상수 | 런타임 문구 상수는 `src/types/*.ts` (컴포넌트 파일 export 금지) |
| 프론트 스타일 | 디자인 토큰(`text-fg-subtle`, `rounded-xl`, `Badge`, `Button`) 사용. 기존 추출기 패널의 zinc 리터럴은 손대지 않음 |
| 서버 상태 | `useQuery` + `queryKeys` 팩토리 |
| TDD | 테스트 선작성 → 구현 |
| Design 참조 주석 | `# Design Ref: §4.2 — …` / `// Design Ref: §5.2 — …` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/domain/document_extractor/policies.py                (+ TemplateSampleExposurePolicy)
├── src/application/agent_builder/schemas.py                  (+ 응답 DTO)
├── src/application/agent_builder/get_agent_document_template_use_case.py  (신규)
├── src/api/routes/agent_builder_router.py                    (+ GET 라우트, DI placeholder)
├── src/api/main.py                                           (+ DI 배선)
└── tests/ (domain policy, application use case, api router)

idt_front/src/
├── constants/api.ts · types/documentExtractor.ts · lib/queryKeys.ts
├── services/agentBuilderService.ts · hooks/useAgentBuilder.ts
├── components/agent-builder/SavedTemplateView.tsx (+ test, 신규)
├── components/agent-builder/DocumentExtractorConfigModal.tsx (+ test 보강)
└── components/agent-builder/LeftConfigPanel.tsx (+ test 보강)
```

### 11.2 Implementation Order

1. [ ] Domain policy + 테스트 (B1–B2)
2. [ ] 응답 DTO + UseCase + 테스트 (B3–B8)
3. [ ] 라우트 + DI + 라우터 테스트 (B9–B10)
4. [ ] 프론트 상수·타입·서비스·쿼리 키·훅 + 테스트 (F1–F3)
5. [ ] SavedTemplateView + 테스트 (F4–F6)
6. [ ] Modal 모드 전환 + LeftConfigPanel 배지·쿼리 + 테스트 (F7–F10)
7. [ ] 회귀 (F11, 백엔드 agent_builder·document_extractor 묶음) + lint·type-check
8. [ ] 화면 확인 (§8.4)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 백엔드 조회 API | `module-1` | 정책·DTO·유스케이스·라우트·DI·테스트 (순서 1–3) | 20–25 |
| 프론트 데이터 계층 | `module-2` | 상수·타입·서비스·쿼리 키·훅·테스트 (순서 4) | 10–15 |
| 프론트 UI | `module-3` | SavedTemplateView·Modal·배지·테스트·회귀·화면 확인 (순서 5–8) | 25–30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` | 30–40 |
| Session 2 | Do | `--scope module-3` | 25–30 |
| Session 3 | Check + Report | 전체 | 20–30 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-08 | Initial draft — Option C 선택, 조회 키를 template_id로·예시값 판정을 양식 원작자 기준으로 변경 | 배상규 |
| 0.2 | 2026-11-09 | Do 반영: 모달 제목 기존 유지, 화면 문구 상수 SAVED_TEMPLATE_TEXT(types/documentExtractor.ts), 라벨·예시값 공백 접기 | 배상규 |
