"""Adapter for answer generation using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.infrastructure.research_agent.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    GENERATOR_HUMAN_TEMPLATE,
)
from src.infrastructure.logging import get_logger


class GeneratorAdapter:
    """Adapter for generating answers using LLM.

    Uses ChatOpenAI to generate answers based on provided context.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0
    ) -> None:
        """Initialize the generator adapter.

        Args:
            model_name: The OpenAI model to use for generation.
            temperature: Temperature setting for the LLM.
        """
        self._logger = get_logger(__name__)
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain chain for answer generation."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", GENERATOR_SYSTEM_PROMPT),
            ("human", GENERATOR_HUMAN_TEMPLATE),
        ])
        return prompt | self._llm

    async def generate(
        self,
        question: str,
        context: str,
        request_id: str
    ) -> str:
        """Generate an answer based on context.

        Args:
            question: The user's question.
            context: The context to use for answering.
            request_id: Request ID for logging context.

        Returns:
            The generated answer as a string.

        Raises:
            Exception: If LLM API call fails.
        """
        self._logger.info(
            "Generating answer",
            request_id=request_id,
            question_length=len(question),
            context_length=len(context)
        )

        try:
            response = await self._chain.ainvoke({
                "question": question,
                "context": context,
            })

            answer = response.content

            self._logger.info(
                "Answer generated",
                request_id=request_id,
                answer_length=len(answer)
            )

            return answer

        except Exception as e:
            self._logger.error(
                "Answer generation failed",
                exception=e,
                request_id=request_id
            )
            raise
