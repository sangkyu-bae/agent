---
name: langchain-middleware
description: Use this skill when the user asks to add, configure, or build features using LangChain middleware. Triggers include any mention of LangChain middleware by name (e.g. SummarizationMiddleware, HumanInTheLoopMiddleware, PIIMiddleware, ShellToolMiddleware, TodoListMiddleware, etc.), or requests like "LangChain 미들웨어로 ~~ 기능 만들어줘", "add summarization to my agent", "limit model calls", "add human approval step", "detect PII", "retry failed tools", or any feature that maps to a built-in LangChain middleware. Also trigger when user says "create_agent with middleware", asks to compose multiple middleware together, or wants to build custom middleware using hooks like before_model, after_model, wrap_model_call, wrap_tool_call, before_agent, after_agent, or dynamic_prompt.
---

LangChain (v1.0+) middleware lets you intercept and modify the core agent loop — before/after model calls and tool calls — without rewriting agent logic. This skill covers all built-in (prebuilt) middleware available in `langchain.agents.middleware`.

## Installation

```bash
pip install --pre -U langchain         # v1.0 alpha (middleware requires this)
pip install -U langchain-anthropic     # or langchain-openai, etc.
```

Requires **Python 3.10+**.

## Core Pattern

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SomeMiddleware

agent = create_agent(
    model="claude-sonnet-4-5-20250929",   # string or BaseChatModel
    tools=[your_tool],
    middleware=[SomeMiddleware(...)],
)
```

- `middleware` is a **list** — order matters
- Execution order: sequential **in** (before_model → modify_model_request), reverse **out** (after_model)
- `model` must be a string or `BaseChatModel` when using middleware

---

## All Built-in Middleware

### 1. SummarizationMiddleware
Summarizes old messages when approaching token limits.

```python
from langchain.agents.middleware import SummarizationMiddleware

SummarizationMiddleware(
    model="gpt-4.1-mini",           # model for generating summaries
    trigger=("tokens", 4000),       # when to summarize: ("tokens"|"messages"|"fraction", value)
    keep=("messages", 20),          # what to keep after: ("tokens"|"messages"|"fraction", value)
    # trigger=[("tokens", 3000), ("messages", 6)],  # OR logic: any condition triggers
)
```

**Use when**: long-running conversations, multi-turn dialogues exceeding context window.

---

### 2. HumanInTheLoopMiddleware
Pauses execution for human approval before tool calls.

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver

# Requires a checkpointer!
agent = create_agent(
    model="...",
    tools=[send_email_tool, read_email_tool],
    checkpointer=InMemorySaver(),
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "send_email_tool": {
                    "allowed_decisions": ["approve", "edit", "reject"],
                },
                "read_email_tool": False,   # never interrupt this tool
            }
        ),
    ],
)
```

**Use when**: high-stakes operations (DB writes, financial transactions), compliance workflows.  
**Required**: `checkpointer` must be set on the agent.

---

### 3. ModelCallLimitMiddleware
Limits total number of model (LLM) calls.

```python
from langchain.agents.middleware import ModelCallLimitMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ModelCallLimitMiddleware(
    thread_limit=10,        # max calls across all runs in a thread (needs checkpointer)
    run_limit=5,            # max calls per single invocation
    exit_behavior="end",    # "end" (graceful) or "error" (raise exception)
)
```

**Use when**: preventing runaway agents, cost control, testing within call budgets.

---

### 4. ToolCallLimitMiddleware
Limits tool call counts, globally or per-tool.

```python
from langchain.agents.middleware import ToolCallLimitMiddleware

# Global limit
ToolCallLimitMiddleware(thread_limit=20, run_limit=10)

# Per-tool limit
ToolCallLimitMiddleware(
    tool_name="search",
    thread_limit=5,
    run_limit=3,
    exit_behavior="continue",   # "continue" | "error" | "end"
)
```

`exit_behavior`:
- `"continue"` (default): block exceeded calls with error message, agent keeps going
- `"error"`: raise exception immediately
- `"end"`: stop with ToolMessage (single-tool only)

**Use when**: rate-limiting expensive APIs, protecting against tool loops.

---

### 5. ModelFallbackMiddleware
Auto-fallback to alternative models on primary model failure.

```python
from langchain.agents.middleware import ModelFallbackMiddleware

ModelFallbackMiddleware(
    "gpt-4.1-mini",                        # first fallback
    "claude-3-5-sonnet-20241022",          # second fallback
)
```

**Use when**: resilience against outages, cost optimization (fallback to cheaper), multi-provider redundancy.

---

### 6. PIIMiddleware
Detects and handles PII (Personally Identifiable Information).

```python
from langchain.agents.middleware import PIIMiddleware

# Built-in types: "email", "credit_card", "ip", "mac_address", "url"
PIIMiddleware("email", strategy="redact", apply_to_input=True)
PIIMiddleware("credit_card", strategy="mask", apply_to_input=True)

# strategy options:
# "redact"  → replace with [REDACTED_EMAIL]
# "mask"    → partially mask (e.g. ****-****-****-1234)
# "hash"    → deterministic hash
# "block"   → raise exception

# apply_to_input=True       check user messages before model call
# apply_to_output=False     check AI messages after model call
# apply_to_tool_results=False  check tool results
```

**Custom PII detector:**
```python
# Regex string
PIIMiddleware("api_key", detector=r"sk-[a-zA-Z0-9]{32}", strategy="block")

# Custom function
def detect_ssn(content: str) -> list[dict]:
    # return [{"text": "...", "start": 0, "end": 11}, ...]
    ...

PIIMiddleware("ssn", detector=detect_ssn, strategy="hash")
```

**Use when**: healthcare/finance compliance, customer service log sanitization.

---

### 7. TodoListMiddleware
Gives agent a `write_todos` tool + system prompt for task planning.

```python
from langchain.agents.middleware import TodoListMiddleware

TodoListMiddleware(
    system_prompt="Use write_todos to...",    # optional custom prompt
    tool_description="...",                   # optional custom tool description
)
```

**Use when**: complex multi-step tasks, long-running operations needing progress tracking.  
**Note**: Similar to how Claude Code manages its own task list.

---

### 8. LLMToolSelectorMiddleware
Uses a smaller LLM to pre-select relevant tools before the main model call.

```python
from langchain.agents.middleware import LLMToolSelectorMiddleware

LLMToolSelectorMiddleware(
    model="gpt-4.1-mini",           # cheaper model for selection
    max_tools=3,                    # max tools to pass to main model
    always_include=["search"],      # always include these (doesn't count toward max_tools)
)
```

**Use when**: agents with 10+ tools, reducing token usage, improving model focus.

---

### 9. ToolRetryMiddleware
Auto-retries failed tool calls with exponential backoff.

```python
from langchain.agents.middleware import ToolRetryMiddleware

ToolRetryMiddleware(
    max_retries=3,                          # default: 2
    backoff_factor=2.0,                     # exponential multiplier
    initial_delay=1.0,                      # seconds before first retry
    max_delay=60.0,                         # cap on delay growth
    jitter=True,                            # ±25% random jitter
    tools=["api_tool"],                     # None = all tools
    retry_on=(ConnectionError, TimeoutError),
    on_failure="return_message",            # "return_message" | "raise" | callable
)
```

**Use when**: transient API failures, network-dependent tools, building resilient agents.

---

### 10. ModelRetryMiddleware
Auto-retries failed model calls with exponential backoff.

```python
from langchain.agents.middleware import ModelRetryMiddleware

ModelRetryMiddleware(
    max_retries=3,
    backoff_factor=2.0,
    initial_delay=1.0,
    on_failure="continue",    # "continue" (return AIMessage) | "error" (raise)
    retry_on=(TimeoutError, ConnectionError),
)
```

---

### 11. LLMToolEmulator
Emulates tool execution with an LLM (for testing/prototyping).

```python
from langchain.agents.middleware import LLMToolEmulator

LLMToolEmulator()                              # emulate ALL tools
LLMToolEmulator(tools=["get_weather"])         # emulate specific tools only
LLMToolEmulator(model="claude-sonnet-4-5-20250929")  # custom model for emulation
```

**Use when**: testing agent behavior without real tools, prototyping before implementing tools.

---

### 12. ContextEditingMiddleware
Clears older tool outputs when context gets too large.

```python
from langchain.agents.middleware import ContextEditingMiddleware, ClearToolUsesEdit

ContextEditingMiddleware(
    edits=[
        ClearToolUsesEdit(
            trigger=100000,          # token count that triggers clearing
            keep=3,                  # preserve this many most recent tool results
            clear_at_least=0,        # min tokens to reclaim
            clear_tool_inputs=False, # also clear tool call arguments?
            exclude_tools=[],        # never clear these tools
            placeholder="[cleared]", # replacement text
        ),
    ],
    token_count_method="approximate",   # "approximate" | "model"
)
```

**Use when**: long conversations with many tool calls, reducing token costs.

---

### 13. ShellToolMiddleware
Exposes a persistent shell session to the agent.

```python
from langchain.agents.middleware import (
    ShellToolMiddleware,
    HostExecutionPolicy,
    DockerExecutionPolicy,
    RedactionRule,
)

# Host execution (default, trusted environments)
ShellToolMiddleware(
    workspace_root="/workspace",
    execution_policy=HostExecutionPolicy(),
    startup_commands=["pip install requests"],
    shutdown_commands=["cleanup.sh"],
    redaction_rules=[
        RedactionRule(pii_type="api_key", detector=r"sk-[a-zA-Z0-9]{32}"),
    ],
)

# Docker isolation
ShellToolMiddleware(
    workspace_root="/workspace",
    execution_policy=DockerExecutionPolicy(
        image="python:3.11-slim",
        command_timeout=60.0,
    ),
)
```

Execution policies:
- `HostExecutionPolicy`: full host access (use inside container/VM)
- `DockerExecutionPolicy`: isolated Docker container per run
- `CodexSandboxExecutionPolicy`: sandboxed via Codex CLI

**Limitation**: does NOT work with HumanInTheLoopMiddleware (no interrupt support yet).

---

### 14. FilesystemFileSearchMiddleware
Adds `glob_search` and `grep_search` tools to the agent.

```python
from langchain.agents.middleware import FilesystemFileSearchMiddleware

FilesystemFileSearchMiddleware(
    root_path="/workspace",    # required
    use_ripgrep=True,          # falls back to Python regex if unavailable
    max_file_size_mb=10,
)
```

**Use when**: code exploration, large codebases, finding files by pattern or content.

---

## Composing Multiple Middleware

```python
agent = create_agent(
    model="claude-sonnet-4-5-20250929",
    tools=[search_tool, db_tool],
    checkpointer=InMemorySaver(),
    middleware=[
        SummarizationMiddleware(model="gpt-4.1-mini", trigger=("tokens", 4000), keep=("messages", 20)),
        HumanInTheLoopMiddleware(interrupt_on={"db_tool": {"allowed_decisions": ["approve", "reject"]}}),
        ModelCallLimitMiddleware(run_limit=10),
        ToolRetryMiddleware(max_retries=3),
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
    ],
)
```

Execution order (entering model call): SummarizationMiddleware → HumanInTheLoop → ModelCallLimit → ToolRetry → PII  
Execution order (leaving model call): PII → ToolRetry → ModelCallLimit → HumanInTheLoop → Summarization (reverse)

---

## Quick Feature → Middleware Mapping

| 원하는 기능 | 사용할 Middleware |
|---|---|
| 긴 대화 컨텍스트 압축 | `SummarizationMiddleware` |
| 사람 승인 단계 추가 | `HumanInTheLoopMiddleware` |
| API 비용/호출 횟수 제한 | `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware` |
| 모델 장애 대비 fallback | `ModelFallbackMiddleware` |
| 개인정보(PII) 감지/마스킹 | `PIIMiddleware` |
| 복잡한 작업 TODO 관리 | `TodoListMiddleware` |
| 도구 많을 때 자동 선택 | `LLMToolSelectorMiddleware` |
| 실패한 tool 자동 재시도 | `ToolRetryMiddleware` |
| 실패한 model 자동 재시도 | `ModelRetryMiddleware` |
| 테스트용 tool 가짜 실행 | `LLMToolEmulator` |
| 오래된 tool 결과 정리 | `ContextEditingMiddleware` |
| 쉘 명령 실행 기능 | `ShellToolMiddleware` |
| 코드베이스 파일 검색 | `FilesystemFileSearchMiddleware` |

---

---

## Custom Middleware

빌트인 middleware로 부족할 때 직접 만드는 방법.

### Hook 종류

**Node-style** (특정 시점에 순서대로 실행):
| Hook | 실행 시점 |
|---|---|
| `before_agent` | 에이전트 시작 전 (invocation당 1회) |
| `before_model` | 모델 호출 전 (매번) |
| `after_model` | 모델 응답 후 (매번) |
| `after_agent` | 에이전트 완료 후 (invocation당 1회) |

**Wrap-style** (호출을 감싸서 제어):
| Hook | 용도 |
|---|---|
| `wrap_model_call` | 모델 호출 전후 제어 (retry, cache, fallback) |
| `wrap_tool_call` | tool 호출 전후 제어 (모니터링, 에러 핸들링) |

**Convenience**:
| Hook | 용도 |
|---|---|
| `@dynamic_prompt` | 런타임에 system prompt 동적 생성 |

---

### Decorator 방식 (단일 hook, 빠른 구현)

```python
from langchain.agents.middleware import before_model, after_model, AgentState
from langchain.messages import AIMessage
from langgraph.runtime import Runtime
from typing import Any

# before_model: 모델 호출 전 검사/수정
@before_model(can_jump_to=["end"])
def check_message_limit(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    if len(state["messages"]) >= 50:
        return {
            "messages": [AIMessage("Conversation limit reached.")],
            "jump_to": "end"   # 조기 종료
        }
    return None  # None 반환 = 계속 진행

# after_model: 모델 응답 후 로깅/검사
@after_model
def log_response(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    print(f"Model returned: {state['messages'][-1].content}")
    return None
```

```python
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from typing import Callable

# wrap_model_call: 모델 호출 자체를 감싸서 retry 등 구현
@wrap_model_call
def retry_model(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    for attempt in range(3):
        try:
            return handler(request)   # handler = 실제 모델 호출
        except Exception as e:
            if attempt == 2:
                raise
            print(f"Retry {attempt + 1}/3: {e}")
```

```python
from langchain.agents.middleware import wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langchain.messages import ToolMessage
from typing import Callable

# wrap_tool_call: tool 호출 모니터링
@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage],
) -> ToolMessage:
    print(f"Tool: {request.tool_call['name']}, Args: {request.tool_call['args']}")
    result = handler(request)
    print(f"Tool done")
    return result
```

**Decorator 사용 시기**: hook 1개, 설정 불필요, 빠른 프로토타이핑

---

### Class 방식 (복수 hook, 설정 필요)

```python
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage
from langgraph.runtime import Runtime
from typing import Any

class MessageLimitMiddleware(AgentMiddleware):
    def __init__(self, max_messages: int = 50):
        super().__init__()
        self.max_messages = max_messages

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        if len(state["messages"]) >= self.max_messages:
            return {
                "messages": [AIMessage("Limit reached.")],
                "jump_to": "end"
            }
        return None

    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        print(f"Response: {state['messages'][-1].content[:50]}")
        return None
```

**Class 사용 시기**: hook 2개 이상, init-time 설정 필요, 재사용성 중요

---

### Custom State Schema

middleware가 상태를 직접 추적해야 할 때.

```python
from langchain.agents.middleware import AgentMiddleware, AgentState
from typing_extensions import NotRequired
from typing import Any

# 커스텀 state 정의
class MyState(AgentState):
    model_call_count: NotRequired[int]
    user_id: NotRequired[str]

# Decorator 방식
from langchain.agents.middleware import before_model, after_model

@before_model(state_schema=MyState, can_jump_to=["end"])
def check_limit(state: MyState, runtime) -> dict[str, Any] | None:
    if state.get("model_call_count", 0) > 10:
        return {"jump_to": "end"}
    return None

@after_model(state_schema=MyState)
def count_calls(state: MyState, runtime) -> dict[str, Any] | None:
    return {"model_call_count": state.get("model_call_count", 0) + 1}

# Class 방식
class CallCounterMiddleware(AgentMiddleware[MyState]):
    state_schema = MyState

    def before_model(self, state: MyState, runtime) -> dict[str, Any] | None:
        if state.get("model_call_count", 0) > 10:
            return {"jump_to": "end"}
        return None

    def after_model(self, state: MyState, runtime) -> dict[str, Any] | None:
        return {"model_call_count": state.get("model_call_count", 0) + 1}

# 호출 시 커스텀 state 값 전달
result = agent.invoke({
    "messages": [HumanMessage("Hello")],
    "model_call_count": 0,
    "user_id": "user-123",
})
```

---

### Agent Jump (조기 종료/분기)

hook에서 `jump_to` 키를 반환하면 에이전트 흐름을 바꿀 수 있다.

```python
# 사용 가능한 jump targets:
# "end"   → 에이전트 실행 종료
# "tools" → tools 노드로 점프
# "model" → model 노드로 점프 (before_model 포함)

@after_model
@hook_config(can_jump_to=["end"])
def block_bad_content(state: AgentState, runtime) -> dict[str, Any] | None:
    last = state["messages"][-1]
    if "BLOCKED" in last.content:
        return {
            "messages": [AIMessage("Cannot respond to that.")],
            "jump_to": "end"
        }
    return None
```

**주의**: `jump_to`를 사용하려면 반드시 `@hook_config(can_jump_to=[...])` 또는 `@before_model(can_jump_to=[...])` 처럼 미리 선언해야 함.

---

### System Message 수정 (wrap_model_call 내에서)

```python
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.messages import SystemMessage
from typing import Callable

@wrap_model_call
def add_context(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    # content_blocks로 항상 접근 (string이든 list든 통일된 인터페이스)
    new_content = list(request.system_message.content_blocks) + [
        {"type": "text", "text": "추가 컨텍스트: 오늘 날짜는 ..."}
    ]
    new_system = SystemMessage(content=new_content)
    return handler(request.override(system_message=new_system))

# Anthropic prompt caching과 함께 사용
@wrap_model_call
def add_cached_context(request: ModelRequest, handler):
    new_content = list(request.system_message.content_blocks) + [
        {
            "type": "text",
            "text": "대용량 문서 내용...",
            "cache_control": {"type": "ephemeral"}   # 이 지점까지 캐시
        }
    ]
    return handler(request.override(system_message=SystemMessage(content=new_content)))
```

**규칙**: `system_message`는 항상 `SystemMessage` 객체. `content_blocks`로 접근해서 append하는 패턴 사용.

---

### 동적 모델 선택 (wrap_model_call)

```python
from langchain.chat_models import init_chat_model

complex_model = init_chat_model("gpt-4.1")
simple_model = init_chat_model("gpt-4.1-mini")

@wrap_model_call
def dynamic_model(request: ModelRequest, handler):
    model = complex_model if len(request.messages) > 10 else simple_model
    return handler(request.override(model=model))
```

---

### 동적 Tool 선택 (wrap_model_call)

```python
@wrap_model_call
def select_tools(request: ModelRequest, handler):
    # 상황에 따라 관련 tool만 필터링해서 전달
    relevant = [t for t in request.tools if is_relevant(t, request.state)]
    return handler(request.override(tools=relevant))

# 모든 tool은 create_agent에 등록해야 함 (override는 그 중 필터링)
agent = create_agent(model="gpt-4.1", tools=all_tools, middleware=[select_tools])
```

---

### Execution Order (다중 middleware 시)

```python
agent = create_agent(middleware=[mw1, mw2, mw3])
```

```
before_agent:   mw1 → mw2 → mw3
before_model:   mw1 → mw2 → mw3
wrap_model:     mw1( mw2( mw3( model ) ) )   # 중첩
after_model:    mw3 → mw2 → mw1              # 역순
after_agent:    mw3 → mw2 → mw1              # 역순
```

핵심: `before_*`는 순서대로, `after_*`는 역순, `wrap_*`는 중첩.

---

### Custom Middleware 빠른 선택 가이드

| 상황 | 방법 |
|---|---|
| hook 1개, 간단한 로직 | `@before_model` / `@after_model` decorator |
| hook 여러 개 or 설정값 필요 | `AgentMiddleware` class |
| 모델/tool 호출 자체를 제어 (retry, cache) | `@wrap_model_call` / `@wrap_tool_call` |
| 에이전트 흐름 변경 (조기 종료 등) | `jump_to` + `can_jump_to` |
| middleware간 데이터 공유 | Custom state schema (`AgentState` 확장) |
| system prompt 동적 추가 | `@wrap_model_call` + `request.override(system_message=...)` |
| 런타임 tool 필터링 | `@wrap_model_call` + `request.override(tools=...)` |

---

## Important Notes

- `HumanInTheLoopMiddleware`와 `ModelCallLimitMiddleware`의 `thread_limit`은 **반드시 `checkpointer` 필요**
- `ShellToolMiddleware`는 `HumanInTheLoopMiddleware`와 **함께 사용 불가** (interrupt 미지원)
- `model` 파라미터는 middleware 사용 시 반드시 **string 또는 BaseChatModel** (함수 불가)
- `prompt`는 string 또는 None만 허용