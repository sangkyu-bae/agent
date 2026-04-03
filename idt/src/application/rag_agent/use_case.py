"""RAGAgentUseCase: LangGraph ReAct 에이전트 기반 내부 문서 질의응답."""
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.rag_agent.schemas import RAGAgentRequest, RAGAgentResponse


class RAGAgentUseCase:
    """LangGraph ReAct 에이전트를 사용한 내부 문서 기반 질의응답 UseCase.

    동작 방식:
    1. 질문을 받아 ReAct 에이전트에 전달한다.
    2. 에이전트가 내부 문서가 필요하다고 판단하면 InternalDocumentSearchTool을 호출한다.
       - 도구는 BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색을 수행한다.
    3. 에이전트가 생성한 최종 답변과 참조 출처 목록을 반환한다.
    """

    _SYSTEM_PROMPT = (
        "당신은 내부 문서 기반 질의응답 AI 어시스턴트입니다.\n"
        "질문에 답하기 위해 내부 문서 정보가 필요하다고 판단되면 "
        "internal_document_search 도구를 사용하여 관련 문서를 검색하세요.\n"
        "일반 상식으로 답할 수 있는 질문은 도구 없이 직접 답변하세요.\n"
        "항상 한국어로 답변하세요."
    )

    def __init__(
        self,
        hybrid_search_use_case: object,
        openai_api_key: str,
        model_name: str,
        logger: LoggerInterface,
    ) -> None:
        self._hybrid_search = hybrid_search_use_case
        self._api_key = openai_api_key
        self._model_name = model_name
        self._logger = logger

    async def execute(
        self, request: RAGAgentRequest, request_id: str
    ) -> RAGAgentResponse:
        """ReAct 에이전트로 질문에 답변한다.

        Args:
            request: 질의 요청 (query, user_id, top_k)
            request_id: 요청 추적 ID

        Returns:
            LLM 생성 답변 + 참조 출처 문서 목록
        """
        self._logger.info(
            "RAGAgent started",
            request_id=request_id,
            query=request.query,
            user_id=request.user_id,
        )
        try:
            tool = InternalDocumentSearchTool(
                hybrid_search_use_case=self._hybrid_search,
                top_k=request.top_k,
                request_id=request_id,
            )
            llm = ChatOpenAI(
                model=self._model_name,
                api_key=self._api_key,
                temperature=0,
            )
            agent = create_react_agent(llm, tools=[tool])

            messages = [
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": request.query},
            ]
            result = await agent.ainvoke({"messages": messages})

            answer, used_internal_docs = self._parse_agent_result(result)

            self._logger.info(
                "RAGAgent completed",
                request_id=request_id,
                used_internal_docs=used_internal_docs,
                sources_count=len(tool.collected_sources),
            )
            return RAGAgentResponse(
                query=request.query,
                answer=answer,
                sources=list(tool.collected_sources),
                used_internal_docs=used_internal_docs,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error("RAGAgent failed", exception=e, request_id=request_id)
            raise

    def _parse_agent_result(self, result: dict) -> tuple[str, bool]:
        """에이전트 결과에서 최종 답변과 내부 문서 사용 여부 추출."""
        messages = result.get("messages", [])
        answer = ""
        if messages:
            last = messages[-1]
            answer = last.content if hasattr(last, "content") else str(last)

        used_internal_docs = any(
            getattr(m, "name", None) == "internal_document_search"
            for m in messages
        )
        return answer, used_internal_docs
