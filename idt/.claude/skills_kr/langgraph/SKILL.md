---
name: langgraph
description: >
  LangChain/LangGraph 기반 AI 에이전트 및 그래프 워크플로우 개발 시 사용.
  StateGraph, 노드/엣지 설계, 멀티에이전트 구조, MCP 툴 연동, 스트리밍,
  LangSmith 트레이싱 등 LangGraph 관련 작업이 포함된 모든 요청에 적용.
  예: "LangGraph로 에이전트 만들어줘", "StateGraph 설계", "멀티에이전트 구조 짜줘",
  "MCP 툴 LangGraph에 연결", "체크포인트 설정", "조건부 엣지 추가"
---

# LangGraph Development Skill

LangGraph(Python) 기반 에이전트/워크플로우 개발을 위한 압축 가이드.
핵심 패턴과 주의사항 위주로 구성. 세부 API는 하단 참고 URL을 fetch해서 확인.

---

## 핵심 아키텍처 개념

### State (상태)
- **반드시 TypedDict로 정의**. Pydantic 모델은 지원하나 TypedDict가 기본
- 메시지 누적은 `Annotated[list, add_messages]` 사용 (덮어쓰기 방지)
- 상태 필드는 **reducer 함수**로 병합 방식 제어

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    current_step: str
    result: str | None
```

### Node (노드)
- **순수 함수**로 작성: `(state: State) -> dict` 또는 `-> State`
- 반환값은 **변경할 필드만** dict로 반환 (전체 state 반환 X)
- 비동기는 `async def` 사용, 그래프도 `.ainvoke()` 호출

```python
def my_node(state: State) -> dict:
    # state 읽기
    messages = state["messages"]
    # 변경된 필드만 반환
    return {"current_step": "done"}
```

### Edge (엣지)
- **일반 엣지**: `graph.add_edge("node_a", "node_b")` — 항상 이동
- **조건부 엣지**: `graph.add_conditional_edges()` — 함수 반환값으로 분기
- `END` import: `from langgraph.graph import END, START`

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

## 그래프 기본 구성 패턴

```python
from langgraph.graph import StateGraph, START, END

# 1. 그래프 빌더 생성
builder = StateGraph(State)

# 2. 노드 추가
builder.add_node("node_name", node_function)

# 3. 엣지 연결
builder.add_edge(START, "node_name")
builder.add_edge("node_name", END)

# 4. 컴파일
graph = builder.compile()

# 5. 실행
result = graph.invoke({"messages": [{"role": "user", "content": "hi"}]})
```

---

## ReAct 에이전트 (가장 흔한 패턴)

```python
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

model = ChatAnthropic(model="claude-sonnet-4-20250514")
tools = [my_tool_1, my_tool_2]

# 간단한 경우 — prebuilt 사용
agent = create_react_agent(model, tools)
result = await agent.ainvoke({"messages": [("user", "질문")]})

# 커스터마이징 필요 시 — 직접 구성
```

---

## MCP 툴 연동 (langchain-mcp-adapters)

```bash
pip install langchain-mcp-adapters
```

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

# stdio 방식 (로컬 MCP 서버)
async with MultiServerMCPClient({
    "my-server": {
        "command": "python",
        "args": ["my_mcp_server.py"],
        "transport": "stdio"
    }
}) as client:
    tools = await client.get_tools()
    agent = create_react_agent(model, tools)
    result = await agent.ainvoke({"messages": [("user", "작업 요청")]})

# HTTP 방식 (원격 MCP 서버)
async with MultiServerMCPClient({
    "remote-server": {
        "url": "http://localhost:8000/mcp",
        "transport": "streamable_http"
    }
}) as client:
    tools = await client.get_tools()
```

**주의사항**
- `MultiServerMCPClient`는 반드시 `async with` 컨텍스트 매니저 사용
- 툴 이름 충돌 시 서버명이 prefix로 붙음
- stdio 서버는 프로세스 관리를 클라이언트가 담당

---

## 체크포인트 (대화 메모리 / Human-in-the-loop)

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver  # 영구 저장

# 인메모리 (개발/테스트용)
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# thread_id로 대화 세션 구분
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": [("user", "안녕")]}, config=config)

# Human-in-the-loop — interrupt 설정
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["sensitive_node"]  # 해당 노드 전에 일시정지
)
```

---

## 스트리밍

```python
# 토큰 단위 스트리밍
async for chunk in agent.astream(
    {"messages": [("user", "질문")]},
    stream_mode="values"  # "updates" | "values" | "messages"
):
    print(chunk)

# LLM 토큰 스트리밍
async for event in agent.astream_events(input, version="v2"):
    if event["event"] == "on_chat_model_stream":
        print(event["data"]["chunk"].content, end="")
```

---

## 멀티에이전트 구조

```python
# Supervisor 패턴
from langgraph.graph import StateGraph

# 각 서브에이전트를 노드로 등록
builder.add_node("researcher", researcher_agent)
builder.add_node("writer", writer_agent)
builder.add_node("supervisor", supervisor_node)

# supervisor가 다음 에이전트 결정
def supervisor_route(state):
    return state["next_agent"]  # "researcher" | "writer" | END

builder.add_conditional_edges("supervisor", supervisor_route)
```

---

## LangSmith 트레이싱 설정

```bash
# .env
LANGSMITH_API_KEY=your_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=my-project
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

```python
# 코드에서 직접 설정
import os
os.environ["LANGSMITH_TRACING"] = "true"
```

---

## 자주 하는 실수 & 주의사항

| 실수 | 올바른 방법 |
|---|---|
| 노드에서 state 전체 반환 | 변경된 필드만 dict로 반환 |
| `add_messages` 없이 메시지 누적 | `Annotated[list, add_messages]` 필수 |
| 동기 graph에서 `ainvoke` | 비동기 graph는 `async def` 노드 필요 |
| MCP client를 컨텍스트 밖에서 사용 | `async with` 블록 안에서만 사용 |
| thread_id 없이 체크포인트 사용 | config에 `thread_id` 반드시 포함 |
| `END` 없이 그래프 종료 | 마지막 노드에서 `END`로 엣지 연결 |

---

## 세부 문서 참고 URL
> 아래 URL은 필요 시 fetch해서 최신 API 확인

- **LangGraph 전체 문서**: https://langchain-ai.github.io/langgraph/
- **LangGraph llms.txt** (AI 친화적 압축 문서): https://langchain-ai.github.io/langgraph/llms.txt
- **MCP Adapters**: https://github.com/langchain-ai/langchain-mcp-adapters
- **LangChain llms.txt**: https://python.langchain.com/llms.txt
- **LangSmith 트레이싱**: https://docs.smith.langchain.com/
- **체크포인트 가이드**: https://langchain-ai.github.io/langgraph/concepts/persistence/
- **멀티에이전트 패턴**: https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- **Human-in-the-loop**: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/