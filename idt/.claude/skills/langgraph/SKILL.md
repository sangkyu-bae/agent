---
name: langgraph
description: >
  Use for LangChain/LangGraph-based AI agent and graph workflow development.
  Applies to any request involving StateGraph, node/edge design, multi-agent
  architecture, MCP tool integration, streaming, checkpointing, or LangSmith
  tracing. Examples: "build a LangGraph agent", "design a StateGraph",
  "set up multi-agent architecture", "connect MCP tools to LangGraph",
  "add checkpointing", "add conditional edges"
---

# LangGraph Development Skill

A condensed guide for building agents and workflows with LangGraph (Python).
Focused on core patterns and common pitfalls. For detailed API references,
fetch the URLs listed at the bottom as needed.

---

## Core Architecture Concepts

### State
- **Always define with TypedDict** — Pydantic models are supported but TypedDict is the default
- Use `Annotated[list, add_messages]` for message accumulation (prevents overwriting)
- Control how fields merge using **reducer functions**

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    current_step: str
    result: str | None
```

### Node
- Write as a **pure function**: `(state: State) -> dict` or `-> State`
- Return **only the fields that changed** as a dict — do NOT return the entire state
- Use `async def` for async nodes; call `.ainvoke()` on the graph accordingly

```python
def my_node(state: State) -> dict:
    messages = state["messages"]
    # return only changed fields
    return {"current_step": "done"}
```

### Edge
- **Regular edge**: `graph.add_edge("node_a", "node_b")` — always transitions
- **Conditional edge**: `graph.add_conditional_edges()` — branches based on function return value
- Import `END` and `START` from `langgraph.graph`

```python
def route(state: State) -> str:
    if state["result"]:
        return "end_node"
    return "retry_node"

graph.add_conditional_edges("check_node", route, {
    "end_node": "end_node",
    "retry_node": "retry_node"
})
```

---

## Basic Graph Setup Pattern

```python
from langgraph.graph import StateGraph, START, END

# 1. Create the graph builder
builder = StateGraph(State)

# 2. Add nodes
builder.add_node("node_name", node_function)

# 3. Connect edges
builder.add_edge(START, "node_name")
builder.add_edge("node_name", END)

# 4. Compile
graph = builder.compile()

# 5. Run
result = graph.invoke({"messages": [{"role": "user", "content": "hi"}]})
```

---

## ReAct Agent (Most Common Pattern)

```python
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

model = ChatAnthropic(model="claude-sonnet-4-20250514")
tools = [my_tool_1, my_tool_2]

# Simple case — use prebuilt
agent = create_react_agent(model, tools)
result = await agent.ainvoke({"messages": [("user", "your question")]})

# For customization — build manually with StateGraph
```

---

## MCP Tool Integration (langchain-mcp-adapters)

```bash
pip install langchain-mcp-adapters
```

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

# stdio transport (local MCP server)
async with MultiServerMCPClient({
    "my-server": {
        "command": "python",
        "args": ["my_mcp_server.py"],
        "transport": "stdio"
    }
}) as client:
    tools = await client.get_tools()
    agent = create_react_agent(model, tools)
    result = await agent.ainvoke({"messages": [("user", "do something")]})

# HTTP transport (remote MCP server)
async with MultiServerMCPClient({
    "remote-server": {
        "url": "http://localhost:8000/mcp",
        "transport": "streamable_http"
    }
}) as client:
    tools = await client.get_tools()
```

**Important notes**
- Always use `MultiServerMCPClient` inside an `async with` context manager
- Tool name conflicts are resolved by prefixing the server name
- The client manages the subprocess lifecycle for stdio servers

---

## Checkpointing (Conversation Memory / Human-in-the-loop)

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver  # for persistence

# In-memory (dev/testing)
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# Use thread_id to separate conversation sessions
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": [("user", "hello")]}, config=config)

# Human-in-the-loop — pause before a node
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["sensitive_node"]
)
```

---

## Streaming

```python
# Stream state updates
async for chunk in agent.astream(
    {"messages": [("user", "question")]},
    stream_mode="values"  # "updates" | "values" | "messages"
):
    print(chunk)

# Stream LLM tokens
async for event in agent.astream_events(input, version="v2"):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="")
```

---

## Multi-Agent Architecture

```python
# Supervisor pattern
from langgraph.graph import StateGraph

# Register each sub-agent as a node
builder.add_node("researcher", researcher_agent)
builder.add_node("writer", writer_agent)
builder.add_node("supervisor", supervisor_node)

# Supervisor decides the next agent
def supervisor_route(state):
    return state["next_agent"]  # "researcher" | "writer" | END

builder.add_conditional_edges("supervisor", supervisor_route)
```

---

## LangSmith Tracing Setup

```bash
# .env
LANGSMITH_API_KEY=your_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=my-project
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

```python
# Set directly in code
import os
os.environ["LANGSMITH_TRACING"] = "true"
```

---

## Common Mistakes & Pitfalls

| Mistake | Correct Approach |
|---|---|
| Returning entire state from a node | Return only changed fields as a dict |
| Accumulating messages without `add_messages` | Use `Annotated[list, add_messages]` |
| Calling `ainvoke` on a sync graph | Async graphs require `async def` nodes |
| Using MCP client outside context manager | Always use inside `async with` block |
| Using checkpointer without `thread_id` | Always include `thread_id` in config |
| Graph with no path to `END` | Connect last node to `END` explicitly |

---

## Reference URLs for Detailed Docs
> Fetch these URLs as needed for the latest API details

- **LangGraph full docs**: https://langchain-ai.github.io/langgraph/
- **LangGraph llms.txt** (AI-friendly condensed docs): https://langchain-ai.github.io/langgraph/llms.txt
- **MCP Adapters**: https://github.com/langchain-ai/langchain-mcp-adapters
- **LangChain llms.txt**: https://python.langchain.com/llms.txt
- **LangSmith tracing**: https://docs.smith.langchain.com/
- **Checkpointing guide**: https://langchain-ai.github.io/langgraph/concepts/persistence/
- **Multi-agent patterns**: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- **Human-in-the-loop**: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/