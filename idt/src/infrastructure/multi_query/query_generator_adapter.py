"""LLM 기반 Multi-Query 생성 어댑터."""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.multi_query.prompts import (
    MULTI_QUERY_SYSTEM_PROMPT,
    MULTI_QUERY_HUMAN_TEMPLATE,
)
from src.infrastructure.multi_query.schemas import MultiQueryGeneratorOutput


class QueryGeneratorAdapter:
    """LLM으로 Multi-Query를 생성하는 인프라 어댑터."""

    def __init__(
        self,
        logger: LoggerInterface,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
    ) -> None:
        self._logger = logger
        llm = ChatOpenAI(model=model_name, temperature=temperature)
        prompt = ChatPromptTemplate.from_messages([
            ("system", MULTI_QUERY_SYSTEM_PROMPT),
            ("human", MULTI_QUERY_HUMAN_TEMPLATE),
        ])
        self._chain = prompt | llm.with_structured_output(MultiQueryGeneratorOutput)

    async def generate(
        self,
        query: str,
        num_queries: int,
        request_id: str,
    ) -> list[str]:
        """Multi-Query 생성. 실패 시 원본 쿼리로 fallback.

        Args:
            query: 원본 사용자 쿼리
            num_queries: 생성할 변형 쿼리 수
            request_id: 요청 추적 ID

        Returns:
            변형 쿼리 리스트 (실패 시 [원본 쿼리])
        """
        self._logger.info(
            "Multi-query generation started",
            request_id=request_id,
            query_length=len(query),
            num_queries=num_queries,
        )

        try:
            output: MultiQueryGeneratorOutput = await self._chain.ainvoke({
                "query": query,
                "num_queries": num_queries,
            })

            filtered = [q.strip() for q in output.queries if q.strip()]

            if not filtered:
                self._logger.warning(
                    "All generated queries were empty, falling back to original",
                    request_id=request_id,
                )
                return [query]

            self._logger.info(
                "Multi-query generation completed",
                request_id=request_id,
                generated_count=len(filtered),
            )
            return filtered

        except Exception as e:
            self._logger.error(
                "Multi-query generation failed",
                exception=e,
                request_id=request_id,
            )
            return [query]
