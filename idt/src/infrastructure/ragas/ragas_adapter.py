"""RAGAS 라이브러리 래핑 어댑터."""
import asyncio
from functools import partial

from src.domain.ragas.interfaces import EvaluatorInterface
from src.infrastructure.logging import get_logger


class RagasEvaluatorAdapter(EvaluatorInterface):
    """RAGAS 평가 어댑터.

    ragas 0.2+ API 기준으로 SingleTurnSample + evaluate 호출.
    """

    METRIC_MAP = {
        "faithfulness": "Faithfulness",
        "answer_relevancy": "AnswerRelevancy",
        "context_precision": "LLMContextPrecisionWithoutReference",
        "context_recall": "LLMContextRecall",
        "answer_correctness": "AnswerCorrectness",
        "answer_similarity": "SemanticSimilarity",
    }

    def __init__(self, llm_model: str = "gpt-4o-mini") -> None:
        self._logger = get_logger(__name__)
        self._llm_model = llm_model

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        metrics: list[str],
        request_id: str,
    ) -> dict[str, float]:
        self._logger.info(
            "RAGAS evaluate start",
            request_id=request_id,
            metrics=metrics,
        )
        try:
            ragas_metrics = self._build_metrics(metrics)
            if not ragas_metrics:
                return {}

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                partial(
                    self._run_sync,
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth,
                    ragas_metrics=ragas_metrics,
                ),
            )
            self._logger.info(
                "RAGAS evaluate done",
                request_id=request_id,
                scores=result,
            )
            return result
        except Exception:
            self._logger.exception("RAGAS evaluate failed", request_id=request_id)
            raise

    def _build_metrics(self, metric_names: list[str]) -> list:
        from ragas.metrics import (
            AnswerCorrectness,
            AnswerRelevancy,
            Faithfulness,
            LLMContextPrecisionWithoutReference,
            LLMContextRecall,
            SemanticSimilarity,
        )

        mapping = {
            "faithfulness": Faithfulness(),
            "answer_relevancy": AnswerRelevancy(),
            "context_precision": LLMContextPrecisionWithoutReference(),
            "context_recall": LLMContextRecall(),
            "answer_correctness": AnswerCorrectness(),
            "answer_similarity": SemanticSimilarity(),
        }

        result = []
        for name in metric_names:
            if name in mapping:
                result.append(mapping[name])
        return result

    def _run_sync(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        ragas_metrics: list,
    ) -> dict[str, float]:
        from ragas import evaluate
        from ragas.dataset_schema import SingleTurnSample, EvaluationDataset

        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth or "",
        )
        dataset = EvaluationDataset(samples=[sample])

        result = evaluate(
            dataset=dataset,
            metrics=ragas_metrics,
        )

        scores: dict[str, float] = {}
        reverse_map = {v: k for k, v in self.METRIC_MAP.items()}
        for col in result.to_pandas().columns:
            if col in reverse_map:
                val = result.to_pandas()[col].iloc[0]
                if val is not None:
                    scores[reverse_map[col]] = float(val)
            elif col not in ("user_input", "response", "retrieved_contexts", "reference"):
                scores[col] = float(result.to_pandas()[col].iloc[0])

        return scores
