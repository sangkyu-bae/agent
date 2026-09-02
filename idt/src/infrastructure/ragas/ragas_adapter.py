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
        # 기본 judge 모델. evaluate(judge_model=...)로 실행별 재정의 가능 (D4).
        self._llm_model = llm_model

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        metrics: list[str],
        request_id: str,
        judge_model: str | None = None,
    ) -> dict[str, float]:
        effective_judge = judge_model or self._llm_model
        self._logger.info(
            "RAGAS evaluate start",
            request_id=request_id,
            metrics=metrics,
            judge_model=effective_judge,
        )
        try:
            ragas_metrics = self._build_metrics(metrics)
            if not ragas_metrics:
                return {}
            # agent-model-benchmark D4: judge를 각 metric에 실제로 주입한다.
            # 주입하지 않으면 RAGAS가 자체 기본 LLM을 쓰기 때문에 화면에서 고른
            # judge가 무시되고, 스윕 간 채점 기준이 조용히 달라진다.
            self._attach_judge(ragas_metrics, effective_judge, request_id)

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

    def _attach_judge(
        self, ragas_metrics: list, judge_model: str, request_id: str
    ) -> None:
        """각 RAGAS metric에 채점용 LLM을 주입한다 (D4).

        embedding 기반 metric(SemanticSimilarity 등)은 llm 속성이 없어 건너뛴다.
        주입 실패는 채점을 막지 않는다 — RAGAS 기본 judge로 낙하하고 경고만 남긴다.
        """
        try:
            from langchain_openai import ChatOpenAI
            from ragas.llms import LangchainLLMWrapper

            wrapped = LangchainLLMWrapper(
                ChatOpenAI(model=judge_model, temperature=0)
            )
        except Exception as e:
            self._logger.warning(
                "Judge LLM 주입 실패 — RAGAS 기본 judge로 진행",
                request_id=request_id,
                judge_model=judge_model,
                exception=e,
            )
            return

        for metric in ragas_metrics:
            if hasattr(metric, "llm"):
                metric.llm = wrapped

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
