# worker-context-injection Design Document

> **Summary**: 워커 노드에 [에이전트 프롬프트 + 역할] 정적 블록을 주입하고, supervisor가 매 라우팅마다 작업 지시(task)를 내려보내며, MCP 도구 실행 직전 플레이스홀더 인자를 차단한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft
> **Planning Doc**: [worker-context-injection.plan.md](../../01-plan/features/worker-context-injection.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | supervisor만 에이전트 프롬프트를 보고, 워커는 못 봐서 도구 인자를 지어낸다 |
| **WHO** | P2(KB 운영자/에이전트 소유자) — 커스텀 에이전트를 만들어 MCP 도구를 붙여 쓰는 사용자 |
| **RISK** | 워커 프롬프트 확대에 따른 토큰 증가 / `SupervisorDecision` 스키마 변경이 기존 라우팅 품질에 주는 회귀 |
| **SUCCESS** | 재현 시나리오("현재 분기 리포트 작성해주세요")에서 example.com류 더미 URL 호출 0건, 워커 system_prompt에 에이전트 프롬프트·역할 포함 100% |
| **SCOPE** | M1 정적 컨텍스트 주입 → M2 동적 task 전달 → M3 환각 인자 가드·관측 |

---

## 1. Overview

### 1.1 Design Goals

1. 워커 react agent가 **자신이 속한 에이전트와 자신의 역할**을 알고 도구를 호출한다.
2. 워커가 **지금 수행할 작업**을 supervisor로부터 명시적으로 전달받는다 — 대화 원문에서 재추론하지 않는다.
3. 근거 없는 도구 인자는 **MCP 서버에 도달하기 전에** 차단되고, 차단 사실이 로그로 남는다.
4. 기존 동작(노드별 자체 프롬프트, 워커 출력 규약, 라우팅)에 회귀를 만들지 않는다.

### 1.2 Design Principles

- **유실 지점에서 고친다**: supervisor→worker 경계가 유실 지점이므로 그 경계에만 변경을 집중한다.
- **규칙은 domain, 실행은 infrastructure**: 플레이스홀더 판정 규칙은 순수 함수로 domain에 두고, 차단 실행만 어댑터가 한다.
- **덧붙이되 덮지 않는다**: 컨텍스트 블록은 기존 노드별 지시문 **앞**에만 붙이고 기존 문자열은 무변경.
- **부재 시 기존 동작**: `task`가 없거나 블록이 비면 변경 전과 동일하게 동작한다(모든 신규 경로에 폴백).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | **Option C: Pragmatic** |
|----------|:-:|:-:|:-:|
| **Approach** | 스키마 무변경, `reasoning` 재활용 | 전용 모듈·정책·가드 어댑터 DI 완전 분리 | domain 정책 1개 + 기존 렌더러 모듈 재사용 |
| **New Files** | 0 | 3 | 1 |
| **Modified Files** | 3 | 7 | 5 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 규칙이 infrastructure에 박혀 재발 | 변경 표면 넓어 회귀 위험 | react agent 경로에 집중 |
| **Plan 요구 충족** | FR-10 미충족 | 전부 | 전부 (function 노드 task는 out-of-scope 명시) |

**Selected**: **Option C — Pragmatic Balance**

**Rationale**: 문제의 MCP 워커는 전부 `create_agent` + `_wrap_worker` 경로(`workflow_compiler.py:456`, `1548`)에 있다. function 노드(search/analysis/document_*)는 이미 자체 프롬프트로 작업 맥락을 갖고 있어 동적 task의 한계효용이 낮은 반면, 그쪽까지 손대면 `search_pipeline`·차트 라우팅까지 검증 표면이 확대된다. 규칙(플레이스홀더 판정)은 B와 동일하게 domain으로 분리하되, 가드 어댑터 DI는 `MCPToolAdapter`가 이미 pydantic `BaseTool` 필드로 구성되는 구조라 과설계다.

### 2.1 Component Diagram

```
                      ┌──────────────────────────────────────────┐
                      │ WorkflowCompiler.compile                 │
                      │                                          │
  agent prompt ──┐    │  render_worker_context_block(            │
  worker.desc ───┼───▶│      agent_prompt, worker_desc, tools)   │
  tool names  ───┘    │            │                             │
                      │            ▼                             │
                      │  system_prompt = datetime + context       │
                      │                  + (노드별 기존 지시)      │
                      └────────────┬─────────────────────────────┘
                                   │ create_agent(...)
                                   ▼
   ┌───────────┐  task   ┌──────────────────┐  args   ┌──────────────────┐
   │supervisor │────────▶│ _wrap_worker     │────────▶│ MCPToolAdapter   │
   │  node     │         │ (react agent)    │         │  ._arun          │
   └───────────┘         └──────────────────┘         └────────┬─────────┘
    SupervisorDecision                                          │ 검증
      .task 신설                                                ▼
    state["worker_task"]                          ToolArgumentPolicy (domain)
                                                   │ placeholder?
                                            ┌──────┴──────┐
                                         차단(지시성      정상 →
                                          오류 반환)      MCP 서버 호출
```

### 2.2 Data Flow

```
[정적 경로 — 컴파일 시 1회]
workflow.supervisor_prompt + worker_def.description + bound tool names
  → render_worker_context_block()  (상한 절단 적용)
  → create_agent(system_prompt = datetime_block + context_block + 기존지시)

[동적 경로 — 매 턴]
supervisor LLM → SupervisorDecision{next, reasoning, answer, task}
  → state["worker_task"] = task
  → _wrap_worker: messages + HumanMessage("[현재 작업] " + task)  (무조건 append)
  → ensure_user_tail(...)  (prefill 방어, 이제 대부분 no-op)
  → worker react agent

[가드 경로 — 도구 호출 시]
worker LLM tool_call(arguments)
  → MCPToolAdapter._arun
  → ToolArgumentPolicy.find_placeholder(arguments)
      ├─ 발견 → logger.warning + 지시성 오류 문자열 반환 (서버 미호출)
      └─ 없음 → 기존 경로대로 session.call_tool
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `WorkflowCompiler` | `prompt_rendering.render_worker_context_block` | 정적 블록 조립 |
| `supervisor_node` | `SupervisorDecision` | `task` 구조화 출력 |
| `_wrap_worker` | `SupervisorState["worker_task"]` | 동적 지시 전달 |
| `MCPToolAdapter` | `domain.mcp.tool_argument_policy` | 인자 판정 (infrastructure → domain, 방향 준수) |

---

## 3. Data Model

### 3.1 상태·스키마 변경

```python
# src/application/agent_builder/supervisor_state.py
class SupervisorState(TypedDict):
    ...
    # worker-context-injection D3: supervisor가 선택한 워커에게 내리는 작업 지시.
    # 빈 문자열이면 _wrap_worker가 기존 범용 문구로 폴백한다.
    worker_task: str
```

```python
# src/application/agent_builder/supervisor_nodes.py
class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
    answer: str = Field(default="", description=...)
    # worker-context-injection D3
    task: str = Field(
        default="",
        description=(
            "선택한 워커가 지금 수행할 작업을 한국어 1~3문장으로 구체적으로 기술. "
            "대화에서 확인된 대상·기간·범위를 명시하고, 확인되지 않은 값은 "
            "지어내지 말고 '미확인'으로 남길 것. FINISH면 빈 문자열."
        ),
    )
```

`build_initial_state`에 `"worker_task": ""` 추가.

### 3.2 도메인 정책 (신규)

```python
# src/domain/mcp/tool_argument_policy.py  ← 신규 파일 (유일한 신규 파일)
"""MCP 도구 인자에 대한 도메인 규칙. 외부 의존성 없음."""

class ToolArgumentPolicy:
    """LLM이 지어낸 플레이스홀더 인자를 판정한다."""

    # 문서·예제에서만 쓰이는 예약 호스트. 실제 스크래핑 대상일 수 없다.
    PLACEHOLDER_HOSTS: frozenset[str] = frozenset({
        "example.com", "example.org", "example.net", "example.edu",
        "test.com", "sample.com", "your-domain.com", "yourdomain.com",
        "domain.com", "site.com", "url.com",
    })
    MAX_SCAN_DEPTH = 4   # 중첩 dict/list 순회 상한

    @staticmethod
    def find_placeholder(arguments: dict) -> str | None:
        """플레이스홀더 URL이 있으면 그 값을, 없으면 None을 반환한다."""

    @staticmethod
    def is_placeholder_url(value: str) -> bool:
        """문자열이 URL이고 호스트가 예약 호스트(또는 그 서브도메인)면 True."""
```

**판정 범위 결정**:
- 대상은 **도구 인자에 담긴 URL 문자열 값**뿐이다. MCP 서버 접속 주소(`server_config.url`)에는 적용하지 않는다 — 사내 `localhost` MCP 서버 운영을 막지 않기 위함.
- 그래서 `localhost` / `127.0.0.1`은 **PLACEHOLDER_HOSTS에 넣지 않는다**. Plan FR-07이 열거한 목록에서 이 두 항목은 오탐(사내 테스트 대상 스크래핑) 위험이 실익보다 커서 의도적으로 제외한다.
- 호스트 매칭은 정확 일치 + 서브도메인 일치(`www.example.com`)까지. 부분 문자열 매칭은 하지 않는다(`myexample.com` 오탐 방지).

---

## 4. API Specification

**변경 없음.** 이 기능은 에이전트 실행 내부 경로만 수정하며 HTTP 엔드포인트·요청/응답 스키마를 바꾸지 않는다. 따라서 `idt_front` 타입 동기화(`/api-contract-sync`)도 불필요하다.

### 4.1 내부 함수 계약 (신규/변경)

#### `render_worker_context_block()` — 신규

```python
# src/application/agent_run/prompt_rendering.py
MAX_AGENT_PROMPT_CHARS = 2000   # 상한 절단 (사용자 선택: 전문 + 상한)

def render_worker_context_block(
    agent_prompt: str,
    worker_description: str,
    tool_names: list[str],
) -> str:
    """워커 react agent의 system_prompt에 prepend할 컨텍스트 블록.

    Returns:
        블록 텍스트(끝에 '\\n---\\n\\n'). 모든 입력이 비면 '' (미배선 = 기존 동작).
    """
```

**출력 형태**:

```
[에이전트 지침]
{agent_prompt 전문, MAX_AGENT_PROMPT_CHARS 초과 시 절단 후 "…(생략)" 표기}

[당신의 역할]
{worker_description}

[사용 가능한 도구]
- {tool_name_1}
- {tool_name_2}

[도구 사용 규범]
도구 인자로 URL·식별자·날짜를 추측해서 만들지 마세요.
대화 내용, 이전 단계 결과, 이전 도구 응답에 근거가 없으면 도구를 호출하지 말고
무엇이 확인되지 않았는지 답변에 밝히세요.

---

```

- `agent_prompt`가 비면 `[에이전트 지침]` 절 생략, `worker_description`이 비면 `[당신의 역할]` 절 생략 — 나머지 절은 유지한다(도구 사용 규범은 항상 포함).
- 절단은 문자 수 기준. 절단 시 `"\n…(에이전트 지침 일부 생략)"`을 덧붙여 잘렸음을 LLM에 알린다.

#### `ToolArgumentPolicy.find_placeholder()` — 신규

| 입력 | 반환 |
|------|------|
| `{"url": "https://www.example.com/x"}` | `"https://www.example.com/x"` |
| `{"arguments": {"targets": ["https://example.org/a"]}}` | `"https://example.org/a"` |
| `{"url": "https://finance.naver.com/x"}` | `None` |
| `{"query": "example.com 관련 뉴스"}` | `None` (URL 값이 아닌 자연어) |
| `{}` / `None` | `None` |

#### `_build_worker_input()` — 신규 (구현 시 `_wrap_worker`에서 분리)

```python
def _build_worker_input(state: SupervisorState) -> list:
    """워커 react agent에 넘길 메시지 배열을 조립한다."""
    messages = list(state["messages"])
    task = state.get("worker_task", "")
    if task:
        messages.append(HumanMessage(content=f"[현재 작업]\n{task}"))
    return ensure_user_tail(messages, instruction=_FALLBACK_WORKER_INSTRUCTION)
```

`_wrap_worker`는 `{"messages": _build_worker_input(state)}`로 호출만 한다.

> **분리 사유**: 조립 로직을 `wrapped` 안에 두면 함수가 43줄이 되어 40줄 규칙을
> 넘는다. 모듈 레벨 순수 함수로 빼면 단위 테스트도 직접 가능하다.

> **핵심 설계 근거**: 기존 코드는 지시문을 `ensure_user_tail(instruction=...)`로만 넘겼는데, 첫 워커 호출 시 메시지 배열의 끝은 사용자 질문(HumanMessage)이라 `ensure_user_tail`이 no-op이 되어 **지시가 한 번도 전달되지 않았다**. 이것이 컨텍스트 유실의 네 번째 축이다. task는 별도 append로 보장하고, `ensure_user_tail`은 본래 역할인 prefill 방어(AI-last 방지)만 담당한다.

출력 규약(`worker-toolmessage-leak-fix`: 최종 `AIMessage(name=worker_id)` 1건)은 **무변경**.

---

## 5. UI/UX Design

**해당 없음** — 백엔드 전용 변경. 프론트엔드 파일 변경 0건.

---

## 6. Error Handling

### 6.1 차단·폴백 동작

| 상황 | 처리 | 사용자 영향 |
|------|------|-------------|
| 플레이스홀더 인자 탐지 | MCP 서버 **미호출**. `logger.warning("MCP tool call blocked (placeholder argument)")` 후 지시성 오류 문자열을 ToolMessage로 반환 | 없음 — 워커가 자기 교정 후 재시도하거나 부족한 정보를 답변에 밝힌다 |
| `task` 부재(강제 라우팅·구조화 출력 실패) | 기존 범용 문구로 폴백 | 변경 전과 동일 |
| `agent_prompt`·`description` 모두 빈 값 | 블록이 `[도구 사용 규범]`만 포함 | 소프트 가드는 유지 |
| 컨텍스트 블록 렌더 실패 | `""` 반환 + warning (degraded) — `render_datetime_block`과 동일 정책 | 변경 전과 동일 동작 |
| 워커 무한 재시도 | 별도 처리 없음. 기존 `IterationLimitPolicy` / `max_retries_per_worker`가 상한을 담당 | 반복 한도 도달 시 기존 안내 경로 |

### 6.2 차단 응답 문자열

```
[도구 호출이 차단되었습니다]
인자에 실재하지 않는 예시 주소가 포함되어 있습니다: {발견된 값}
추측한 URL로는 도구를 호출할 수 없습니다.
대화 내용이나 이전 단계 결과에서 확인된 대상만 사용하고,
확인된 대상이 없다면 도구를 다시 호출하지 말고
어떤 정보가 필요한지 답변에 밝히세요.
```

예외를 던지지 않는다 — `_arun`이 문자열을 반환하면 LangChain이 ToolMessage로 감싸 워커 react 루프에 되돌려주므로, 워커가 스스로 교정할 기회를 얻는다.

### 6.3 관측 로그 필드

```python
logger.warning(
    "MCP tool call blocked (placeholder argument)",
    request_id=self.request_id,
    tool_id=self.tool_id,
    server=self.server_config.name,
    tool=self.mcp_tool_name,
    reason="placeholder_url",
    blocked_value=<발견된 값>,
)
```

`log_extra` 딕셔너리를 재사용하고 `reason`/`blocked_value`만 추가한다. 예약 키(`name`, `message`, `args` 등)와 충돌하지 않는 이름만 사용한다(`fix-logger-reserved-key-conflict` 교훈).

---

## 7. Security Considerations

- [x] **SSRF 표면 축소**: LLM이 합성한 임의 URL이 그대로 MCP 서버로 흘러가던 경로에 검증 단계가 생긴다. (단, 이번 정책은 플레이스홀더 호스트만 막는 것이지 SSRF 방어 전체가 아니다 — 내부망 차단은 MCP 서버 책임으로 남는다.)
- [x] **프롬프트 노출**: 컨텍스트 블록에 들어가는 것은 에이전트 소유자가 작성한 `supervisor_prompt`와 워커 `description`뿐이며, 사용자 PII(`render_user_context_block`의 whitelist 대상)는 포함하지 않는다.
- [x] **로그 위생**: `blocked_value`는 LLM이 생성한 URL이므로 사용자 입력 원문이 아니다. 다만 사용자 발화가 URL에 섞일 가능성을 고려해 로그 레벨을 warning으로 두고 별도 외부 전송은 하지 않는다.
- [ ] 해당 없음: 인증/인가 변경, 암호화, HTTPS, Rate Limiting

---

## 8. Test Plan

> 백엔드 pytest 기준. Do 단계에서 **테스트 선작성 → 실패 확인 → 구현 → 통과** 사이클을 지킨다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: 단위 (domain) | `ToolArgumentPolicy` 판정 | pytest | Do |
| L1: 단위 (application) | `render_worker_context_block` 출력·절단·폴백 | pytest | Do |
| L2: 통합 (compiler) | 워커 `system_prompt` 조립 순서, 기존 노드 보존 | pytest + fake LLM/factory | Do |
| L2: 통합 (supervisor) | `task` 생성·상태 전달·폴백 | pytest | Do |
| L3: 시나리오 | 차단 경로 end-to-end (더미 URL → 서버 미호출) | pytest + mock MCP session | Do |
| 회귀 | 기존 agent_builder 스위트 전량 | pytest | Do/Check |

### 8.2 L1 — 단위 테스트 시나리오

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| 1 | `is_placeholder_url` | `https://www.example.com/a` | True |
| 2 | `is_placeholder_url` | `https://finance.naver.com/a` | False |
| 3 | `is_placeholder_url` | `https://myexample.com/a` | False (부분 일치 오탐 방지) |
| 4 | `is_placeholder_url` | `http://localhost:8080/x` | False (의도적 제외) |
| 5 | `find_placeholder` | 중첩 dict/list 안의 example.org URL | 해당 값 반환 |
| 6 | `find_placeholder` | `{"query": "example.com 뉴스"}` | None (URL 값 아님) |
| 7 | `find_placeholder` | `{}`, `None`, 깊이 5 이상 중첩 | None (예외 없음) |
| 8 | `render_worker_context_block` | 전 인자 정상 | 4개 절 + `---` 구분자 포함 |
| 9 | `render_worker_context_block` | `agent_prompt` 2000자 초과 | 절단 + 생략 표기 포함 |
| 10 | `render_worker_context_block` | 전 인자 빈 값 | `[도구 사용 규범]`만 포함 |

### 8.3 L2 — 통합 테스트 시나리오

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| 1 | 일반 tool 워커 컴파일 | MCP 워커 1개 | `create_agent` 호출의 `system_prompt`에 datetime → 컨텍스트 블록 순으로 포함 |
| 2 | wiki_read 워커 컴파일 | 목차 블록 존재 | 순서가 `datetime → context → wiki_toc → 기존 지시` 이고 기존 지시 문자열 무변경 |
| 3 | search / analysis / document_* 노드 | 기존 테스트 | 전량 통과 (동작 보존) |
| 4 | `supervisor_node` | LLM이 `task` 반환 | 반환 dict에 `worker_task` 포함 |
| 5 | `supervisor_node` | `task` 없음/빈 문자열 | `worker_task=""`, 그래프 정상 진행 |
| 6 | `_wrap_worker` | `worker_task` 있고 tail이 **user** | 워커 입력 마지막이 `[현재 작업]` HumanMessage (← 회귀 방지 핵심) |
| 7 | `_wrap_worker` | `worker_task` 없음 | 기존과 동일 동작 |
| 8 | `_wrap_worker` | 출력 | `AIMessage(name=worker_id)` 1건 규약 유지 |
| 9 | 강제 라우팅(`AttachmentRoutingHooks`) | `SupervisorDecision` 미경유 | `worker_task` 부재 폴백으로 정상 동작 |

### 8.4 L3 — 시나리오 테스트

| # | 시나리오 | 단계 | 성공 기준 |
|---|----------|------|-----------|
| 1 | 더미 URL 차단 | 워커가 `{"url": "https://www.example.com/financial-market-2026-09-03"}`로 호출 | `session.call_tool` 미호출, 차단 문자열 반환, warning 로그 1건 |
| 2 | 정상 호출 통과 | 실제 도메인 URL 인자 | `session.call_tool` 1회 호출, 기존 응답 그대로 |
| 3 | 차단 후 재시도 | 차단 → 워커가 인자 없이 재호출 | 무한 루프 없이 종료(반복 한도 내) |

### 8.5 검증 스킬

- `/verify-architecture` — domain이 infrastructure를 참조하지 않는지 (신규 `domain/mcp/tool_argument_policy.py`)
- `/verify-logging` — print 부재, 차단 로그 필드 규약
- `/verify-tdd` — 신규 모듈의 테스트 존재

---

## 9. Clean Architecture

### 9.1 Layer Structure (this feature)

| Layer | 파일 | 책임 |
|-------|------|------|
| **domain** | `src/domain/mcp/tool_argument_policy.py` (신규) | 플레이스홀더 판정 규칙 — 순수 함수, 외부 의존 없음 |
| **application** | `src/application/agent_run/prompt_rendering.py` | 컨텍스트 블록 렌더링 |
| **application** | `src/application/agent_builder/supervisor_nodes.py` | `task` 생성·전달 |
| **application** | `src/application/agent_builder/supervisor_state.py` | `worker_task` 상태 키 |
| **application** | `src/application/agent_builder/workflow_compiler.py` | 주입 지점·워커 진입 지시 |
| **infrastructure** | `src/infrastructure/mcp/tool_adapter.py` | 정책 호출 + 차단 실행 + 로그 |

### 9.2 Dependency Rules

```
application ──→ domain ←── infrastructure
     │
     └──→ infrastructure (ToolFactory 등 기존 경로)

신규 의존: infrastructure/mcp/tool_adapter.py ──→ domain/mcp/tool_argument_policy.py   ✅
금지 확인: domain/mcp/tool_argument_policy.py 는 아무것도 import 하지 않는다          ✅
```

### 9.3 파일별 변경 요약

| 파일 | 종류 | 변경 내용 | 예상 규모 |
|------|------|-----------|:---------:|
| `src/domain/mcp/tool_argument_policy.py` | 신규 | `ToolArgumentPolicy` | ~115줄 |
| `src/application/agent_run/prompt_rendering.py` | 수정 | `render_worker_context_block` + `_truncate_prompt` + 상수 | +61줄 |
| `src/application/agent_builder/supervisor_state.py` | 수정 | `worker_task` 키 | +5줄 |
| `src/application/agent_builder/supervisor_nodes.py` | 수정 | `SupervisorDecision.task`, 3개 반환 경로에 `worker_task`, `build_initial_state`, 결정 프롬프트 지시 | +26줄 |
| `src/application/agent_builder/workflow_compiler.py` | 수정 | 컨텍스트 블록 조립·주입(2개 분기), `_tool_names`, `_build_worker_input`, 폴백 상수 | +88줄 |
| `src/infrastructure/mcp/tool_adapter.py` | 수정 | `_arun` 진입부 검증·차단·로그 | +14줄 |

신규 1 / 수정 5 파일 (실측 +196 / -23줄, 테스트 제외).

**`worker_task` 초기화 지점 (구현 시 확정)** — 낡은 지시가 다음 턴으로 새지 않도록
세 경로 모두에서 비운다:

| 경로 | 처리 |
|------|------|
| 워커 라우팅 (`decision.next`가 유효 워커) | `worker_task = decision.task` |
| FINISH / 무효 워커 / 스킵 → `__end__` | `worker_task = ""` |
| 강제 라우팅 (`hooks.force_worker`) | `worker_task = ""` — `SupervisorDecision`을 거치지 않음 |
| supervisor LLM 실패 → `__end__` | 워커가 실행되지 않으므로 무해 (미설정) |

---

## 10. Coding Convention Reference

| 항목 | 적용 |
|------|------|
| 네이밍 | 함수 snake_case, 클래스 PascalCase, 상수 UPPER_SNAKE |
| 함수 길이 | 40줄 이하 — `find_placeholder`의 재귀 순회는 내부 헬퍼로 분리 |
| if 중첩 | 2단계 이하 — 조기 반환(guard clause) 사용 |
| 타입 | 전 공개 함수에 명시적 타입 힌트 |
| 하드코딩 | 플레이스홀더 목록·길이 상한은 정책 클래스 상수로만 정의, 매직 넘버 인라인 금지 |
| 로깅 | `print` 금지, 예외는 `exception=e`로 스택 트레이스 보존 |
| 주석 | 신규 결정 지점에 `# Design Ref: worker-context-injection §{절}` 표기 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/mcp/
│   └── tool_argument_policy.py          [신규]
├── application/
│   ├── agent_run/prompt_rendering.py    [수정]
│   └── agent_builder/
│       ├── supervisor_state.py          [수정]
│       ├── supervisor_nodes.py          [수정]
│       └── workflow_compiler.py         [수정]
└── infrastructure/mcp/
    └── tool_adapter.py                  [수정]

tests/
├── domain/mcp/test_tool_argument_policy.py            [신규]
├── application/agent_run/test_worker_context_block.py [신규]
├── application/agent_builder/
│   ├── test_worker_context_injection.py               [신규]
│   └── test_supervisor_worker_task.py                 [신규]
└── infrastructure/mcp/test_tool_adapter_guard.py      [신규]
```

### 11.2 Implementation Order

1. [ ] **M3-a** `ToolArgumentPolicy` 테스트 작성 → 실패 확인 → 구현 (의존 없어 먼저 착수 가능)
2. [ ] **M3-b** `MCPToolAdapter._arun` 차단·로그 테스트 → 구현
3. [ ] **M1-a** `render_worker_context_block` 테스트 → 구현
4. [ ] **M1-b** `WorkflowCompiler` 주입 테스트(일반/wiki 순서, 기존 노드 보존) → 구현
5. [ ] **M2-a** `SupervisorDecision.task` + `worker_task` 상태 + `build_initial_state` 테스트 → 구현
6. [ ] **M2-b** `_wrap_worker` task append 테스트(**tail이 user인 케이스 필수**) → 구현
7. [ ] 회귀: `pytest tests/application/agent_builder tests/infrastructure/mcp tests/domain/mcp`
8. [ ] 검증 스킬 3종 실행

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 환각 인자 가드 | `module-1` | `ToolArgumentPolicy` + `MCPToolAdapter._arun` 차단·로그 (M3) | 10-14 |
| 정적 컨텍스트 주입 | `module-2` | `render_worker_context_block` + `WorkflowCompiler` 주입 (M1) | 14-18 |
| 동적 작업 지시 | `module-3` | `SupervisorDecision.task` + `worker_task` + `_wrap_worker` (M2) | 12-16 |

> 순서 근거: module-1은 다른 모듈에 의존하지 않고 단독으로 "더미 URL이 서버에 도달하지 않는다"는 즉시 효과를 낸다. module-2가 재발 확률을 낮추고, module-3이 매 턴 정확도를 올린다.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 30-40 |
| Session 3 | Do | `--scope module-3` | 15-20 |
| Session 4 | Check + Report | 전체 | 25-35 |

---

## 12. Open Items (Do 착수 전 확인)

| # | 항목 | 영향 | 미확인 시 기본 처리 |
|---|------|------|---------------------|
| 1 | 문제의 스크래핑 MCP 도구가 URL을 인자로 직접 받는지 | `find_placeholder`의 탐색이 유효한지 | 인자 전체를 재귀 순회하므로 필드명을 몰라도 동작 — 기본 처리로 진행 가능 |
| 2 | 해당 에이전트의 워커 `description`이 채워져 있는지 | 정적 주입 효과 | 비어 있어도 에이전트 프롬프트 + 도구 규범은 주입됨. 빌더 측 작성 가이드는 별도 이슈 |
| 3 | `MAX_AGENT_PROMPT_CHARS = 2000`이 실제 에이전트 프롬프트 길이 분포에 맞는지 | 절단 빈도 | DB의 `supervisor_prompt` 길이 분포를 Do 착수 시 1회 확인해 조정 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 초안 — Option C 선택. `ensure_user_tail` no-op으로 인한 네 번째 유실 축 발견·반영 | 배상규 |
| 0.2 | 2026-09-03 | 구현 반영 — `_build_worker_input` 분리(40줄 규칙), `worker_task` 초기화 3경로 확정, `localhost`/`127.0.0.1` 차단 목록 제외 근거(§3.2), 파일별 실측 규모 | 배상규 |
