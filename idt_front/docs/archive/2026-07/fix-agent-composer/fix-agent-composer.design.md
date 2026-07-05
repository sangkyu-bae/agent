# fix-agent-composer Design Document

> **Summary**: Fix 에이전트 탭 — 채팅 → compose API(`current_config`/`history` 확장) → 초안 카드 [적용하기] → 좌측 폼 반영. 풀스택 설계.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-04
> **Status**: Draft
> **Planning Doc**: [fix-agent-composer.plan.md](../../01-plan/features/fix-agent-composer.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- compose API를 **하위호환**으로 확장 — `current_config`/`history` 미전송 시 기존 동작과 100% 동일
- 초안은 **[적용하기] 클릭 시에만** 폼에 반영 (자동 덮어쓰기 금지)
- 기존 서버 보정 파이프라인(환각 drop → MCP 매핑/병합 → 상한 clamp → coverage 재산정)을 **수정 없이 재사용**
- 채팅 UI는 `TestChatView` 패턴(로컬 state, 새 대화, Enter 전송)을 따르되 스트리밍 없음(단건 mutation)

### 1.2 Design Principles

- 프론트 레이어링: types → constants → services → hooks → components (CLAUDE.md 규칙)
- 백엔드 클린 아키텍처: application 스키마 확장 + composer 프롬프트 확장, domain 정책(`ComposePolicy`)에 절단 상수 추가
- 대화·초안은 서버 무저장(로컬 state) — compose 무저장 원칙 유지

---

## 2. Architecture

### 2.1 Data Flow

```
[FixAgentPanel 채팅 입력]
    │  user_request + current_config(폼 스냅샷) + history(최근 6턴)
    ▼
POST /api/v1/agents/compose  (agent_composer_router — 엔드포인트 불변)
    │
    ▼
ComposeAgentUseCase.execute()
    ├─ _resolve_llm_model_id()            (기존)
    ├─ _collect_candidates()              (기존: 내부 TOOL_REGISTRY + MCP 카탈로그/폴백)
    ├─ composer.compose(user_request, candidates,
    │                   current_config, history)   ← 확장
    │     └─ 시스템 프롬프트에 [현재 에이전트 설정] 블록 + 증분 수정 규칙 주입
    │        history를 messages 배열로 삽입 (system → history... → user)
    └─ _assemble_draft() → _to_response() (기존 보정/조립 그대로)
    │
    ▼
ComposeAgentDraftResponse (스키마 불변)
    │
    ▼
[ComposeDraftCard 렌더] ─ [적용하기] ─▶ AgentBuilderPage.handleApplyDraft()
                                          └─ form.name/systemPrompt/tools/model/temperature 반영
```

### 2.2 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| FixAgentPanel | useComposeAgent, ComposeDraftCard | 채팅 상태 관리 + compose 호출 |
| useComposeAgent | agentComposerService | TanStack Query mutation |
| agentComposerService | authClient, API_ENDPOINTS | 인증 포함 HTTP 호출 |
| AgentBuilderPage.handleApplyDraft | useLlmModels(models) | llm_model_id → model_name 역매핑 |
| AgentComposer(BE) | ComposePolicy | history/현재설정 절단 상수 |

---

## 3. Backend Design (idt/)

### 3.1 요청 스키마 확장 — `src/application/agent_composer/schemas.py`

```python
class ComposeCurrentConfig(BaseModel):
    """증분 수정용 현재 폼 스냅샷 (모두 optional — 빈 폼도 허용)."""
    name: str | None = Field(None, max_length=200)
    system_prompt: str | None = Field(None, max_length=4000)
    tool_ids: list[str] = Field(default_factory=list, max_length=10)
    llm_model_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)


class ComposeHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class ComposeAgentRequest(BaseModel):
    user_request: str = Field(..., min_length=1, max_length=1000)   # 기존
    name: str | None = Field(None, max_length=200)                  # 기존
    llm_model_id: str | None = None                                 # 기존
    current_config: ComposeCurrentConfig | None = None              # 신규
    history: list[ComposeHistoryTurn] | None = Field(None, max_length=20)  # 신규
```

**응답 스키마는 변경 없음** (`ComposeAgentDraftResponse` 그대로).

### 3.2 절단 정책 — `src/domain/agent_composer/policies.py` (`ComposePolicy` 확장)

| 상수 | 값 | 적용 |
|------|-----|------|
| `MAX_HISTORY_TURNS` | 6 | 최근 6턴만 유지 (`history[-6:]`) |
| `MAX_HISTORY_TURN_CHARS` | 500 | 턴당 content 500자 절단 |

- 절단은 **서버에서 무조건 수행** (프론트 절단에 의존하지 않음). `ComposePolicy.clamp_history(turns) -> list[...]` 정적 메서드 추가.

### 3.3 Composer 확장 — `src/application/agent_composer/composer.py`

`compose()` 시그니처 확장 (기본값으로 하위호환):

```python
async def compose(
    self,
    user_request: str,
    candidates: list[CandidateTool],
    request_id: str,
    current_config: ComposeCurrentConfig | None = None,
    history: list[ComposeHistoryTurn] | None = None,
) -> _ComposeOutput:
```

**시스템 프롬프트 확장** — `current_config`가 있을 때만 아래 블록을 기존 `_SYSTEM_PROMPT` 뒤에 덧붙인다:

```
[현재 에이전트 설정]
- 이름: {name or "(미정)"}
- 사용 중 도구: {tool_ids 나열 or "(없음)"}
- 시스템 프롬프트:
{system_prompt or "(없음)"}

[증분 수정 규칙]
- 위 설정은 사용자가 이미 구성한 상태입니다. 사용자의 요청에서 명시적으로
  요구된 변경만 적용하고, 나머지 설정(도구 구성, 프롬프트의 목적·방향)은 유지하세요.
- 유지할 기존 도구도 workers에 반드시 포함하세요 (누락하면 해제로 처리됩니다).
- system_prompt는 기존 내용을 바탕으로 요청된 변경만 반영해 다시 작성하세요.
```

**메시지 배열 구성** — history는 system과 최종 user 사이에 그대로 삽입:

```python
messages = [{"role": "system", "content": system}]
for t in clamped_history:
    messages.append({"role": t.role, "content": t.content})
messages.append({"role": "user", "content": user_request})
```

### 3.4 UseCase 배선 — `compose_agent_use_case.py`

- `execute()`에서 `ComposePolicy.clamp_history(request.history)` 후 `composer.compose(..., current_config=request.current_config, history=clamped)` 전달. **그 외 로직(후보 수집/보정/조립/응답) 변경 없음.**
- 기존 도구 유지 규칙의 안전망: current_config.tool_ids 중 후보에 없는 id(비활성 MCP 등)를 LLM이 workers에 넣어도 기존 `drop_unknown_tools`가 제거하고 notes에 기록 — 추가 코드 불필요.

### 3.5 Backend Test Cases (pytest, Red 먼저)

| # | 대상 | 케이스 |
|---|------|--------|
| B1 | schemas | `current_config`/`history` 없이 기존 요청 그대로 검증 통과 (하위호환) |
| B2 | schemas | history 21턴 → 422, turn content 2001자 → 422, role 오타 → 422 |
| B3 | ComposePolicy | `clamp_history`: 8턴 → 최근 6턴, 700자 content → 500자 절단 |
| B4 | composer | current_config 있으면 시스템 프롬프트에 `[현재 에이전트 설정]`/`[증분 수정 규칙]` 블록 포함, 없으면 미포함 |
| B5 | composer | history가 messages 배열에 system과 user 사이 순서대로 삽입 |
| B6 | use case | current_config 전달 시 composer 호출 인자 검증 (mock) + 기존 보정 파이프라인 회귀 |

---

## 4. Frontend Design (idt_front/)

### 4.1 타입 — `src/types/agentComposer.ts` (신규)

```typescript
export interface ComposeCurrentConfig {
  name: string | null;
  system_prompt: string | null;
  tool_ids: string[];
  llm_model_id: string | null;
  temperature: number | null;
}

export interface ComposeHistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ComposeAgentRequest {
  user_request: string;
  name?: string | null;
  llm_model_id?: string | null;
  current_config?: ComposeCurrentConfig | null;
  history?: ComposeHistoryTurn[] | null;
}

export interface ComposeMissingCapability {
  capability: string;
  reason: string;
  suggestion: string;
}

export interface ComposeWorkerInfo {
  tool_id: string;
  worker_id: string;
  description: string;
  sort_order: number;
  tool_config: Record<string, unknown> | null;
  worker_type?: string;
  ref_agent_id?: string | null;
  ref_agent_name?: string | null;
}

export type ComposeCoverage = 'full' | 'partial' | 'none';

export interface ComposeAgentDraftResponse {
  coverage: ComposeCoverage;
  name_suggestion: string;
  system_prompt: string;
  tool_ids: string[];
  workers: ComposeWorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  temperature: number;
  missing_capabilities: ComposeMissingCapability[];
  notes: string;
}

/** Fix 채팅 로컬 메시지 (서버 영속 아님). */
export interface FixChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;                       // user 입력 또는 assistant 요약 텍스트
  draft?: ComposeAgentDraftResponse;     // assistant 초안 카드 (없으면 텍스트/에러 버블)
  isError?: boolean;
  applied?: boolean;                     // [적용하기] 완료 표시
}
```

### 4.2 엔드포인트/서비스/훅

- `src/constants/api.ts`: `AGENT_COMPOSE: '/api/v1/agents/compose'` (AGENT_BUILDER_* 그룹 옆)
- `src/services/agentComposerService.ts`:
  ```typescript
  export const agentComposerService = {
    compose: async (data: ComposeAgentRequest): Promise<ComposeAgentDraftResponse> => {
      const res = await authClient.post(API_ENDPOINTS.AGENT_COMPOSE, data);
      return res.data;
    },
  };
  ```
- `src/hooks/useAgentComposer.ts`: `useComposeAgent()` — `useMutation({ mutationFn: agentComposerService.compose })`. 캐시 무효화 없음(무저장), queryKeys 등록 불필요(mutation 단독).

### 4.3 컴포넌트 — `src/components/agent-builder/fix/`

#### FixAgentPanel.tsx

```typescript
interface FixAgentPanelProps {
  mode: 'create' | 'edit';
  form: AgentBuilderFormData;          // current_config 스냅샷 소스
  models?: LlmModel[];                 // model_name ↔ id 매핑용
  onApplyDraft: (draft: ComposeAgentDraftResponse) => void;
}
```

**상태**: `messages: FixChatMessage[]`, `input: string`, mutation pending.

**레이아웃** (시안 `docs/img/fix_agent.png` + TestChatView 구조 준수):

```
┌──────────────────────────────────────────┐
│                         [🖊 새 대화]      │ ← shrink-0, 우측 정렬
├──────────────────────────────────────────┤
│  (빈 상태)                                │
│     ◯ 렌치 아이콘 (점선 원, violet)        │
│     "새 에이전트 수정"                     │ ← edit 모드: "{name} 수정"
│     "자연어로 에이전트를 수정하세요"        │
│     예시 프롬프트 3줄 (클릭 → input 삽입)  │
│  (대화 상태) 유저 버블 / 초안 카드 / 에러   │ ← flex:1, overflowY:auto
├──────────────────────────────────────────┤
│  [textarea: "에이전트를 어떻게 수정할지    │
│   설명하세요..."]              [전송 ↑]   │
│  Enter로 전송, Shift + Enter로 줄바꿈      │
└──────────────────────────────────────────┘
```

- 예시 프롬프트(시안 그대로): `"tavily 검색 도구 추가해줘"`, `"todo로 작업 관리할 수 있는 기능 추가해줘"`, `"시스템 프롬프트를 구조화된 프롬프트로 압축해 개선해줘"`
- 전송 시:
  1. user 메시지 push
  2. `current_config` 생성: `{ name: form.name || null, system_prompt: form.systemPrompt || null, tool_ids: form.tools, llm_model_id: models?.find(m => m.model_name === form.model)?.id ?? null, temperature: form.temperature }`
  3. `history` 생성: 기존 `messages`를 turn으로 변환(최근 6개, 아래 4.4 규칙), 지금 보낸 user 입력은 `user_request`로만 전달(중복 금지)
  4. mutation 실행 — pending 동안 입력/전송 비활성 + 로딩 인디케이터(bounce dots)
  5. 성공: assistant 메시지 push (`content`=요약 텍스트, `draft`=응답)
  6. 실패: `isError: true` 버블 push (422 detail 우선, 없으면 일반 메시지) — 대화 유지, 재전송 가능
- '새 대화': `messages`/`input` 초기화 (**폼은 유지**)
- 로딩 중 전송 차단(중복 방지), Enter/Shift+Enter는 TestChatView와 동일

#### 4.4 history 변환 규칙 (프론트)

- user 턴: `content` 그대로
- assistant 턴: **카드 JSON을 보내지 않는다.** 요약 텍스트로 변환:
  `초안(coverage: {coverage}) — 이름: {name_suggestion} / 도구: {tool_ids.join(', ') || '없음'}{applied ? ' (적용됨)' : ''}`
- 에러 버블(`isError`)은 history에서 제외
- 최근 6턴만 전송 (서버도 재절단하지만 payload 최소화)

#### ComposeDraftCard.tsx

```typescript
interface ComposeDraftCardProps {
  draft: ComposeAgentDraftResponse;
  mode: 'create' | 'edit';
  currentToolIds: string[];        // FR-10 edit 도구 변경 감지
  applied: boolean;
  onApply: () => void;
  onDismiss: () => void;
}
```

**렌더 구성** (rounded-2xl border 카드, 디자인 토큰 준수):

| 영역 | 내용 | 조건 |
|------|------|------|
| 헤더 | 📋 `name_suggestion` + coverage 뱃지 (full=emerald / partial=amber / none=red) | 항상 |
| 도구 | `tool_ids` 칩 목록 — `mcp_` 접두사는 MCP 뱃지(sky) 구분 | coverage ≠ none |
| 흐름 | `flow_hint` (12px, zinc-400) | 값 존재 시 |
| 프롬프트 | `system_prompt` 3줄 clamp + "더보기" 토글 | coverage ≠ none |
| 미커버 | ⚠ `missing_capabilities` 목록 (capability — reason, suggestion) | 배열 비어있지 않을 때 |
| 노트 | `notes` (11px, zinc-400) | 값 존재 시 |
| edit 경고 | "도구 변경은 수정 화면에서 저장되지 않습니다" (amber) | `mode==='edit' && draft.tool_ids와 currentToolIds 불일치` |
| 액션 | [적용하기](primary violet) [무시](ghost) → applied면 "✓ 적용됨" 뱃지로 치환 | coverage ≠ none |
| none 안내 | "현재 등록된 도구로는 요청을 수행할 수 없습니다" + missing/notes만, 액션 미노출 | coverage === none |

### 4.5 배선 변경

| 파일 | 변경 |
|------|------|
| `AgentTestPanel.tsx` | ① `fix` 탭 `enabled: true` ② props에 `form`, `models`, `onApplyDraft` 추가 ③ `tab === 'fix'`이면 `<FixAgentPanel/>` 렌더 (기본 fallback은 TestChatView 유지) |
| `StudioLayout.tsx` | `onApplyDraft` prop 추가, AgentTestPanel에 `form`/`models`/`onApplyDraft` 전달 |
| `AgentBuilderPage/index.tsx` | `handleApplyDraft(draft)` 구현 (아래 4.6) + StudioLayout에 전달 + MCP 필터 제거 (아래 4.7) |

### 4.6 폼 반영 매핑 — `handleApplyDraft`

| draft 필드 | form 필드 | 규칙 |
|-----------|-----------|------|
| `name_suggestion` | `name` | 항상 교체 (요청 name이 있으면 서버가 echo하므로 안전) |
| `system_prompt` | `systemPrompt` | 항상 교체 |
| `tool_ids` | `tools` | **전체 교체** + 부수효과 동기화: `RAG_TOOL_ID` 신규 포함 시 `toolConfigs[RAG_TOOL_ID] = DEFAULT_RAG_CONFIG`(기존 설정 있으면 유지), 제외 시 config 삭제; `DOCUMENT_EXTRACTOR_TOOL_ID` 제외 시 `documentExtractorDraft = null` (handleToolToggle과 동일 규칙) |
| `temperature` | `temperature` | 항상 교체 |
| `llm_model_id` | `model` | `models.find(m => m.id === draft.llm_model_id)?.model_name`으로 역매핑. **실패 시 model 미변경** (silent 금지 — 카드/토스트에 "모델 {id}를 찾을 수 없어 유지" 표시) |
| `workers`/`flow_hint` | — | 폼 미반영 (카드 표시 전용) |

- 단일 `setForm(prev => ...)` 호출로 원자적 반영.
- 적용 후 해당 메시지 `applied: true` 마킹.

### 4.7 MCP 필터 제거 (FR-08)

| 위치 | 현재 | 변경 |
|------|------|------|
| `AgentBuilderPage` handleSave (L164-169) | `form.tools`에서 `source === 'mcp'` 제외 후 전송 | 필터 삭제 — `form.tools` 그대로 전송 (`length > 0 ? tools : undefined` 유지) |
| `ToolPickerModal.tsx` (L75-84) | `!isEditMode && source === 'mcp'` → 선택 비활성 | `mcpDisabled` 로직 제거 (MCP 뱃지 표시는 유지) |
| 저장 422 처리 | 에러 메시지 다이얼로그 표시 (기존 `onError`) | 변경 없음 — 백엔드 한국어 메시지("등록되지 않았거나 비활성화된 MCP 도구입니다: …") 그대로 노출됨 확인만 |

### 4.8 Frontend Test Cases (Vitest + RTL + MSW, Red 먼저)

MSW: `handlers.ts`에 `http.post('*/api/v1/agents/compose', ...)` — 요청 body 캡처 가능하게 작성.

| # | 대상 | 케이스 |
|---|------|--------|
| F1 | agentComposerService | compose 호출 → 응답 파싱 (MSW) |
| F2 | useComposeAgent | mutation 성공/에러 상태 전이 (renderHook + createWrapper) |
| F3 | FixAgentPanel | 빈 상태: 아이콘/타이틀/예시 3개 렌더, 예시 클릭 → input 채움 |
| F4 | FixAgentPanel | 전송 → user 버블 + 초안 카드 렌더, 요청 body에 current_config(폼 스냅샷)/history 포함 검증 |
| F5 | FixAgentPanel | 2번째 전송 시 history에 이전 user+assistant 요약 포함, 에러 버블은 제외 |
| F6 | FixAgentPanel | '새 대화' → 메시지 초기화, pending 중 전송 차단 |
| F7 | ComposeDraftCard | coverage partial: 미커버 경고+적용 버튼 / none: 안내만·버튼 없음 / 적용 클릭 → onApply 호출 |
| F8 | ComposeDraftCard | edit 모드 + tool_ids 불일치 → 저장 제약 경고 노출 |
| F9 | AgentBuilderPage 통합 | 초안 적용 → 좌측 폼 name/prompt/tools/temperature 반영, llm_model_id 역매핑(미등록 id면 model 유지) |
| F10 | AgentBuilderPage 통합 | MCP tool_id 포함 저장 → 요청 body에 mcp_* 포함 (필터 제거 검증), 422 응답 → 에러 다이얼로그 메시지 |
| F11 | AgentTestPanel | fix 탭 활성화·클릭 시 FixAgentPanel 렌더 (기존 비활성 placeholder 테스트 갱신) |

---

## 5. Error Handling

| 상황 | HTTP | 프론트 처리 |
|------|------|------------|
| user_request 1~1000자 위반 | 422 | 전송 전 프론트 검증(빈 문자열 차단, 1000자 초과 시 절단+안내) + 에러 버블 |
| llm_model_id 미존재 | 422 | 에러 버블에 detail 표시 |
| history/current_config 검증 실패 | 422 | 프론트 규칙(6턴/요약 변환)상 정상 경로에서 미발생 — 에러 버블 폴백 |
| LLM 호출 실패 | 500 | 에러 버블 "초안 생성에 실패했습니다. 다시 시도해주세요." |
| 저장 시 비활성 MCP | 422 | 저장 결과 다이얼로그에 백엔드 메시지 그대로 |
| 인증 만료 | 401 | authClient 공통 갱신/리다이렉트 (기존 인터셉터) |

---

## 6. Security Considerations

- [x] compose/저장 모두 authClient(Bearer) 경유 — 신규 공개 엔드포인트 없음
- [x] current_config는 사용자 본인 폼 데이터만 전송 (타 사용자 데이터 미포함)
- [x] 프롬프트/입력은 서버 측 길이 제한으로 남용 방지 (1000자/4000자/500자×6턴)
- [x] 비밀값 없음 — 신규 환경변수 없음

---

## 7. Implementation Order

```
Phase A — 백엔드 (idt/)
  1. [ ] pytest B1~B3 작성(Red) → schemas.py + ComposePolicy.clamp_history 구현(Green)
  2. [ ] pytest B4~B5 작성(Red) → composer.py 프롬프트/메시지 확장(Green)
  3. [ ] pytest B6 작성(Red) → compose_agent_use_case.py 배선(Green) → 기존 테스트 회귀 확인

Phase B — 프론트 기반 (idt_front/)
  4. [ ] types/agentComposer.ts + constants/api.ts(AGENT_COMPOSE)
  5. [ ] MSW compose 핸들러 → F1~F2(Red) → agentComposerService + useAgentComposer(Green)

Phase C — 프론트 UI
  6. [ ] F7~F8(Red) → ComposeDraftCard(Green)
  7. [ ] F3~F6(Red) → FixAgentPanel(Green)
  8. [ ] F11(Red) → AgentTestPanel fix 탭 활성화 + StudioLayout 배선(Green)

Phase D — 폼 반영 + MCP
  9. [ ] F9(Red) → AgentBuilderPage.handleApplyDraft(Green)
  10. [ ] F10(Red) → MCP 필터 제거(handleSave + ToolPickerModal)(Green)

Phase E — 마무리
  11. [ ] docs/api/nl-agent-composer.md 확장분 갱신 (current_config/history)
  12. [ ] npm run type-check / lint / test:run(--pool=threads), idt pytest 전체
  13. [ ] 수동 E2E: 채팅→카드→적용→저장 1회
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-04 | Initial draft — Plan 결정사항 4건 반영, 백엔드/프론트 상세 설계 | 배상규 |
