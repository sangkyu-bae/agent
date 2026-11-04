# agent-run-tool-trace Design Document

> **Summary**: 실행 기록에서 "도구 실행 내역"을 조립하는 도메인 정책과 서비스를 근거 칩과 같은 구조로 두고, `ANSWER_COMPLETED`의 additive `tool_trace`와 세션 내역 API로 전달한다. 프론트는 답변 아래 접이식 내역과 호출별 드릴다운을 표시한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-03
> **Status**: Draft
> **Planning Doc**: [agent-run-tool-trace.plan.md](../../01-plan/features/agent-run-tool-trace.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 입력·결과는 WS로 전송되고 DB에도 저장되지만 화면에 표시되지 않는다. 사용자는 도구가 값을 실제로 가져왔는지 알 수 없다. |
| **WHO** | P2 KB 운영자·에이전트 소유자(주), P1 여신 심사역·P4 일반 사용자(보조). |
| **RISK** | 도구 결과에 포함된 개인정보·민감정보 노출, 타인 세션 열람, 2026-05에 raw JSON 노출을 제거한 결정(agent-chat-reasoning-display FR-04)과 같은 가독성 문제 재발, 실시간과 재진입 표시 불일치. |
| **SUCCESS** | 실시간과 재진입의 내역 순서·항목 일치, MCP 포함 실런 표시, 타인 세션 0건 노출, 답변 흐름 비차단, 기존 경로 회귀 0건. |
| **SCOPE** | M1 표시 정책(백엔드 도메인) → M2 세션 도구 내역 API → M3 실시간 경로 정리 → M4 프론트 접이식 내역·드릴다운 |

---

## 1. Overview

### 1.1 Design Goals

1. 실시간과 재진입이 **같은 서비스·같은 정책**을 지나 같은 내역을 만든다 (Plan R4 해소).
2. 새 수집·저장·마이그레이션 없이 `ai_tool_call`·`ai_run_step`만 읽는다.
3. 근거 칩(PR #86) 동작과 계약을 바꾸지 않는다.
4. 화면은 기본 접힘, 정리된 표시가 기본, 원문은 토글 뒤에 둔다.

### 1.2 Design Principles

- 근거 칩과 같은 모양: 도메인 순수 정책 → 애플리케이션 서비스 → 실시간 리더 포트 + 세션 API.
- 계약 확장은 additive (`conventions/additive-contract-extension.md`). `input_preview`·`output_preview`는 유지한다.
- 내역은 부가 정보다. 조회 실패는 흡수하고 답변·히스토리를 막지 않는다 (`backend/patterns/degradation-vs-failure-boundary.md`).
- 호출자 opt-in(기본 False). WS 경로만 켠다 (`run-agent-caller-optin-gating` 메모).

### 1.3 실데이터 확인 결과 (로컬 DB, 2026-11-03)

Plan R2·R7과 Design 가정을 실데이터로 확인했다. 아래 사실이 정책 규칙의 근거다.

| # | 사실 | 정책 반영 |
|---|------|----------|
| D1 | `result_summary`는 평문이거나 ToolMessage dump(`{"content": "...", "additional_kwargs": {}, ...}`)다. 1KB 절단으로 dump JSON이 깨진 행도 있다 | `unwrap_tool_summary` 재사용 + 절단 dump의 `", "additional_kwargs"` 이하 꼬리 제거 (§3.3 R-05) |
| D2 | MCP 인자는 `{"arguments": {...}}`로 한 겹 감싼 행과 평평한 행이 섞여 있다 | 단일 키 `arguments` 래퍼만 벗긴다 (R-04) |
| D3 | `status=SUCCESS`이지만 본문이 `Error executing tool ...`인 MCP 호출이 실재한다 (list_inquiries 4건) | 실패로 표시 (R-06) |
| D4 | `step_id`가 NULL인 호출이 있다 (tavily_search) | 정렬은 시각 폴백, 워커 라벨 없음 (R-02, R-08) |
| D5 | `ai_run_step`의 `output_summary`는 supervisor에서만 자연어 판단이다. 다른 노드는 `도구 호출 1회`, `tier=PASS ...`, `mode=on phone=1` 같은 내부 요약이다 | supervisor step만 추론 항목으로 쓴다 (R-01) |
| D6 | 런당 도구 호출 최대 15건 | 상한 기본 50 (config) |
| D7 | 도구 결과의 전화번호는 MCP 서버가 이미 `010-****-XXXX`로 마스킹해 돌려준다. 작성자 이름은 도구 결과와 최종 답변에 똑같이 나온다 | 답변보다 넓은 노출은 생기지 않는다. 마스킹은 저장값을 그대로 따른다 (§7) |
| D8 | `pii-masking-integration` 설계는 "사용자 화면·DB에 placeholder 0건"을 목표로 한다. 사용자는 원래 값을 보는 것이 정책이다 | 요청 사용자 본인 세션에 원래 값 표시는 정책과 일치 |
| D9 | `created_at`·`started_at`은 DATETIME(초 단위), 도구 호출 id는 uuid4다 | 같은 step·같은 초의 호출 순서는 id로 고정된다(실제 호출 순서와 다를 수 있음). 실시간·재진입은 같은 규칙이라 서로 일치한다 (§10 알려진 한계) |

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| 접근 | 실시간은 프론트가 WS preview 파싱, 백엔드는 세션 API만 | 근거·내역을 단일 "실행 증거" 로더로 통합 | 근거 칩 구조를 본뜬 별도 정책·서비스, 카탈로그 조회만 공유 |
| 실시간·재진입 일치 | ✗ (직렬화·이름이 다름) | ✓ | ✓ |
| 근거 칩 회귀 위험 | 없음 | 높음 (PR #86 코드 재구성) | 낮음 (카탈로그 조회 추출만) |
| 쿼리 수 | 적음 | 가장 적음 | 근거와 별도 조회 (런당 +2) |
| 신규/수정 파일 | 6 / 6 | 9 / 12 | 11 / 13 |
| **선택** | | | **✅ (사용자 선택)** |

### 2.1 Component Diagram

```
[ai_tool_call] [ai_run_step] [tool_catalog]
        │            │              │
        └──── AgentRunRepository ───┘   (find_tool_calls_by_runs / find_steps_by_runs 신규)
                     │
         RunToolTraceService ──uses── ToolTracePolicy (domain, 순수)
          │        └──uses── ToolCatalogLookup (application, 근거 서비스와 공유)
          │
  ┌───────┴────────────────────────┐
  │ 실시간                          │ 재진입
  SessionScopedRunToolTraceReader   GetSessionToolTracesUseCase
  (RunToolTraceReaderPort)           └─ SessionAnswerRunsResolver (근거 유스케이스와 공유)
  │                                  │
  RunAgentUseCase._attach_tool_trace GET /conversations/agents/{a}/sessions/{s}/tool-traces
  │  (include_tool_trace opt-in)     │
  WS agent_answer_completed           chatService.getAgentSessionToolTraces
     .data.tool_trace                 │
  │                                  useAgentSessionMessages (병합)
  useAgentRunStream.toolTrace         │
  └──── ChatPage updateMessage ── Message.toolTrace ── MessageBubble ── ToolTraceList
```

### 2.2 Data Flow

- **실시간**: 그래프 종료 → `final_answer` 완료 → `_attach_sources` → `_attach_tool_trace`(리더가 별도 DB 세션으로 런 1개 조립) → `ANSWER_COMPLETED.data.tool_trace` → 프론트 스트림 상태 → 완료 시 placeholder 메시지에 기록.
- **재진입**: 세션 메시지 조회 → (assistant, 직전 user) 쌍 → user 메시지별 마지막 런 → 소유 확인 → 런 묶음 일괄 조립 → 메시지 id별 응답 → 프론트가 메시지 id로 병합.
- 하단 "추론 진행" 패널은 기존 WS `agent_tool_*`·`agent_step_reasoning` 이벤트로 계속 동작한다 (무변경).

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ToolTracePolicy` | `entities.ToolCall`, `entities.AgentRunStep`, `source_policy.unwrap_tool_summary`, `MCP_ERROR_PREFIX` | 순수 변환 |
| `RunToolTraceService` | `AgentRunRepositoryInterface`, `ToolCatalogLookup`, `LoggerInterface` | 조회 + 실패 흡수 |
| `ToolCatalogLookup` | `ToolCatalogRepositoryInterface`, `MCPConnectionPolicy`, `parse_mcp_tool_id` | 런타임 이름 → 표시 이름·분류 |
| `GetSessionToolTracesUseCase` | `ConversationMessageRepository`, `AgentRunRepositoryInterface`, `RunToolTraceService` | 세션 일괄 조회 |

---

## 3. Data Model

### 3.1 도메인 타입 (`idt/src/domain/agent_run/tool_trace_policy.py`)

```python
class ToolTraceKind(StrEnum):      # wire 값 — 변경은 프론트 계약 변경
    REASONING = "reasoning"
    TOOL = "tool"

class ToolTraceStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"   # v0.2 Check G-01: 종료 기록 없는 STARTED

class ToolTraceSource(StrEnum):
    INTERNAL = "internal"
    MCP = "mcp"

@dataclass(frozen=True)
class ToolDisplayInfo:              # ToolCatalogLookup 산출물
    display_name: str
    source: ToolTraceSource
    requires_approval: bool
    category: Optional[str]
    tool_id: Optional[str]

@dataclass(frozen=True)
class ToolTraceItem:
    seq: int                         # 1부터, 표시 순서
    kind: ToolTraceKind
    label: str                       # 도구 표시 이름 / 추론은 "판단"
    worker: Optional[str] = None     # 서브에이전트 소속 라벨
    # reasoning 전용
    text: Optional[str] = None
    # tool 전용
    source: Optional[ToolTraceSource] = None
    status: Optional[ToolTraceStatus] = None
    requires_approval: bool = False
    duration_ms: Optional[int] = None
    input: Optional[dict] = None
    input_truncated: bool = False
    output: Optional[str] = None
    output_truncated: bool = False
    error: Optional[str] = None

    def to_payload(self) -> dict: ...  # None 키 제외, False 플래그 제외

@dataclass(frozen=True)
class ToolTrace:
    items: list[ToolTraceItem]
    omitted_count: int = 0           # 상한 초과로 잘린 항목 수

    @property
    def tool_count(self) -> int: ...  # kind=tool 개수 (FR-12 N)

@dataclass(frozen=True)
class ToolTraceEvidence:
    tool_calls: list[ToolCall]
    steps: list[AgentRunStep]
    tools: dict[str, ToolDisplayInfo]   # 런타임 이름 → 정보
```

### 3.2 `ToolCatalogLookup` (`idt/src/application/agent_run/tool_catalog_lookup.py`)

`RunSourcesService._mcp_tools`의 정방향 이름 계산을 추출해 공유한다.

- 입력: 도구 호출 목록. 출력: `dict[runtime_name, ToolDisplayInfo]`.
- MCP: `tool_catalog.list_active` → `parse_mcp_tool_id` → `MCPConnectionPolicy.build_tool_name(f"mcp_{server_id}_{tool_name}")` (기존 로직 그대로).
- 내부 도구: `tool_id = internal:<name>`이면 런타임 이름 `<name>`으로 매핑. **Do에서 `tavily_search`·`internal_document_search`·`wiki_read`의 카탈로그 tool_id를 실DB로 확인한다.**
- 카탈로그 조회 실패 → 빈 dict + warning. 근거 서비스는 이전과 같이 MCP 칩만 제외되고(fail-closed), 내역은 이름 폴백으로 계속 표시된다.
- 근거 서비스는 `ToolDisplayInfo`에서 `McpToolInfo`를 만들어 쓴다. `McpToolInfo`·`RunSourcePolicy` 시그니처는 바꾸지 않는다.

### 3.3 조립 규칙 (`ToolTracePolicy.build(evidence, *, max_items) -> ToolTrace`)

| ID | 규칙 |
|----|------|
| R-01 | 추론 항목 = `node_type == SUPERVISOR`이고 `output_summary`가 비어 있지 않은 step. 다른 노드 요약은 쓰지 않는다 (D5). 라벨 "판단". |
| R-02 | 정렬 키: 도구는 소속 step의 `(step_index, created_at, id)`, 추론은 `(step_index, started_at, "")`. `step_id`가 없거나 step을 못 찾는 도구는 `started_at <= created_at`인 마지막 step의 `step_index`를 쓴다(없으면 0). seq는 정렬 후 1부터. |
| R-03 | 도구 라벨: `tools[tool_name].display_name` → MCP 런타임 이름(`mcp_` 접두)이면 "MCP 도구" → 그 외 런타임 이름. UUID는 라벨에 나오지 않는다. `unnamed_tool`은 "도구". |
| R-04 | 입력: `arguments_json`이 `{"arguments": {...}}` 단일 키이면 안쪽 dict를 쓴다. `{"_truncated": true, "input": "..."}`이면 `input={"input": "..."}`, `input_truncated=True`. None이면 None. |
| R-05 | 결과: `unwrap_tool_summary(result_summary)`. 절단된 dump에서 `", "additional_kwargs"` 이후 꼬리가 남으면 잘라 낸다. `len(result_summary) >= 1024`이면 `output_truncated=True`. |
| R-06 | 상태: `status == "STARTED"` → `INCOMPLETE`(결과·오류 미표시, v0.2). 그 외 `status != "SUCCESS"` 또는 (MCP이고 결과가 `Error executing tool`로 시작) → `FAILED`. |
| R-07 | 실패 문구: `error_text` 또는 오류 본문의 첫 줄, 200자 상한. 실패 항목도 `input`은 싣는다. 실패 항목의 `output`은 비운다(오류 본문은 `error`로만). |
| R-08 | 워커 라벨: 도구·추론 step의 `depth >= 1`이면 `parent_step_id`를 따라 `depth == 0` 조상 step의 `node_name`을 정규화(`sub_agent_` 접두와 `_<숫자>` 접미 제거, `_`→공백). 조상을 못 찾거나 순환이면 None. 최상위(depth 0) 워커는 도구와 1:1이라 라벨을 달지 않는다. |
| R-09 | `requires_approval`은 카탈로그 값을 그대로 싣는다(승인 후 실행된 호출 표시용). 승인 대기로 실행되지 않은 호출은 `ai_tool_call`에 행이 없어 내역에 나오지 않는다(Plan FR-14의 "승인 대기" 상태는 표시하지 않음 — §10). |
| R-10 | 상한: 정렬 후 앞에서 `max_items`개. 나머지는 `omitted_count`. 도구가 0건이면 추론이 있어도 빈 `ToolTrace`(내역 미표시, FR-12). |

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/conversations/agents/{agent_id}/sessions/{session_id}/tool-traces` | assistant 메시지별 도구 실행 내역 | Required |
| WS | `/ws/agent/{run_id}` `agent_answer_completed.data.tool_trace` | 실시간 내역 (additive) | 기존 |

### 4.2 GET `.../sessions/{session_id}/tool-traces`

세션 근거 API(`get_session_sources`)와 같은 규칙을 쓴다.

- 토큰 사용자의 세션만 조회. 없는 세션·타인 세션·다른 에이전트 런은 빈 200.
- 쿼리 수: 메시지 1 + 런 1 + 도구 호출 1 + step 1 + 카탈로그 1. 메시지 수에 비례하지 않는다.
- `response_model_exclude_none=True`.

**Response (200):**
```json
{
  "session_id": "s-1",
  "items": [
    {
      "message_id": 812,
      "tool_trace": {
        "omitted_count": 0,
        "items": [
          { "seq": 1, "kind": "reasoning", "label": "판단",
            "text": "운영 배포 승인 코드는 위키에 있어 wiki_read_worker를 선택합니다." },
          { "seq": 2, "kind": "tool", "label": "위키 열람", "source": "internal",
            "status": "success", "duration_ms": 320,
            "input": { "article_id": "2b6a…" },
            "output": "[위키 문서: 배포 승인 절차]\n…" },
          { "seq": 3, "kind": "tool", "label": "고객 문의 목록", "source": "mcp",
            "status": "failed", "duration_ms": 41,
            "input": { "board": "loan", "limit": 1 },
            "error": "Error executing tool list_inquiries: 1 validation error for list_inquiriesArguments" }
        ]
      }
    }
  ]
}
```

- 도구 0건인 메시지는 `items`에 넣지 않는다.
- 응답 스키마 파일: `idt/src/interfaces/schemas/agent_run_response.py`에 `ToolTraceItemResponse`, `ToolTraceResponse`, `MessageToolTraceResponse`, `SessionToolTracesResponse` 추가(기존 타입 무변경).

### 4.3 WS `agent_answer_completed.data.tool_trace`

- 형태는 §4.2의 `tool_trace` 객체와 같다. 도구가 있을 때만 키를 싣는다(`sources`·`charts` 선례).
- 일반 완료 경로와 recursion limit 강등 경로 두 곳. prompt guard 차단 턴에는 싣지 않는다.
- `RunAgentUseCase.stream(..., include_tool_trace: bool = False)`, `ws_router`만 True.

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌ 상플AI ───────────────────────────────────────────┐
│ 답변 본문 (MarkdownRenderer)                        │
│ [차트]                                              │
│ [근거 칩: 문서 · 웹 · 위키 · MCP]                    │
│ ▸ 도구 실행 내역 (3)                    ← button     │
│   ┌──────────────────────────────────────────┐    │
│   │ 💡 판단  운영 배포 승인 코드는 위키에 …       │    │
│   │ ✓ 위키 열람        성공 · 320ms        ▸   │    │
│   │ ✓ 네이버 검색 MCP  성공 · 1.2s         ▾   │    │
│   │    입력   query: 여신 한도                    │    │
│   │    결과   { "items": [ … ] }   [원문 보기]    │    │
│   │           저장 한도로 일부만 표시됩니다         │    │
│   │ ✗ 고객 문의 목록 MCP  실패 · 41ms      ▸   │    │
│   │    [답변 작성자] ← 서브에이전트 워커 라벨       │    │
│   │ 외 2건은 표시하지 않았습니다 (omitted_count)    │    │
│   └──────────────────────────────────────────┘    │
│ 👍 👎                                               │
└───────────────────────────────────────────────────┘
```

### 5.2 User Flow

답변 완료 → 접힌 "도구 실행 내역 (N)" 확인 → 펼침 → 도구 행 펼침 → 입력·결과 확인 → (선택) 원문 보기 → 세션 재진입 시 같은 내역.

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ToolTraceList` | `idt_front/src/components/chat/ToolTraceList.tsx` | 접기/펼치기 헤더, 항목 목록, omitted 안내 |
| `ToolTraceEntry` | `idt_front/src/components/chat/ToolTraceEntry.tsx` | 추론 행 / 도구 행(상태·시간·워커), 도구 드릴다운(입력·결과·원문 토글·잘림·오류) |
| `toolTraceFormat` | `idt_front/src/utils/toolTraceFormat.ts` | `formatInputLines(input)`, `formatOutput(output)` → `{ text, isJson }`, `formatDuration(ms)` 순수 함수 |
| `sessionToolTraces` | `idt_front/src/utils/sessionToolTraces.ts` | 응답 → `Record<messageId, ToolTrace>`, 메시지 병합 |

### 5.4 Page UI Checklist

#### ChatPage — 답변별 도구 실행 내역

- [ ] 헤더 버튼: "도구 실행 내역 (N)", `aria-expanded`, 기본 접힘, N은 도구 수
- [ ] 도구 0건이면 헤더 미표시
- [ ] 추론 행: Lightbulb 아이콘 + "판단" + 자연어(`text-fg-muted`)
- [ ] 도구 행: 상태 아이콘 + 상태 텍스트(성공/실패) 병행, 라벨, 소요 시간, MCP는 "MCP" Badge, 워커 라벨 Badge
- [ ] `requires_approval`이면 "승인 후 실행" Badge
- [ ] 도구 행 펼침 버튼 `aria-expanded`, 키보드 조작
- [ ] 입력: `key: value` 줄 목록(중첩 값은 한 줄 JSON), 입력 없으면 "입력 없음"
- [ ] 결과: JSON이면 2칸 들여쓰기, 아니면 줄바꿈 보존 텍스트, `max-h-64 overflow-auto` 고정 폭(`font-mono text-xs`)
- [ ] "원문 보기" 토글: 입력은 `JSON.stringify(input)`, 결과는 받은 문자열 그대로
- [ ] `input_truncated`/`output_truncated` → "저장 한도로 일부만 표시됩니다"
- [ ] 실패: `error` 문구 표시(`text-danger` + "실패" 텍스트)
- [ ] `omitted_count > 0` → "외 N건은 표시하지 않았습니다"
- [ ] 모든 값은 텍스트 노드로만 렌더 (MarkdownRenderer·`dangerouslySetInnerHTML` 금지)
- [ ] 하단 "추론 진행" 패널 동작 불변
- [ ] 토큰·공통 컴포넌트(`Badge`, `cn`)만 사용, hex·`text-[Npx]` 금지

---

## 6. Error Handling

| 지점 | 실패 | 처리 |
|------|------|------|
| `RunToolTraceService` 기록 조회 | DB 예외 | warning(`exception=e`) + 빈 결과 |
| `ToolCatalogLookup` | 카탈로그 조회 예외 | warning + 빈 dict → 라벨 폴백(R-03) |
| 정책 단계 | 예상 밖 예외 | 유스케이스·리더에서 warning + 빈 결과 |
| 실시간 리더 | 세션 획득 실패 | warning + 키 미포함, 답변 정상 |
| 세션 API | 메시지 조회 실패 | 전파(5xx) — 근거 API와 동일 |
| 세션 API | 런·내역 조회 실패 | 빈 200 |
| 프론트 세션 내역 조회 | 4xx/5xx/네트워크 | `{}`로 흡수, 메시지는 정상 표시 |
| 프론트 `formatOutput` | JSON 파싱 실패(절단) | 텍스트로 표시 |

---

## 7. Security Considerations

- [x] 인증 필수, 토큰 사용자 세션만 (`user_id` + `agent_id` 이중 확인 — 근거 API 규칙 재사용)
- [x] 타인 세션은 빈 200 (존재 여부 비노출)
- [x] 입력 인자에 비밀값 없음: 도구 비밀은 `tool_config`·MCP 서버 헤더에 있고 `arguments_json`은 LLM이 만든 인자다 (실데이터 D2 표본 확인)
- [x] 노출 범위 ≤ 답변: 요청 사용자는 이미 같은 결과로 만든 답변을 받는다. MCP 서버 측 마스킹 값은 저장값 그대로 표시된다 (D7)
- [x] PII 정책 정합: 저장값만 읽는다(별도 원본 경로 없음). `pii-masking-integration` Check 때 `ai_tool_call.arguments_json`·`result_summary`에 placeholder가 남는지 확인 항목으로 넘긴다 (D8)
- [x] XSS: 모든 값 텍스트 렌더, 링크 자동 변환 없음
- [x] 실패 문구 200자 상한, 스택 트레이스 미포함(`error_text`는 `str(error)`라 스택 없음)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위 | `ToolTracePolicy` 규칙 R-01~R-10 | pytest | Do |
| 단위 | `ToolCatalogLookup`, `RunToolTraceService` 실패 흡수 | pytest + fake repo | Do |
| 회귀 | `RunSourcesService`·근거 정책 기존 테스트 무변경 통과 | pytest | Do |
| 계약 | `RunAgentUseCase` opt-in 기본 False, `ws_router`만 True (AST) | pytest | Do |
| L1 | 세션 API: 본인 200·타인 빈 200·미인증 401·쿼리 수 | TestClient | Do/Check |
| 동일성 | 같은 픽스처로 실시간 payload와 세션 API 응답의 `tool_trace` 동일 | pytest | Do |
| 단위 | `toolTraceFormat`, `sessionToolTraces` | Vitest | Do |
| 컴포넌트 | `ToolTraceList`/`ToolTraceEntry` 접기·펼치기·원문 토글·잘림·실패·omitted·텍스트 렌더 | RTL + user-event | Do |
| 훅 | `useAgentRunStream` `tool_trace` 보관, `useAgentSessionMessages` 병합·실패 흡수 | Vitest + MSW | Do |
| 실런 | 실 LLM + 실 MCP 1회(WS), 세션 재진입 확인 | TestClient WS + 화면 | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Test | Expected |
|---|----------|------|----------|
| 1 | GET tool-traces | 본인 세션, 도구 2건 | 200, `items[0].tool_trace.items` 순서·필드 |
| 2 | GET tool-traces | 타인 세션 | 200, `items: []` |
| 3 | GET tool-traces | 토큰 없음 | 401 |
| 4 | GET tool-traces | 도구 0건 세션 | 200, `items: []` |
| 5 | GET tool-traces | 저장소 예외 주입 | 200, `items: []`, warning 1건 |

### 8.3 L2: UI Action Test Scenarios

| # | Action | Expected |
|---|--------|----------|
| 1 | 헤더 클릭 | 목록 펼침, `aria-expanded=true` |
| 2 | 도구 행 클릭 | 입력 key: value, 결과 정리 표시 |
| 3 | 원문 보기 클릭 | 원문 문자열로 전환 |
| 4 | 실패 항목 펼침 | "실패" + 오류 문구, 결과 영역 없음 |
| 5 | `<script>` 포함 결과 | 텍스트로 표시, 실행 없음 |

### 8.4 L3: E2E Scenario

| # | Scenario | Success Criteria |
|---|----------|-----------------|
| 1 | MCP 도구가 있는 에이전트로 질문 → 답변 완료 → 내역 펼침 → 새로고침·세션 재진입 | 두 화면의 항목·순서 동일, MCP 라벨에 UUID 없음 |

### 8.5 Seed Data

| Entity | Count | Fields |
|--------|:-:|--------|
| ai_run + ai_run_step(supervisor 2, worker 2, sub-agent depth 1 1) | 1 | step_index, parent_step_id, output_summary |
| ai_tool_call | 4 | 성공·실패·`Error executing tool` 본문·`{"arguments":…}` 인자·절단 dump·step_id NULL |
| tool_catalog | 2 | MCP 1(이름 있음), internal 1 |

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ToolTracePolicy`, 타입 | Domain | `idt/src/domain/agent_run/tool_trace_policy.py` |
| `RunToolTraceReaderPort` | Domain | `idt/src/domain/agent_run/interfaces.py` |
| `find_steps_by_runs` 선언 | Domain | `idt/src/domain/agent_run/interfaces.py` |
| `ToolCatalogLookup` | Application | `idt/src/application/agent_run/tool_catalog_lookup.py` |
| `RunToolTraceService` | Application | `idt/src/application/agent_run/run_tool_trace.py` |
| `SessionAnswerRunsResolver` | Application | `idt/src/application/agent_run/session_answer_runs.py` (근거 유스케이스에서 추출) |
| `GetSessionToolTracesUseCase` | Application | `idt/src/application/agent_run/use_cases/get_session_tool_traces_use_case.py` |
| `SessionScopedRunToolTraceReader` | Infrastructure | `idt/src/infrastructure/agent_run/run_tool_trace_reader.py` |
| `find_steps_by_runs` 구현 | Infrastructure | `agent_run_repository.py` |
| 라우트·스키마 | Interface | `agent_run_router.py`, `agent_run_response.py` |
| DI | Composition | `idt/src/api/main.py` |

도메인 정책은 DB·LangChain을 import하지 않는다 (AST 경계 테스트 추가).

---

## 10. Coding Convention Reference

### 10.4 This Feature's Conventions

| Item | Convention |
|------|-----------|
| 백엔드 이름 | `ToolTrace*`, 서비스 `RunToolTraceService` |
| 프론트 이름 | `ToolTrace`, `ToolTraceItem` (types/toolTrace.ts), wire 값은 `as const` 객체 (`TOOL_TRACE_KIND`, `TOOL_TRACE_STATUS`) |
| config | `agent_run_tool_trace_max_items: int = 50` (`idt/src/config.py`). 소비 지점: `main.py`의 `_make_run_tool_trace_service` → `RunToolTraceService(max_items=…)` — docstring에 명기 |
| 로그 | `logger.warning(..., exception=e, request_id=...)` |
| 런타임 상수 | 컴포넌트 파일에서 export 금지 → `src/types/toolTrace.ts` |

### 알려진 한계 (Plan 대비 조정)

| 항목 | 내용 |
|------|------|
| 같은 초 순서 | 같은 step 안에서 같은 초에 기록된 호출은 id 순으로 고정된다. 실제 호출 순서와 다를 수 있으나 실시간·재진입은 일치한다 (D9). 정밀 순서는 마이그레이션이 필요해 범위 밖 |
| 승인 대기 | 실행되지 않은 승인 대기 호출은 기록이 없어 표시하지 않는다. Plan FR-14의 "승인 대기" 상태는 "승인 후 실행" 배지로 대체한다 |
| 일반 채팅 | 답변별 내역은 에이전트 경로만 (Plan §2.2) |
| 원문 보기 | Plan FR-13의 "저장된 문자열" 대신 R-04·R-05로 래퍼를 벗긴 문자열을 원문으로 보여 준다. 저장 형태(`{"content": …}` dump)는 사용자에게 의미가 없어서다. 정리 표시와 같으면 토글을 두지 않는다 (v0.2 Check G-04·G-05) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/agent_run/tool_trace_policy.py               (신규)
├── domain/agent_run/interfaces.py                      (수정: 포트·find_steps_by_runs)
├── application/agent_run/tool_catalog_lookup.py        (신규)
├── application/agent_run/run_tool_trace.py             (신규)
├── application/agent_run/session_answer_runs.py        (신규, 추출)
├── application/agent_run/run_sources.py                (수정: lookup 사용)
├── application/agent_run/use_cases/get_session_sources_use_case.py      (수정: 추출 함수 사용)
├── application/agent_run/use_cases/get_session_tool_traces_use_case.py  (신규)
├── application/agent_builder/run_agent_use_case.py     (수정: _attach_tool_trace, opt-in)
├── infrastructure/agent_run/run_tool_trace_reader.py   (신규)
├── infrastructure/persistence/repositories/agent_run_repository.py (수정)
├── interfaces/schemas/agent_run_response.py            (수정: 응답 타입 추가)
├── api/routes/agent_run_router.py                      (수정: 라우트)
├── api/routes/ws_router.py                             (수정: include_tool_trace=True)
├── api/main.py                                         (수정: DI)
└── config.py                                           (수정: max_items)

idt_front/src/
├── types/toolTrace.ts                                  (신규)
├── types/chat.ts                                       (수정: Message.toolTrace)
├── types/websocket.ts                                  (수정: tool_trace optional)
├── constants/api.ts                                    (수정)
├── services/chatService.ts                             (수정)
├── utils/toolTraceFormat.ts                            (신규)
├── utils/sessionToolTraces.ts                          (신규)
├── hooks/useAgentRunStream.ts                          (수정)
├── hooks/useChat.ts                                    (수정: 병합)
├── components/chat/ToolTraceList.tsx                   (신규)
├── components/chat/ToolTraceEntry.tsx                  (신규)
├── components/chat/MessageBubble.tsx                   (수정: 배치)
└── pages/ChatPage/index.tsx                            (수정: view·updateMessage)
```

### 11.2 Implementation Order

1. [ ] 도메인 타입·정책 + 단위 테스트 (Red→Green)
2. [ ] `ToolCatalogLookup` 추출 → 근거 서비스 전환, 근거 테스트 회귀 0 확인
3. [ ] `find_steps_by_runs` (인터페이스·구현·테스트)
4. [ ] `RunToolTraceService` + 실패 흡수 테스트
5. [ ] `SessionAnswerRunsResolver` 추출 → 근거 유스케이스 전환, 회귀 0
6. [ ] 세션 내역 유스케이스·스키마·라우트·DI + L1
7. [ ] 실시간 리더·`_attach_tool_trace`·opt-in·AST 계약 + 동일성 테스트
8. [ ] 실런 스모크 1회 (WS, 실 MCP) — module-3 완료 조건
9. [ ] 프론트 타입·서비스·유틸 + 테스트
10. [ ] 스트림 훅·세션 병합 + 테스트
11. [ ] 컴포넌트 + 테스트, MessageBubble·ChatPage 배선
12. [ ] 화면 확인 (375/768/1440), 세션 재진입 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:-:|
| 정책·조회 기반 | `module-1` | 도메인 정책, `ToolCatalogLookup` 추출, `find_steps_by_runs`, `RunToolTraceService` (순서 1~4) | 25-35 |
| 세션 API | `module-2` | 쌍 추출, 유스케이스, 스키마, 라우트, DI, L1 (순서 5~6) | 15-25 |
| 실시간 경로 | `module-3` | 리더, `_attach_tool_trace`, opt-in 계약, 동일성 테스트, 실런 (순서 7~8) | 15-25 |
| 프론트 | `module-4` | 타입·서비스·유틸·훅·컴포넌트·배선·화면 확인 (순서 9~12) | 30-40 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-:|
| 1 | Do | `--scope module-1` | 30 |
| 2 | Do | `--scope module-2,module-3` | 40 |
| 3 | Do | `--scope module-4` | 40 |
| 4 | Check + Report | 전체 | 30 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | 초안 — 설계안 C 선택, 실데이터 확인 D1~D9 반영 | 배상규 |
| 0.2 | 2026-11-04 | Check 반영 — `INCOMPLETE` 상태(G-01), 원문 토글 조건·표기(G-04·G-05), 연결 클래스명(G-06) | 배상규 |
