"""Adapter for answer relevance evaluation using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.research_agent.value_objects import RelevanceResult
from src.infrastructure.research_agent.prompts import (
    RELEVANCE_SYSTEM_PROMPT,
    RELEVANCE_HUMAN_TEMPLATE,
)
from src.infrastructure.research_agent.schemas import RelevanceOutput
from src.infrastructure.logging import get_logger


class RelevanceEvaluatorAdapter:
    """Adapter for evaluating answer relevance using LLM.

    Uses ChatOpenAI with structured output to determine if an answer
    is relevant to the given question.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0
    ) -> None:
        """Initialize the relevance evaluator adapter.

        Args:
            model_name: The OpenAI model to use for evaluation.
            temperature: Temperature setting for the LLM (0.0 for deterministic output).
        """
        self._logger = get_logger(__name__)
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain chain for relevance evaluation."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", RELEVANCE_SYSTEM_PROMPT),
            ("human", RELEVANCE_HUMAN_TEMPLATE),
        ])
        return prompt | self._llm.with_structured_output(RelevanceOutput)

    async def evaluate(
        self,
        question: str,
        answer: str,
        request_id: str
    ) -> RelevanceResult:
        """Evaluate if an answer is relevant to a question.

        Args:
            question: The user's question.
            answer: The generated answer to evaluate.
            request_id: Request ID for logging context.

        Returns:
            RelevanceResult with is_relevant field.

        Raises:
            Exception: If LLM API call fails.
        """
        self._logger.info(
            "Evaluating answer relevance",
            request_id=request_id,
            question_length=len(question),
            answer_length=len(answer)
        )

        try:
            output: RelevanceOutput = await self._chain.ainvoke({
                "question": question,
                "answer": answer,
            })

            self._logger.info(
                "Answer relevance evaluated",
                request_id=request_id,
                is_relevant=output.is_relevant
            )

            return RelevanceResult(is_relevant=output.is_relevant)

        except Exception as e:
            self._logger.error(
                "Relevance evaluation failed",
                exception=e,
                request_id=request_id
            )
            raise
