# Task: Self-Corrective RAG Agent (자기 수정 RAG 에이전트)

> Task ID: AGENT-001  
> 의존성: LOG-001, RET-001, COMP-001, EVAL-001, QUERY-001, SEARCH-001  
> 최종 수정: 2025-01-31

---

## 1. 목적

- 질문 유형에 따라 Web Search 또는 RAG 경로로 라우팅
- RAG 경로에서 문서 관련성 평가 (Grade Documents)
- LLM 답변 생성 후 할루시네이션 검증
- 답변 관련성 검증 실패 시 쿼리 재작성 후 재시도
- 자기 수정(Self-Corrective) 메커니즘으로 답변 품질 보장

---

## 2. 플로우 다이어그램

```
                                    ┌─────────────────┐
                                    │   Web Search    │
                              Web   │    (Tavily)     │
                            ┌──────►│   SEARCH-001    │─────────┐
                            │       └─────────────────┘         │
                            │                                   │
┌──────────┐   ┌─────────┐  │       ┌─────────────────┐         │    ┌─────────────┐
│ Question │──►│ Routing │──┤       │    Retrieve     │         │    │  Generate   │
└──────────┘   └─────────┘  │  RAG  │ (Vector Store)  │         ├───►│    (LLM)    │
                            └──────►│    RET-001      │         │    └──────┬──────┘
                                    └────────┬────────┘         │           │
                                             │                  │           ▼
                                             ▼                  │    ┌─────────────┐
                                    ┌─────────────────┐         │    │Hallucination│
                                    │ Grade Documents │         │    │   Check     │
                                    │   COMP-001      │─────────┘    │  EVAL-001   │
                                    └────────┬────────┘              └──────┬──────┘
                                             │                              │
                                             │ (문서 부족 시)                │ YES (환각 있음)
                                             ▼                              ▼
                                    ┌─────────────────┐              ┌─────────────┐
                                    │ Transform Query │◄─────────────│  Relevant?  │
                                    │   QUERY-001     │     NO       │   Check     │
                                    └─────────────────┘              └──────┬──────┘
                                             │                              │
                                             │                              │ YES
                                             ▼                              ▼
                                    (Retrieve로 재시도)                   [END]
```

---

## 3. 설계 원칙

### 3.1 아키텍처 레이어 배치

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `RoutingPolicy`, `ResearchState`, `RouteDecision` | 라우팅 규칙, 상태 VO 정의 |
| application | `SelfCorrectiveRAGWorkflow` | LangGraph 워크플로우 오케스트레이션 |
| infrastructure | `RouterAdapter`, `GeneratorAdapter`, `RelevanceEvaluatorAdapter` | LLM 호출, 외부 시스템 연동 |

### 3.2 의존성

- LOG-001 (로깅 필수)
- RET-001 (리트리버)
- COMP-001 (문서 압축/평가)
- EVAL-001 (할루시네이션 평가)
- QUERY-001 (쿼리 재작성)
- SEARCH-001 (웹 검색)
- LangGraph (`StateGraph`, `END`)
- LangChain (`ChatPromptTemplate`, `with_structured_output`)

---

## 4. 도메인 설계

### 4.1 RouteDecision (Value Object)

```python
# domain/research_agent/value_objects.py
from enum import Enum
from pydantic import BaseModel, Field


class RouteType(str, Enum):
    """라우팅 타입"""
    WEB_SEARCH = "web_search"
    RAG = "rag"


class RouteDecision(BaseModel):
    """라우팅 결정 결과 VO"""
    
    route: RouteType = Field(description="Selected route type")
    reason: str = Field(default="", description="Reason for routing decision")


class RelevanceResult(BaseModel):
    """답변 관련성 평가 결과 VO"""
    
    is_relevant: bool = Field(description="True if answer is relevant to question")
```

### 4.2 ResearchState (Graph State)

```python
# domain/research_agent/state.py
from typing import TypedDict, Annotated
from operator import add


class ResearchState(TypedDict):
    """LangGraph 상태 정의"""
    
    # 입력
    question: str
    request_id: str
    
    # 라우팅
    route: str  # "web_search" | "rag"
    
    # 검색 결과
    documents: Annotated[list[str], add]  # 검색된 문서들
    web_results: list[dict]  # 웹 검색 결과
    
    # 생성 결과
    generation: str  # LLM 답변
    
    # 평가 결과
    documents_relevant: bool  # 문서 관련성
    hallucination_detected: bool  # 할루시네이션 여부
    answer_relevant: bool  # 답변 관련성
    
    # 재시도 관리
    retry_count: int  # 현재 재시도 횟수
    rewritten_query: str  # 재작성된 쿼리
```

### 4.3 RoutingPolicy (Domain Policy)

```python
# domain/research_agent/policy.py

class RoutingPolicy:
    """라우팅 정책"""
    
    MAX_RETRY_COUNT = 3
    
    # 웹 검색 키워드 (예시)
    WEB_SEARCH_KEYWORDS = [
        "최신", "오늘", "현재", "뉴스", "속보",
        "latest", "today", "current", "news", "recent",
    ]
    
    @staticmethod
    def should_use_web_search(question: str) -> bool:
        """웹 검색 사용 여부 휴리스틱 판단"""
        question_lower = question.lower()
        return any(
            keyword in question_lower
            for keyword in RoutingPolicy.WEB_SEARCH_KEYWORDS
        )
    
    @staticmethod
    def can_retry(retry_count: int) -> bool:
        """재시도 가능 여부"""
        return retry_count < RoutingPolicy.MAX_RETRY_COUNT
    
    @staticmethod
    def should_end(
        hallucination_detected: bool,
        answer_relevant: bool,
    ) -> bool:
        """종료 조건 판단"""
        return not hallucination_detected and answer_relevant
```

---

## 5. 인프라스트럭처 설계

### 5.1 Router Prompt & Adapter

```python
# infrastructure/research_agent/prompts.py

ROUTER_SYSTEM_PROMPT = """You are a query router. Your task is to determine the best data source for answering a question.

## Available Routes
1. **web_search**: Use for questions about current events, recent news, real-time information, or topics that require up-to-date data.
2. **rag**: Use for questions about documents, policies, regulations, historical data, or domain-specific knowledge stored in the vector database.

## Guidelines
- If the question mentions "최신", "오늘", "현재", "뉴스" or similar time-sensitive terms → web_search
- If the question is about company policies, documents, reports, or stored knowledge → rag
- When in doubt, prefer rag for domain-specific questions

Respond with the selected route."""


ROUTER_HUMAN_TEMPLATE = """Question: {question}

Which route should be used? (web_search or rag)"""
```

```python
# infrastructure/research_agent/schemas.py
from pydantic import BaseModel, Field
from typing import Literal


class RouterOutput(BaseModel):
    """라우터 LLM 출력 스키마"""
    
    route: Literal["web_search", "rag"] = Field(
        description="Selected route: web_search or rag"
    )


class RelevanceOutput(BaseModel):
    """관련성 평가 LLM 출력 스키마"""
    
    is_relevant: bool = Field(
        description="True if the answer is relevant to the question"
    )
```

```python
# infrastructure/research_agent/router_adapter.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from domain.research_agent.value_objects import RouteDecision, RouteType
from infrastructure.research_agent.prompts import (
    ROUTER_SYSTEM_PROMPT,
    ROUTER_HUMAN_TEMPLATE,
)
from infrastructure.research_agent.schemas import RouterOutput
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class RouterAdapter:
    """질문 라우팅 LLM Adapter"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", ROUTER_SYSTEM_PROMPT),
            ("human", ROUTER_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm.with_structured_output(RouterOutput)
    
    async def route(
        self,
        question: str,
        request_id: str,
    ) -> RouteDecision:
        """
        질문 라우팅 결정
        
        Args:
            question: 사용자 질문
            request_id: 요청 추적 ID
            
        Returns:
            RouteDecision
        """
        logger.info(
            "Routing decision started",
            extra={
                "request_id": request_id,
                "question_length": len(question),
            }
        )
        
        try:
            result: RouterOutput = await self._chain.ainvoke({
                "question": question,
            })
            
            route_type = RouteType(result.route)
            
            logger.info(
                "Routing decision completed",
                extra={
                    "request_id": request_id,
                    "route": route_type.value,
                }
            )
            
            return RouteDecision(route=route_type)
            
        except Exception as e:
            logger.error(
                "Routing decision failed",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise
```

### 5.2 Relevance Evaluator Adapter

```python
# infrastructure/research_agent/prompts.py (추가)

RELEVANCE_SYSTEM_PROMPT = """You are an answer relevance evaluator. Your task is to determine whether the generated answer properly addresses the user's question.

## Evaluation Criteria
- Does the answer directly address what the user asked?
- Is the answer complete enough to satisfy the user's information need?
- Is the answer on-topic and not tangential?

## Response
Answer with a single boolean:
- true: The answer is relevant and addresses the question
- false: The answer is irrelevant, off-topic, or doesn't address the question"""


RELEVANCE_HUMAN_TEMPLATE = """## Question
{question}

## Answer
{answer}

Is this answer relevant to the question? (true/false)"""
```

```python
# infrastructure/research_agent/relevance_adapter.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from domain.research_agent.value_objects import RelevanceResult
from infrastructure.research_agent.prompts import (
    RELEVANCE_SYSTEM_PROMPT,
    RELEVANCE_HUMAN_TEMPLATE,
)
from infrastructure.research_agent.schemas import RelevanceOutput
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class RelevanceEvaluatorAdapter:
    """답변 관련성 평가 LLM Adapter"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", RELEVANCE_SYSTEM_PROMPT),
            ("human", RELEVANCE_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm.with_structured_output(RelevanceOutput)
    
    async def evaluate(
        self,
        question: str,
        answer: str,
        request_id: str,
    ) -> RelevanceResult:
        """
        답변 관련성 평가
        
        Args:
            question: 사용자 질문
            answer: LLM 생성 답변
            request_id: 요청 추적 ID
            
        Returns:
            RelevanceResult
        """
        logger.info(
            "Relevance evaluation started",
            extra={
                "request_id": request_id,
                "question_length": len(question),
                "answer_length": len(answer),
            }
        )
        
        try:
            result: RelevanceOutput = await self._chain.ainvoke({
                "question": question,
                "answer": answer,
            })
            
            logger.info(
                "Relevance evaluation completed",
                extra={
                    "request_id": request_id,
                    "is_relevant": result.is_relevant,
                }
            )
            
            return RelevanceResult(is_relevant=result.is_relevant)
            
        except Exception as e:
            logger.error(
                "Relevance evaluation failed",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise
```

### 5.3 Generator Adapter

```python
# infrastructure/research_agent/prompts.py (추가)

GENERATOR_SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question based on the provided context.

## Guidelines
- Only use information from the provided context
- If the context doesn't contain enough information, say so
- Be concise and direct
- Cite specific parts of the context when relevant"""


GENERATOR_HUMAN_TEMPLATE = """## Context
{context}

## Question
{question}

Please answer the question based on the context above."""
```

```python
# infrastructure/research_agent/generator_adapter.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from infrastructure.research_agent.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    GENERATOR_HUMAN_TEMPLATE,
)
from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class GeneratorAdapter:
    """답변 생성 LLM Adapter"""
    
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
    ):
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", GENERATOR_SYSTEM_PROMPT),
            ("human", GENERATOR_HUMAN_TEMPLATE),
        ])
        self._chain = self._prompt | self._llm
    
    async def generate(
        self,
        question: str,
        context: str,
        request_id: str,
    ) -> str:
        """
        답변 생성
        
        Args:
            question: 사용자 질문
            context: 검색된 문서/웹 결과 컨텍스트
            request_id: 요청 추적 ID
            
        Returns:
            생성된 답변 문자열
        """
        logger.info(
            "Answer generation started",
            extra={
                "request_id": request_id,
                "question_length": len(question),
                "context_length": len(context),
            }
        )
        
        try:
            result = await self._chain.ainvoke({
                "question": question,
                "context": context,
            })
            
            answer = result.content
            
            logger.info(
                "Answer generation completed",
                extra={
                    "request_id": request_id,
                    "answer_length": len(answer),
                }
            )
            
            return answer
            
        except Exception as e:
            logger.error(
                "Answer generation failed",
                extra={"request_id": request_id},
                exc_info=True,
            )
            raise
```

---

## 6. Application 설계 (LangGraph Workflow)

### 6.1 Workflow 구현

```python
# application/research_agent/workflow.py
from langgraph.graph import StateGraph, END

from domain.research_agent.state import ResearchState
from domain.research_agent.policy import RoutingPolicy
from domain.research_agent.value_objects import RouteType

from infrastructure.research_agent.router_adapter import RouterAdapter
from infrastructure.research_agent.generator_adapter import GeneratorAdapter
from infrastructure.research_agent.relevance_adapter import RelevanceEvaluatorAdapter

# 의존 모듈 (다른 Task에서 가져옴)
from application.hallucination.use_case import HallucinationEvaluatorUseCase
from application.query_rewrite.use_case import QueryRewriterUseCase
from application.web_search.use_case import WebSearchUseCase
# from application.retriever.use_case import RetrieverUseCase  # RET-001
# from application.compressor.use_case import CompressorUseCase  # COMP-001

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class SelfCorrectiveRAGWorkflow:
    """Self-Corrective RAG LangGraph 워크플로우"""
    
    def __init__(
        self,
        router_adapter: RouterAdapter,
        generator_adapter: GeneratorAdapter,
        relevance_adapter: RelevanceEvaluatorAdapter,
        hallucination_use_case: HallucinationEvaluatorUseCase,
        query_rewriter_use_case: QueryRewriterUseCase,
        web_search_use_case: WebSearchUseCase,
        # retriever_use_case: RetrieverUseCase,
        # compressor_use_case: CompressorUseCase,
    ):
        self._router = router_adapter
        self._generator = generator_adapter
        self._relevance = relevance_adapter
        self._hallucination = hallucination_use_case
        self._query_rewriter = query_rewriter_use_case
        self._web_search = web_search_use_case
        # self._retriever = retriever_use_case
        # self._compressor = compressor_use_case
        
        self._graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """LangGraph 그래프 구성"""
        
        workflow = StateGraph(ResearchState)
        
        # 노드 추가
        workflow.add_node("route_question", self._route_question)
        workflow.add_node("web_search", self._web_search_node)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("grade_documents", self._grade_documents_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("check_hallucination", self._check_hallucination_node)
        workflow.add_node("check_relevance", self._check_relevance_node)
        workflow.add_node("transform_query", self._transform_query_node)
        
        # 엣지 설정
        workflow.set_entry_point("route_question")
        
        # 라우팅 분기
        workflow.add_conditional_edges(
            "route_question",
            self._route_condition,
            {
                "web_search": "web_search",
                "rag": "retrieve",
            }
        )
        
        # Web Search → Generate
        workflow.add_edge("web_search", "generate")
        
        # Retrieve → Grade Documents
        workflow.add_edge("retrieve", "grade_documents")
        
        # Grade Documents 분기
        workflow.add_conditional_edges(
            "grade_documents",
            self._grade_condition,
            {
                "relevant": "generate",
                "not_relevant": "transform_query",
            }
        )
        
        # Generate → Check Hallucination
        workflow.add_edge("generate", "check_hallucination")
        
        # Check Hallucination 분기
        workflow.add_conditional_edges(
            "check_hallucination",
            self._hallucination_condition,
            {
                "no_hallucination": "check_relevance",
                "hallucination": "transform_query",
            }
        )
        
        # Check Relevance 분기
        workflow.add_conditional_edges(
            "check_relevance",
            self._relevance_condition,
            {
                "relevant": END,
                "not_relevant": "transform_query",
            }
        )
        
        # Transform Query → Retrieve (재시도)
        workflow.add_conditional_edges(
            "transform_query",
            self._retry_condition,
            {
                "retry": "retrieve",
                "max_retry": END,
            }
        )
        
        return workflow.compile()
    
    # ===== 노드 구현 =====
    
    async def _route_question(self, state: ResearchState) -> dict:
        """질문 라우팅 노드"""
        question = state["question"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: route_question",
            extra={"request_id": request_id}
        )
        
        decision = await self._router.route(question, request_id)
        
        return {"route": decision.route.value}
    
    async def _web_search_node(self, state: ResearchState) -> dict:
        """웹 검색 노드"""
        question = state.get("rewritten_query") or state["question"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: web_search",
            extra={"request_id": request_id}
        )
        
        result = self._web_search.search(question, request_id)
        
        # 웹 검색 결과를 문서 형태로 변환
        documents = [
            f"Title: {item.title}\nURL: {item.url}\nContent: {item.content}"
            for item in result.results
        ]
        
        return {
            "web_results": [item.model_dump() for item in result.results],
            "documents": documents,
        }
    
    async def _retrieve_node(self, state: ResearchState) -> dict:
        """벡터 검색 노드"""
        question = state.get("rewritten_query") or state["question"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: retrieve",
            extra={"request_id": request_id}
        )
        
        # TODO: RET-001 RetrieverUseCase 연동
        # documents = await self._retriever.retrieve(question, request_id)
        
        # 임시 구현 (실제로는 RET-001 사용)
        documents = []
        
        return {"documents": documents}
    
    async def _grade_documents_node(self, state: ResearchState) -> dict:
        """문서 관련성 평가 노드"""
        documents = state["documents"]
        question = state["question"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: grade_documents",
            extra={
                "request_id": request_id,
                "document_count": len(documents),
            }
        )
        
        # TODO: COMP-001 CompressorUseCase 연동
        # relevant_docs = await self._compressor.compress(documents, question, request_id)
        
        # 임시: 문서가 있으면 관련 있다고 판단
        documents_relevant = len(documents) > 0
        
        return {"documents_relevant": documents_relevant}
    
    async def _generate_node(self, state: ResearchState) -> dict:
        """답변 생성 노드"""
        question = state["question"]
        documents = state["documents"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: generate",
            extra={"request_id": request_id}
        )
        
        context = "\n\n---\n\n".join(documents)
        generation = await self._generator.generate(question, context, request_id)
        
        return {"generation": generation}
    
    async def _check_hallucination_node(self, state: ResearchState) -> dict:
        """할루시네이션 검사 노드"""
        documents = state["documents"]
        generation = state["generation"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: check_hallucination",
            extra={"request_id": request_id}
        )
        
        result = await self._hallucination.evaluate(
            documents=documents,
            generation=generation,
            request_id=request_id,
        )
        
        return {"hallucination_detected": result.is_hallucinated}
    
    async def _check_relevance_node(self, state: ResearchState) -> dict:
        """답변 관련성 검사 노드"""
        question = state["question"]
        generation = state["generation"]
        request_id = state["request_id"]
        
        logger.info(
            "Node: check_relevance",
            extra={"request_id": request_id}
        )
        
        result = await self._relevance.evaluate(
            question=question,
            answer=generation,
            request_id=request_id,
        )
        
        return {"answer_relevant": result.is_relevant}
    
    async def _transform_query_node(self, state: ResearchState) -> dict:
        """쿼리 재작성 노드"""
        question = state["question"]
        request_id = state["request_id"]
        retry_count = state.get("retry_count", 0)
        
        logger.info(
            "Node: transform_query",
            extra={
                "request_id": request_id,
                "retry_count": retry_count,
            }
        )
        
        result = await self._query_rewriter.rewrite(question, request_id)
        
        return {
            "rewritten_query": result.rewritten_query,
            "retry_count": retry_count + 1,
        }
    
    # ===== 조건 함수 =====
    
    def _route_condition(self, state: ResearchState) -> str:
        """라우팅 조건"""
        return state["route"]
    
    def _grade_condition(self, state: ResearchState) -> str:
        """문서 관련성 조건"""
        if state.get("documents_relevant", False):
            return "relevant"
        return "not_relevant"
    
    def _hallucination_condition(self, state: ResearchState) -> str:
        """할루시네이션 조건"""
        if state.get("hallucination_detected", False):
            return "hallucination"
        return "no_hallucination"
    
    def _relevance_condition(self, state: ResearchState) -> str:
        """답변 관련성 조건"""
        if state.get("answer_relevant", False):
            return "relevant"
        return "not_relevant"
    
    def _retry_condition(self, state: ResearchState) -> str:
        """재시도 조건"""
        retry_count = state.get("retry_count", 0)
        if RoutingPolicy.can_retry(retry_count):
            return "retry"
        return "max_retry"
    
    # ===== 실행 =====
    
    async def run(
        self,
        question: str,
        request_id: str,
    ) -> ResearchState:
        """
        워크플로우 실행
        
        Args:
            question: 사용자 질문
            request_id: 요청 추적 ID
            
        Returns:
            최종 상태
        """
        logger.info(
            "Workflow started",
            extra={
                "request_id": request_id,
                "question": question[:100],
            }
        )
        
        initial_state: ResearchState = {
            "question": question,
            "request_id": request_id,
            "route": "",
            "documents": [],
            "web_results": [],
            "generation": "",
            "documents_relevant": False,
            "hallucination_detected": False,
            "answer_relevant": False,
            "retry_count": 0,
            "rewritten_query": "",
        }
        
        try:
            final_state = await self._graph.ainvoke(initial_state)
            
            logger.info(
                "Workflow completed",
                extra={
                    "request_id": request_id,
                    "retry_count": final_state.get("retry_count", 0),
                    "hallucination_detected": final_state.get("hallucination_detected"),
                    "answer_relevant": final_state.get("answer_relevant"),
                }
            )
            
            return final_state
            
        except Exception as e:
            logger.error(
                "Workflow failed",
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
│   └── research_agent/
│       ├── __init__.py
│       ├── policy.py              # RoutingPolicy
│       ├── state.py               # ResearchState (TypedDict)
│       └── value_objects.py       # RouteDecision, RelevanceResult
├── application/
│   └── research_agent/
│       ├── __init__.py
│       └── workflow.py            # SelfCorrectiveRAGWorkflow
└── infrastructure/
    └── research_agent/
        ├── __init__.py
        ├── prompts.py             # 모든 프롬프트
        ├── schemas.py             # RouterOutput, RelevanceOutput
        ├── router_adapter.py      # RouterAdapter
        ├── generator_adapter.py   # GeneratorAdapter
        └── relevance_adapter.py   # RelevanceEvaluatorAdapter
```

---

## 8. 테스트 요구사항

### 8.1 Domain 테스트 (Mock 금지)

```python
# tests/domain/research_agent/test_policy.py
import pytest
from domain.research_agent.policy import RoutingPolicy


class TestRoutingPolicy:
    
    class TestShouldUseWebSearch:
        
        def test_returns_true_for_latest_keyword(self):
            assert RoutingPolicy.should_use_web_search("최신 뉴스 알려줘") is True
        
        def test_returns_true_for_today_keyword(self):
            assert RoutingPolicy.should_use_web_search("오늘 날씨 어때?") is True
        
        def test_returns_false_for_general_question(self):
            assert RoutingPolicy.should_use_web_search("회사 정책 알려줘") is False
    
    class TestCanRetry:
        
        def test_returns_true_when_under_max(self):
            assert RoutingPolicy.can_retry(0) is True
            assert RoutingPolicy.can_retry(2) is True
        
        def test_returns_false_when_at_max(self):
            assert RoutingPolicy.can_retry(3) is False
            assert RoutingPolicy.can_retry(5) is False
    
    class TestShouldEnd:
        
        def test_returns_true_when_no_hallucination_and_relevant(self):
            assert RoutingPolicy.should_end(
                hallucination_detected=False,
                answer_relevant=True,
            ) is True
        
        def test_returns_false_when_hallucination_detected(self):
            assert RoutingPolicy.should_end(
                hallucination_detected=True,
                answer_relevant=True,
            ) is False
        
        def test_returns_false_when_not_relevant(self):
            assert RoutingPolicy.should_end(
                hallucination_detected=False,
                answer_relevant=False,
            ) is False
```

### 8.2 Infrastructure 테스트 (Mock 사용)

```python
# tests/infrastructure/research_agent/test_router_adapter.py
import pytest
from unittest.mock import AsyncMock

from infrastructure.research_agent.router_adapter import RouterAdapter
from infrastructure.research_agent.schemas import RouterOutput
from domain.research_agent.value_objects import RouteType


class TestRouterAdapter:
    
    @pytest.fixture
    def mock_chain(self):
        return AsyncMock()
    
    @pytest.fixture
    def adapter(self, mock_chain):
        adapter = RouterAdapter()
        adapter._chain = mock_chain
        return adapter
    
    @pytest.mark.asyncio
    async def test_route_returns_web_search(self, adapter, mock_chain):
        # Given
        mock_chain.ainvoke.return_value = RouterOutput(route="web_search")
        
        # When
        result = await adapter.route("최신 뉴스", "req-123")
        
        # Then
        assert result.route == RouteType.WEB_SEARCH
    
    @pytest.mark.asyncio
    async def test_route_returns_rag(self, adapter, mock_chain):
        # Given
        mock_chain.ainvoke.return_value = RouterOutput(route="rag")
        
        # When
        result = await adapter.route("회사 정책 알려줘", "req-123")
        
        # Then
        assert result.route == RouteType.RAG
```

### 8.3 Application 테스트 (Integration)

```python
# tests/application/research_agent/test_workflow.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from application.research_agent.workflow import SelfCorrectiveRAGWorkflow
from domain.research_agent.value_objects import RouteDecision, RouteType, RelevanceResult
from domain.hallucination.value_objects import HallucinationEvaluationResult
from domain.query_rewrite.value_objects import RewrittenQuery


class TestSelfCorrectiveRAGWorkflow:
    
    @pytest.fixture
    def mock_dependencies(self):
        return {
            "router_adapter": AsyncMock(),
            "generator_adapter": AsyncMock(),
            "relevance_adapter": AsyncMock(),
            "hallucination_use_case": AsyncMock(),
            "query_rewriter_use_case": AsyncMock(),
            "web_search_use_case": MagicMock(),
        }
    
    @pytest.mark.asyncio
    async def test_workflow_ends_when_answer_is_relevant(self, mock_dependencies):
        # Given
        mock_dependencies["router_adapter"].route.return_value = RouteDecision(
            route=RouteType.RAG
        )
        mock_dependencies["generator_adapter"].generate.return_value = "Good answer"
        mock_dependencies["hallucination_use_case"].evaluate.return_value = (
            HallucinationEvaluationResult(is_hallucinated=False)
        )
        mock_dependencies["relevance_adapter"].evaluate.return_value = (
            RelevanceResult(is_relevant=True)
        )
        
        workflow = SelfCorrectiveRAGWorkflow(**mock_dependencies)
        
        # When
        result = await workflow.run("테스트 질문입니다", "req-123")
        
        # Then
        assert result["answer_relevant"] is True
        assert result["hallucination_detected"] is False
    
    @pytest.mark.asyncio
    async def test_workflow_retries_on_hallucination(self, mock_dependencies):
        # Given: 첫 번째는 환각, 두 번째는 정상
        mock_dependencies["router_adapter"].route.return_value = RouteDecision(
            route=RouteType.RAG
        )
        mock_dependencies["generator_adapter"].generate.return_value = "Answer"
        mock_dependencies["hallucination_use_case"].evaluate.side_effect = [
            HallucinationEvaluationResult(is_hallucinated=True),
            HallucinationEvaluationResult(is_hallucinated=False),
        ]
        mock_dependencies["relevance_adapter"].evaluate.return_value = (
            RelevanceResult(is_relevant=True)
        )
        mock_dependencies["query_rewriter_use_case"].rewrite.return_value = (
            RewrittenQuery(original_query="q", rewritten_query="better q")
        )
        
        workflow = SelfCorrectiveRAGWorkflow(**mock_dependencies)
        
        # When
        result = await workflow.run("테스트 질문", "req-123")
        
        # Then
        assert result["retry_count"] >= 1
```

---

## 9. 사용 예시

```python
from application.research_agent.workflow import SelfCorrectiveRAGWorkflow
from infrastructure.research_agent.router_adapter import RouterAdapter
from infrastructure.research_agent.generator_adapter import GeneratorAdapter
from infrastructure.research_agent.relevance_adapter import RelevanceEvaluatorAdapter

# 의존성 (다른 Task 모듈)
from application.hallucination.use_case import HallucinationEvaluatorUseCase
from application.query_rewrite.use_case import QueryRewriterUseCase
from application.web_search.use_case import WebSearchUseCase
from infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from infrastructure.query_rewrite.adapter import QueryRewriterAdapter
from infrastructure.web_search.tavily_tool import TavilySearchTool


# 의존성 생성
router = RouterAdapter()
generator = GeneratorAdapter()
relevance = RelevanceEvaluatorAdapter()

hallucination_adapter = HallucinationEvaluatorAdapter()
hallucination_use_case = HallucinationEvaluatorUseCase(hallucination_adapter)

query_rewriter_adapter = QueryRewriterAdapter()
query_rewriter_use_case = QueryRewriterUseCase(query_rewriter_adapter)

tavily_tool = TavilySearchTool()
web_search_use_case = WebSearchUseCase(tavily_tool)

# 워크플로우 생성
workflow = SelfCorrectiveRAGWorkflow(
    router_adapter=router,
    generator_adapter=generator,
    relevance_adapter=relevance,
    hallucination_use_case=hallucination_use_case,
    query_rewriter_use_case=query_rewriter_use_case,
    web_search_use_case=web_search_use_case,
)

# 실행
result = await workflow.run(
    question="최신 AI 기술 동향을 알려줘",
    request_id="req-abc-123",
)

print(f"Route: {result['route']}")
print(f"Answer: {result['generation']}")
print(f"Retry count: {result['retry_count']}")
```

---

## 10. 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `MAX_RETRY_COUNT` | `3` | 최대 재시도 횟수 |
| Router `model_name` | `gpt-4o-mini` | 라우터 LLM 모델 |
| Router `temperature` | `0.0` | 라우터 temperature |
| Generator `model_name` | `gpt-4o-mini` | 생성기 LLM 모델 |
| Generator `temperature` | `0.7` | 생성기 temperature |
| Relevance `temperature` | `0.0` | 관련성 평가 temperature |

---

## 11. 로깅 체크리스트 (LOG-001 준수)

- [x] `get_logger(__name__)` 사용
- [x] 각 노드 진입 시 INFO 로그
- [x] 워크플로우 시작/완료 INFO 로그
- [x] 예외 발생 시 ERROR 로그 + `exc_info=True`
- [x] `request_id` 전 구간 전파
- [x] 재시도 횟수, 평가 결과 로깅

---

## 12. 금지 사항

- ❌ 무한 루프 (MAX_RETRY_COUNT 필수 적용)
- ❌ 노드에서 직접 외부 API 호출 (Adapter 통해서만)
- ❌ State에 민감 정보 저장 금지
- ❌ `print()` 사용 금지
- ❌ `request_id` 없는 로그 금지

---

## 13. 의존성 패키지

```txt
langgraph>=0.0.30
langchain-core>=0.1.0
langchain-openai>=0.1.0
pydantic>=2.0.0
```

---
