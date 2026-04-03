# Task: Research Team Agent (연구 팀 에이전트)

> Task ID: AGENT-003
> 의존성: LOG-001, SEARCH-001, RET-001, COMP-001, QUERY-001, EVAL-001, LLM-001
> 최종 수정: 2026-03-04

---

## 1. 목적

LangGraph Supervisor 패턴으로 두 개의 전문 팀을 조율하는 Research Team 에이전트 구현.

- **Web Search Team**: Tavily 기반 실시간 웹 검색 (SEARCH-001)
- **Document Search Team**: Qdrant 기반 내부 문서 검색 (RET-001 + COMP-001)
- **Supervisor**: 질문 분석 후 팀 선택 및 병렬 실행, 결과 통합

---

## 2. 아키텍처 다이어그램

```
                    ┌─────────────────────────────┐
                    │        Supervisor            │
                    │  (질문 분석 → 팀 라우팅)      │
                    └──────┬──────────────┬────────┘
                           │              │
               ┌───────────┘              └───────────┐
               ▼                                      ▼
  ┌────────────────────────┐          ┌────────────────────────┐
  │    Web Search Team     │          │  Document Search Team  │
  │  ┌──────────────────┐  │          │  ┌──────────────────┐  │
  │  │  Query Rewrite   │  │          │  │  Query Rewrite   │  │
  │  │  (QUERY-001)     │  │          │  │  (QUERY-001)     │  │
  │  └────────┬─────────┘  │          │  └────────┬─────────┘  │
  │           ▼            │          │           ▼            │
  │  ┌──────────────────┐  │          │  ┌──────────────────┐  │
  │  │  Tavily Search   │  │          │  │  Vector Retrieve  │ │
  │  │  (SEARCH-001)    │  │          │  │  (RET-001)       │  │
  │  └────────┬─────────┘  │          │  └────────┬─────────┘  │
  │           ▼            │          │           ▼            │
  │  ┌──────────────────┐  │          │  ┌──────────────────┐  │
  │  │  Result Format   │  │          │  │  Compress Docs   │  │
  │  └──────────────────┘  │          │  │  (COMP-001)      │  │
  └────────────┬───────────┘          │  └──────────────────┘  │
               │                      └────────────┬───────────┘
               └──────────────┬───────────────────┘
                              ▼
                 ┌────────────────────────┐
                 │      Synthesizer       │
                 │  (결과 통합 + 답변 생성) │
                 │  (LLM-001)             │
                 └────────────┬───────────┘
                              ▼
                 ┌────────────────────────┐
                 │  Hallucination Check   │
                 │  (EVAL-001)            │
                 └────────────┬───────────┘
                              │
               ┌──────────────┴──────────────┐
               │ 할루시네이션 있음?             │
               │ YES → 재시도 (max 3)         │
               │ NO  → END                   │
               └─────────────────────────────┘
```

---

## 3. 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `ResearchTeamState`, `TeamRoutingPolicy`, `TeamType` | 상태, 라우팅 규칙, 팀 타입 정의 |
| application | `ResearchTeamWorkflow` | LangGraph 수퍼바이저 그래프 |
| application | `WebSearchTeam`, `DocumentSearchTeam` | 팀별 서브 워크플로우 |
| infrastructure | `SupervisorAdapter`, `SynthesizerAdapter` | LLM 어댑터 |

---

## 4. 도메인 설계

### 4.1 TeamType (Value Object)

```python
# domain/research_team/value_objects.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import List


class TeamType(str, Enum):
    """리서치 팀 타입"""
    WEB_SEARCH = "web_search"
    DOCUMENT_SEARCH = "document_search"
    BOTH = "both"


class TeamRoutingDecision(BaseModel):
    """수퍼바이저 라우팅 결정 VO"""

    teams: List[TeamType] = Field(description="활성화할 팀 목록")
    reason: str = Field(default="", description="라우팅 이유")


class TeamSearchResult(BaseModel):
    """팀별 검색 결과 VO"""

    team_type: TeamType
    query_used: str
    documents: List[str]
    source_count: int
```

### 4.2 ResearchTeamState (Graph State)

```python
# domain/research_team/state.py
from typing import TypedDict, Annotated, List, Dict
from operator import add


class ResearchTeamState(TypedDict):
    """Research Team LangGraph 상태"""

    # 입력
    question: str
    request_id: str

    # 수퍼바이저 결정
    active_teams: List[str]      # ["web_search", "document_search"]
    supervisor_reason: str

    # 팀별 결과 (add로 병렬 수집)
    web_search_docs: Annotated[List[str], add]
    document_search_docs: Annotated[List[str], add]

    # 쿼리 재작성 결과
    rewritten_query: str

    # 최종 결과
    synthesis: str               # 통합 답변
    hallucination_detected: bool
    retry_count: int

    # 팀별 메타데이터
    web_sources: List[Dict]      # URL, title 등
    doc_sources: List[Dict]      # chunk_id, doc_title 등
```

### 4.3 TeamRoutingPolicy (Domain Policy)

```python
# domain/research_team/policy.py


class TeamRoutingPolicy:
    """팀 라우팅 정책 (LLM 없는 휴리스틱 규칙)"""

    MAX_RETRY_COUNT = 3

    # 웹 검색 키워드
    WEB_SEARCH_KEYWORDS = [
        "최신", "오늘", "현재", "뉴스", "최근",
        "latest", "today", "current", "news", "recent",
    ]

    # 내부 문서 키워드
    DOCUMENT_KEYWORDS = [
        "정책", "규정", "내부", "문서", "보고서", "계약",
        "policy", "regulation", "internal", "document", "report",
    ]

    @staticmethod
    def suggest_teams(question: str) -> list[str]:
        """휴리스틱 기반 팀 제안 (최종은 Supervisor LLM이 결정)"""
        question_lower = question.lower()
        teams = []

        if any(kw in question_lower for kw in TeamRoutingPolicy.WEB_SEARCH_KEYWORDS):
            teams.append("web_search")

        if any(kw in question_lower for kw in TeamRoutingPolicy.DOCUMENT_KEYWORDS):
            teams.append("document_search")

        # 키워드 매칭 없으면 양쪽 모두
        return teams if teams else ["web_search", "document_search"]

    @staticmethod
    def can_retry(retry_count: int) -> bool:
        return retry_count < TeamRoutingPolicy.MAX_RETRY_COUNT

    @staticmethod
    def should_activate_web_search(active_teams: list[str]) -> bool:
        return "web_search" in active_teams

    @staticmethod
    def should_activate_document_search(active_teams: list[str]) -> bool:
        return "document_search" in active_teams
```

---

## 5. 인프라스트럭처 설계

### 5.1 SupervisorAdapter

```python
# infrastructure/research_team/supervisor_adapter.py
from pydantic import BaseModel, Field
from typing import List, Literal
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from domain.research_team.value_objects import TeamRoutingDecision, TeamType
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

SUPERVISOR_SYSTEM_PROMPT = """You are a research team supervisor.
Analyze the user's question and decide which research teams to activate.

## Available Teams
1. **web_search**: For current events, news, real-time information
2. **document_search**: For internal documents, policies, regulations, reports
3. **both**: When question needs both real-time + internal knowledge

## Decision Rules
- Time-sensitive (최신, 오늘, 뉴스) → web_search
- Internal knowledge (정책, 규정, 내부 문서) → document_search
- Complex analysis needing both → both
- Ambiguous → both

Return a JSON with: teams (list of "web_search" and/or "document_search"), reason."""

SUPERVISOR_HUMAN_TEMPLATE = "Question: {question}"


class SupervisorOutput(BaseModel):
    """수퍼바이저 LLM 출력"""
    teams: List[Literal["web_search", "document_search"]] = Field(
        description="활성화할 팀 목록"
    )
    reason: str = Field(description="팀 선택 이유")


class SupervisorAdapter:
    """수퍼바이저 LLM 어댑터"""

    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SUPERVISOR_SYSTEM_PROMPT),
            ("human", SUPERVISOR_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm.with_structured_output(SupervisorOutput)

    async def decide(self, question: str, request_id: str) -> TeamRoutingDecision:
        logger.info("Supervisor deciding teams", extra={"request_id": request_id})

        try:
            result: SupervisorOutput = await self._chain.ainvoke({"question": question})

            teams = [TeamType(t) for t in result.teams]

            logger.info(
                "Supervisor decision made",
                extra={"request_id": request_id, "teams": result.teams, "reason": result.reason}
            )
            return TeamRoutingDecision(teams=teams, reason=result.reason)

        except Exception as e:
            logger.error("Supervisor decision failed", extra={"request_id": request_id}, exc_info=True)
            raise
```

### 5.2 SynthesizerAdapter

```python
# infrastructure/research_team/synthesizer_adapter.py
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

SYNTHESIZER_SYSTEM_PROMPT = """You are a research synthesizer.
Combine search results from multiple teams into a coherent, accurate answer.

## Guidelines
- Integrate information from all provided sources
- Prioritize document search results for internal/policy questions
- Prioritize web search results for current events
- Cite sources when possible
- Be concise and accurate"""

SYNTHESIZER_HUMAN_TEMPLATE = """## Question
{question}

## Web Search Results
{web_results}

## Document Search Results
{doc_results}

Synthesize a comprehensive answer."""


class SynthesizerAdapter:
    """결과 통합 LLM 어댑터"""

    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.3):
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SYNTHESIZER_SYSTEM_PROMPT),
            ("human", SYNTHESIZER_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm

    async def synthesize(
        self,
        question: str,
        web_docs: list[str],
        document_docs: list[str],
        request_id: str,
    ) -> str:
        logger.info("Synthesizing results", extra={"request_id": request_id})

        try:
            result = await self._chain.ainvoke({
                "question": question,
                "web_results": "\n\n".join(web_docs) if web_docs else "없음",
                "doc_results": "\n\n".join(document_docs) if document_docs else "없음",
            })

            answer = result.content
            logger.info(
                "Synthesis completed",
                extra={"request_id": request_id, "answer_length": len(answer)}
            )
            return answer

        except Exception as e:
            logger.error("Synthesis failed", extra={"request_id": request_id}, exc_info=True)
            raise
```

---

## 6. Application 설계 (LangGraph Workflow)

### 6.1 WebSearchTeam (서브 워크플로우)

```python
# application/research_team/web_search_team.py
from application.query_rewrite.use_case import QueryRewriterUseCase
from application.web_search.use_case import WebSearchUseCase
from domain.research_team.state import ResearchTeamState
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class WebSearchTeam:
    """웹 검색 팀 (SEARCH-001 + QUERY-001 사용)"""

    def __init__(
        self,
        web_search_use_case: WebSearchUseCase,
        query_rewriter_use_case: QueryRewriterUseCase,
    ):
        self._web_search = web_search_use_case
        self._query_rewriter = query_rewriter_use_case

    async def run(self, state: ResearchTeamState) -> dict:
        """웹 검색 팀 실행 노드"""
        question = state.get("rewritten_query") or state["question"]
        request_id = state["request_id"]

        logger.info("WebSearchTeam started", extra={"request_id": request_id})

        # 쿼리 재작성 (QUERY-001)
        rewrite_result = await self._query_rewriter.rewrite(question, request_id)
        optimized_query = rewrite_result.rewritten_query

        # 웹 검색 (SEARCH-001)
        search_result = self._web_search.search(optimized_query, request_id)

        documents = [
            f"[Web] {item.title}\nURL: {item.url}\n{item.content}"
            for item in search_result.results
        ]

        web_sources = [
            {"title": item.title, "url": item.url}
            for item in search_result.results
        ]

        logger.info(
            "WebSearchTeam completed",
            extra={"request_id": request_id, "doc_count": len(documents)}
        )

        return {
            "web_search_docs": documents,
            "web_sources": web_sources,
        }
```

### 6.2 DocumentSearchTeam (서브 워크플로우)

```python
# application/research_team/document_search_team.py
from application.query_rewrite.use_case import QueryRewriterUseCase
from application.retrieval.retrieval_use_case import RetrievalUseCase
from domain.research_team.state import ResearchTeamState
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class DocumentSearchTeam:
    """문서 검색 팀 (RET-001 + COMP-001 + QUERY-001 사용)"""

    def __init__(
        self,
        retrieval_use_case: RetrievalUseCase,
        query_rewriter_use_case: QueryRewriterUseCase,
    ):
        self._retrieval = retrieval_use_case
        self._query_rewriter = query_rewriter_use_case

    async def run(self, state: ResearchTeamState) -> dict:
        """문서 검색 팀 실행 노드"""
        question = state.get("rewritten_query") or state["question"]
        request_id = state["request_id"]

        logger.info("DocumentSearchTeam started", extra={"request_id": request_id})

        # 쿼리 재작성 (QUERY-001)
        rewrite_result = await self._query_rewriter.rewrite(question, request_id)
        optimized_query = rewrite_result.rewritten_query

        # 벡터 검색 + 압축 (RET-001 + COMP-001)
        retrieval_result = await self._retrieval.search(
            query=optimized_query,
            request_id=request_id,
            use_compression=True,
            use_parent_context=True,
        )

        documents = [
            f"[Doc] {doc.content}"
            for doc in retrieval_result.documents
        ]

        doc_sources = [
            {"chunk_id": doc.chunk_id, "doc_title": doc.metadata.get("title", "")}
            for doc in retrieval_result.documents
        ]

        logger.info(
            "DocumentSearchTeam completed",
            extra={"request_id": request_id, "doc_count": len(documents)}
        )

        return {
            "document_search_docs": documents,
            "doc_sources": doc_sources,
        }
```

### 6.3 ResearchTeamWorkflow (Supervisor Graph)

```python
# application/research_team/workflow.py
from langgraph.graph import StateGraph, END

from domain.research_team.state import ResearchTeamState
from domain.research_team.policy import TeamRoutingPolicy

from application.research_team.web_search_team import WebSearchTeam
from application.research_team.document_search_team import DocumentSearchTeam
from application.hallucination.use_case import HallucinationEvaluatorUseCase

from infrastructure.research_team.supervisor_adapter import SupervisorAdapter
from infrastructure.research_team.synthesizer_adapter import SynthesizerAdapter
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class ResearchTeamWorkflow:
    """Research Team LangGraph 수퍼바이저 워크플로우"""

    def __init__(
        self,
        supervisor_adapter: SupervisorAdapter,
        web_search_team: WebSearchTeam,
        document_search_team: DocumentSearchTeam,
        synthesizer_adapter: SynthesizerAdapter,
        hallucination_use_case: HallucinationEvaluatorUseCase,
    ):
        self._supervisor = supervisor_adapter
        self._web_team = web_search_team
        self._doc_team = document_search_team
        self._synthesizer = synthesizer_adapter
        self._hallucination = hallucination_use_case

        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(ResearchTeamState)

        # 노드 등록
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("web_search_team", self._web_team.run)
        workflow.add_node("document_search_team", self._doc_team.run)
        workflow.add_node("synthesize", self._synthesize_node)
        workflow.add_node("check_hallucination", self._check_hallucination_node)
        workflow.add_node("transform_query", self._transform_query_node)

        # 엔트리포인트
        workflow.set_entry_point("supervisor")

        # 수퍼바이저 → 팀 (병렬 또는 조건부)
        workflow.add_conditional_edges(
            "supervisor",
            self._route_to_teams,
            {
                "web_only": "web_search_team",
                "doc_only": "document_search_team",
                "both_web": "web_search_team",
                "both_doc": "document_search_team",
            }
        )

        # 팀 → 통합
        workflow.add_edge("web_search_team", "synthesize")
        workflow.add_edge("document_search_team", "synthesize")

        # 통합 → 할루시네이션 검사
        workflow.add_edge("synthesize", "check_hallucination")

        # 할루시네이션 검사 → 종료 또는 재시도
        workflow.add_conditional_edges(
            "check_hallucination",
            self._hallucination_condition,
            {
                "ok": END,
                "retry": "transform_query",
            }
        )

        # 재시도 → 수퍼바이저 (팀 재실행)
        workflow.add_conditional_edges(
            "transform_query",
            self._retry_condition,
            {
                "retry": "supervisor",
                "max_retry": END,
            }
        )

        return workflow.compile()

    # ===== 노드 구현 =====

    async def _supervisor_node(self, state: ResearchTeamState) -> dict:
        question = state["question"]
        request_id = state["request_id"]

        logger.info("Node: supervisor", extra={"request_id": request_id})

        decision = await self._supervisor.decide(question, request_id)
        active_teams = [t.value for t in decision.teams]

        return {
            "active_teams": active_teams,
            "supervisor_reason": decision.reason,
        }

    async def _synthesize_node(self, state: ResearchTeamState) -> dict:
        request_id = state["request_id"]

        logger.info("Node: synthesize", extra={"request_id": request_id})

        synthesis = await self._synthesizer.synthesize(
            question=state["question"],
            web_docs=state.get("web_search_docs", []),
            document_docs=state.get("document_search_docs", []),
            request_id=request_id,
        )

        return {"synthesis": synthesis}

    async def _check_hallucination_node(self, state: ResearchTeamState) -> dict:
        request_id = state["request_id"]

        logger.info("Node: check_hallucination", extra={"request_id": request_id})

        all_docs = (
            state.get("web_search_docs", []) +
            state.get("document_search_docs", [])
        )

        result = await self._hallucination.evaluate(
            documents=all_docs,
            generation=state["synthesis"],
            request_id=request_id,
        )

        return {"hallucination_detected": result.is_hallucinated}

    async def _transform_query_node(self, state: ResearchTeamState) -> dict:
        """쿼리 재작성 (재시도 전)"""
        request_id = state["request_id"]
        retry_count = state.get("retry_count", 0)

        logger.info(
            "Node: transform_query",
            extra={"request_id": request_id, "retry_count": retry_count}
        )

        # 각 팀이 자체 query rewrite를 수행하므로 여기서는 상태 초기화만
        return {
            "retry_count": retry_count + 1,
            "web_search_docs": [],
            "document_search_docs": [],
        }

    # ===== 조건 함수 =====

    def _route_to_teams(self, state: ResearchTeamState) -> str:
        """팀 라우팅 조건 (LangGraph 병렬 실행 지원)"""
        active = state["active_teams"]
        both = TeamRoutingPolicy.should_activate_web_search(active) and \
               TeamRoutingPolicy.should_activate_document_search(active)

        if both:
            # NOTE: LangGraph는 같은 조건키에서 여러 노드로 분기 불가
            # 병렬 실행은 Send API 사용 권장 (아래 주석 참고)
            return "both_web"  # web_search_team 먼저, doc_search_team은 conditional로 연결
        elif TeamRoutingPolicy.should_activate_web_search(active):
            return "web_only"
        else:
            return "doc_only"

    def _hallucination_condition(self, state: ResearchTeamState) -> str:
        return "retry" if state.get("hallucination_detected") else "ok"

    def _retry_condition(self, state: ResearchTeamState) -> str:
        retry_count = state.get("retry_count", 0)
        return "retry" if TeamRoutingPolicy.can_retry(retry_count) else "max_retry"

    # ===== 실행 =====

    async def run(self, question: str, request_id: str) -> ResearchTeamState:
        logger.info(
            "ResearchTeamWorkflow started",
            extra={"request_id": request_id, "question": question[:100]}
        )

        initial_state: ResearchTeamState = {
            "question": question,
            "request_id": request_id,
            "active_teams": [],
            "supervisor_reason": "",
            "web_search_docs": [],
            "document_search_docs": [],
            "rewritten_query": "",
            "synthesis": "",
            "hallucination_detected": False,
            "retry_count": 0,
            "web_sources": [],
            "doc_sources": [],
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)

            logger.info(
                "ResearchTeamWorkflow completed",
                extra={
                    "request_id": request_id,
                    "teams_used": final_state.get("active_teams"),
                    "retry_count": final_state.get("retry_count", 0),
                }
            )
            return final_state

        except Exception as e:
            logger.error(
                "ResearchTeamWorkflow failed",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise
```

---

## 7. 파일 구조

```
src/
├── domain/
│   └── research_team/
│       ├── __init__.py
│       ├── state.py              # ResearchTeamState (TypedDict)
│       ├── policy.py             # TeamRoutingPolicy
│       └── value_objects.py      # TeamType, TeamRoutingDecision, TeamSearchResult
│
├── application/
│   └── research_team/
│       ├── __init__.py
│       ├── workflow.py           # ResearchTeamWorkflow (Supervisor)
│       ├── web_search_team.py    # WebSearchTeam
│       └── document_search_team.py # DocumentSearchTeam
│
└── infrastructure/
    └── research_team/
        ├── __init__.py
        ├── supervisor_adapter.py  # SupervisorAdapter
        └── synthesizer_adapter.py # SynthesizerAdapter

tests/
├── domain/
│   └── research_team/
│       ├── test_policy.py
│       └── test_value_objects.py
├── application/
│   └── research_team/
│       ├── test_web_search_team.py
│       ├── test_document_search_team.py
│       └── test_workflow.py
└── infrastructure/
    └── research_team/
        ├── test_supervisor_adapter.py
        └── test_synthesizer_adapter.py
```

---

## 8. 테스트 요구사항

### 8.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/research_team/test_policy.py
import pytest
from domain.research_team.policy import TeamRoutingPolicy


class TestTeamRoutingPolicy:

    class TestSuggestTeams:

        def test_suggests_web_for_latest_keyword(self):
            teams = TeamRoutingPolicy.suggest_teams("최신 뉴스 알려줘")
            assert "web_search" in teams

        def test_suggests_document_for_policy_keyword(self):
            teams = TeamRoutingPolicy.suggest_teams("내부 정책 문서 보여줘")
            assert "document_search" in teams

        def test_suggests_both_for_ambiguous(self):
            teams = TeamRoutingPolicy.suggest_teams("알려줘")
            assert "web_search" in teams
            assert "document_search" in teams

    class TestCanRetry:

        def test_can_retry_within_limit(self):
            assert TeamRoutingPolicy.can_retry(0) is True
            assert TeamRoutingPolicy.can_retry(2) is True

        def test_cannot_retry_at_limit(self):
            assert TeamRoutingPolicy.can_retry(3) is False

    class TestShouldActivate:

        def test_should_activate_web_search(self):
            assert TeamRoutingPolicy.should_activate_web_search(["web_search"]) is True
            assert TeamRoutingPolicy.should_activate_web_search(["document_search"]) is False

        def test_should_activate_document_search(self):
            assert TeamRoutingPolicy.should_activate_document_search(["document_search"]) is True
            assert TeamRoutingPolicy.should_activate_document_search(["web_search"]) is False
```

### 8.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/research_team/test_supervisor_adapter.py
import pytest
from unittest.mock import AsyncMock
from infrastructure.research_team.supervisor_adapter import SupervisorAdapter, SupervisorOutput
from domain.research_team.value_objects import TeamType


class TestSupervisorAdapter:

    @pytest.fixture
    def adapter(self):
        adapter = SupervisorAdapter()
        adapter._chain = AsyncMock()
        return adapter

    @pytest.mark.asyncio
    async def test_decide_returns_web_search_for_news(self, adapter):
        # Given
        adapter._chain.ainvoke.return_value = SupervisorOutput(
            teams=["web_search"],
            reason="최신 뉴스 질문"
        )

        # When
        result = await adapter.decide("오늘 뉴스", "req-001")

        # Then
        assert TeamType.WEB_SEARCH in result.teams

    @pytest.mark.asyncio
    async def test_decide_returns_both_for_complex(self, adapter):
        # Given
        adapter._chain.ainvoke.return_value = SupervisorOutput(
            teams=["web_search", "document_search"],
            reason="복합 질문"
        )

        # When
        result = await adapter.decide("최신 정책 동향 + 내부 규정", "req-002")

        # Then
        assert len(result.teams) == 2
```

### 8.3 Application 테스트 (Mock 사용)

```python
# tests/application/research_team/test_workflow.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from application.research_team.workflow import ResearchTeamWorkflow
from domain.research_team.value_objects import TeamRoutingDecision, TeamType
from domain.hallucination.value_objects import HallucinationEvaluationResult


class TestResearchTeamWorkflow:

    @pytest.fixture
    def mock_deps(self):
        supervisor = AsyncMock()
        supervisor.decide.return_value = TeamRoutingDecision(
            teams=[TeamType.WEB_SEARCH],
            reason="웹 검색 필요"
        )

        web_team = AsyncMock()
        web_team.run.return_value = {"web_search_docs": ["웹 결과"], "web_sources": []}

        doc_team = AsyncMock()
        doc_team.run.return_value = {"document_search_docs": [], "doc_sources": []}

        synthesizer = AsyncMock()
        synthesizer.synthesize.return_value = "통합 답변"

        hallucination = AsyncMock()
        hallucination.evaluate.return_value = HallucinationEvaluationResult(is_hallucinated=False)

        return {
            "supervisor_adapter": supervisor,
            "web_search_team": web_team,
            "document_search_team": doc_team,
            "synthesizer_adapter": synthesizer,
            "hallucination_use_case": hallucination,
        }

    @pytest.mark.asyncio
    async def test_workflow_completes_with_web_search_only(self, mock_deps):
        workflow = ResearchTeamWorkflow(**mock_deps)

        result = await workflow.run("최신 AI 뉴스", "req-001")

        assert result["synthesis"] == "통합 답변"
        assert result["hallucination_detected"] is False
        assert result["retry_count"] == 0

    @pytest.mark.asyncio
    async def test_workflow_retries_on_hallucination(self, mock_deps):
        mock_deps["hallucination_use_case"].evaluate.side_effect = [
            HallucinationEvaluationResult(is_hallucinated=True),
            HallucinationEvaluationResult(is_hallucinated=False),
        ]

        workflow = ResearchTeamWorkflow(**mock_deps)
        result = await workflow.run("테스트 질문", "req-002")

        assert result["retry_count"] >= 1
```

---

## 9. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `MAX_RETRY_COUNT` | `3` | 최대 재시도 횟수 |
| Supervisor `model_name` | `gpt-4o-mini` | 수퍼바이저 LLM |
| Supervisor `temperature` | `0.0` | 결정적 라우팅 |
| Synthesizer `model_name` | `gpt-4o-mini` | 통합 LLM |
| Synthesizer `temperature` | `0.3` | 창의적 통합 |

---

## 10. LangGraph 병렬 실행 (고급)

두 팀을 **병렬**로 실행하려면 `Send` API 사용:

```python
# 병렬 실행 패턴 (Send API)
from langgraph.types import Send

def _route_to_teams_parallel(self, state: ResearchTeamState):
    """병렬 팀 실행"""
    active = state["active_teams"]
    sends = []

    if TeamRoutingPolicy.should_activate_web_search(active):
        sends.append(Send("web_search_team", state))

    if TeamRoutingPolicy.should_activate_document_search(active):
        sends.append(Send("document_search_team", state))

    return sends  # LangGraph가 병렬로 실행
```

> 주의: `Send` API 사용 시 각 팀 노드의 반환값이 `Annotated[list, add]` 필드에 자동 병합됨

---

## 11. 로깅 체크리스트 (LOG-001 준수)

- [ ] `get_logger(__name__)` 사용
- [ ] 수퍼바이저 결정 INFO 로그 (teams, reason)
- [ ] 각 팀 시작/완료 INFO 로그 (doc_count)
- [ ] 통합 시작/완료 INFO 로그 (answer_length)
- [ ] 할루시네이션 결과 INFO 로그
- [ ] 재시도 INFO 로그 (retry_count)
- [ ] 예외 시 ERROR + `exc_info=True`
- [ ] 전 구간 `request_id` 전파
- [ ] `print()` 사용 금지

---

## 12. 금지 사항

- ❌ 무한 루프 (MAX_RETRY_COUNT 필수)
- ❌ 노드에서 직접 외부 API 호출 (Adapter/UseCase 통해서만)
- ❌ domain 레이어에서 LangChain/LangGraph 사용
- ❌ State에 민감 정보 저장
- ❌ `print()` 사용

---

## 13. 의존성 패키지

```txt
langgraph>=0.1.0
langchain-core>=0.1.0
langchain-openai>=0.1.0
pydantic>=2.0.0
```

---

## 14. 의존성 그래프

```
AGENT-003 (Research Team Agent)
├── LOG-001   (로깅)
├── SEARCH-001 (Tavily 웹 검색)
├── RET-001   (벡터 검색)
├── COMP-001  (문서 압축)
├── QUERY-001 (쿼리 재작성)
├── EVAL-001  (할루시네이션 평가)
└── LLM-001   (Claude LLM - 통합에 사용 가능)
```
