"""Adapter for hallucination evaluation using LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from src.domain.hallucination.value_objects import HallucinationEvaluationResult
from src.infrastructure.hallucination.prompts import (
    HALLUCINATION_EVALUATION_SYSTEM_PROMPT,
    HALLUCINATION_EVALUATION_HUMAN_TEMPLATE,
)
from src.infrastructure.hallucination.schemas import HallucinationOutput
from src.infrastructure.logging import get_logger


class HallucinationEvaluatorAdapter:
    """Adapter for evaluating hallucination using LLM with structured output.

    Uses ChatOpenAI with structured output to determine if an LLM generation
    is grounded in the provided reference documents.
    """

    DOCUMENT_SEPARATOR = "\n---\n"

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0
    ) -> None:
        """Initialize the hallucination evaluator adapter.

        Args:
            model_name: The OpenAI model to use for evaluation.
            temperature: Temperature setting for the LLM (0.0 for deterministic output).
        """
        self._logger = get_logger(__name__)
        self._llm = ChatOpenAI(model=model_name, temperature=temperature)
        self._chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain chain for hallucination evaluation."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", HALLUCINATION_EVALUATION_SYSTEM_PROMPT),
            ("human", HALLUCINATION_EVALUATION_HUMAN_TEMPLATE),
        ])
        return prompt | self._llm.with_structured_output(HallucinationOutput)

    async def evaluate(
        self,
        documents: list[str],
        generation: str,
        request_id: str
    ) -> HallucinationEvaluationResult:
        """Evaluate if a generation is hallucinated.

        Args:
            documents: List of reference documents to check against.
            generation: The LLM-generated text to evaluate.
            request_id: Request ID for logging context.

        Returns:
            HallucinationEvaluationResult with is_hallucinated field.

        Raises:
            Exception: If LLM API call fails.
        """
        joined_documents = self.DOCUMENT_SEPARATOR.join(documents)

        try:
            output: HallucinationOutput = await self._chain.ainvoke({
                "documents": joined_documents,
                "generation": generation,
            })
            return HallucinationEvaluationResult(is_hallucinated=output.is_hallucinated)
        except Exception as e:
            self._logger.error(
                "Hallucination evaluation failed",
                exception=e,
                request_id=request_id
            )
            raise
