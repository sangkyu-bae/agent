"""DefaultTargetExecutor — 평가 대상별 답변·컨텍스트 생성 (eval-hub Design §2.4).

- retrieval: 컬렉션 벡터 검색 → contexts + 순위 메트릭(hit_rate/mrr/ndcg)
- rag: 검색 contexts + LLM 답변 생성
- agent: RunAgentUseCase 헤드리스 실행(agent_schedule 선례) → answer만

순위 메트릭의 정답 판정: 케이스의 expected_contexts 각 문자열이 검색된
컨텍스트 텍스트에 부분 포함되면 해당 순위를 관련 문서로 간주한다
(ID 배관 없이 동작하는 v1 근사 — 코드 주석으로 계약 고정).
"""
from typing import Awaitable, Callable

from langchain_core.prompts import ChatPromptTemplate
from qdrant_client import AsyncQdrantClient

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.interfaces import TargetExecutorInterface
from src.domain.ragas.policies import RETRIEVAL_RANK_METRICS
from src.domain.ragas.value_objects import EvalConfig, TestCase
from src.domain.vector.interfaces import EmbeddingInterface
from src.infrastructure.ragas.retrieval_metric_calculator import (
    RetrievalMetricCalculator,
)
from src.infrastructure.retriever.qdrant_retriever import QdrantRetriever

# (agent_id, question, user_id, request_id) -> answer
AgentRunner = Callable[[str, str, str, str], Awaitable[str]]

_RAG_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "다음 문서 발췌만 근거로 사용자 질문에 한국어로 답하세요. "
        "발췌에 없는 내용은 지어내지 말고 '문서에서 확인할 수 없습니다'라고 답하세요.\n"
        "--- 문서 발췌 ---\n{contexts}",
    ),
    ("human", "{question}"),
])


class DefaultTargetExecutor(TargetExecutorInterface):
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        embedding: EmbeddingInterface,
        agent_runner: AgentRunner,
        logger: LoggerInterface,
    ) -> None:
        self._client = qdrant_client
        self._embedding = embedding
        self._agent_runner = agent_runner
        self._logger = logger
        self._llm_cache: dict[str, object] = {}

    async def execute(
        self,
        target_type: str,
        config: EvalConfig,
        case: TestCase,
        user_id: str | None,
        request_id: str,
    ) -> tuple[str, list[str], dict[str, float]]:
        if target_type == "agent":
            return await self._run_agent(config, case, user_id, request_id)

        contexts = await self._retrieve(config, case.question)
        if target_type == "retrieval":
            extra = self._rank_scores(config, contexts, case.expected_contexts)
            return "", contexts, extra

        answer = await self._generate_answer(
            case.question, contexts, config.llm_model
        )
        return answer, contexts, {}

    # ── agent ───────────────────────────────────────────────────────

    async def _run_agent(
        self,
        config: EvalConfig,
        case: TestCase,
        user_id: str | None,
        request_id: str,
    ) -> tuple[str, list[str], dict[str, float]]:
        if not config.agent_id:
            raise ValueError("agent 대상 평가에는 agent_id가 필요합니다")
        if not user_id:
            raise ValueError("agent 대상 평가에는 실행 사용자가 필요합니다")
        answer = await self._agent_runner(
            config.agent_id, case.question, user_id, request_id
        )
        return answer, [], {}

    # ── rag / retrieval ────────────────────────────────────────────

    async def _retrieve(self, config: EvalConfig, question: str) -> list[str]:
        if not config.collection_name:
            raise ValueError("rag/retrieval 대상 평가에는 collection_name이 필요합니다")
        retriever = QdrantRetriever(
            client=self._client,
            collection_name=config.collection_name,
            embedding=self._embedding,
        )
        docs_with_scores = await retriever.retrieve_with_scores(
            question, top_k=config.top_k
        )
        return [doc.content for doc, _ in docs_with_scores]

    async def _generate_answer(
        self, question: str, contexts: list[str], llm_model: str
    ) -> str:
        llm = self._get_llm(llm_model)
        joined = "\n---\n".join(contexts) if contexts else "(검색 결과 없음)"
        message = await (_RAG_PROMPT | llm).ainvoke(
            {"question": question, "contexts": joined}
        )
        return str(message.content)

    def _get_llm(self, model_name: str):
        if model_name not in self._llm_cache:
            from langchain_openai import ChatOpenAI

            self._llm_cache[model_name] = ChatOpenAI(
                model=model_name, temperature=0.0
            )
        return self._llm_cache[model_name]

    def _rank_scores(
        self,
        config: EvalConfig,
        contexts: list[str],
        expected_contexts: list[str],
    ) -> dict[str, float]:
        wanted = {m for m in config.metrics if m in RETRIEVAL_RANK_METRICS}
        if not wanted or not expected_contexts:
            return {}

        retrieved_ids = [str(i) for i in range(len(contexts))]
        relevant_ids = [
            str(i)
            for i, text in enumerate(contexts)
            if any(exp.strip() and exp.strip() in text for exp in expected_contexts)
        ]

        calc = RetrievalMetricCalculator()
        available = {
            "hit_rate": lambda: calc.hit_rate(retrieved_ids, relevant_ids),
            "mrr": lambda: calc.mrr(retrieved_ids, relevant_ids),
            "ndcg": lambda: calc.ndcg(retrieved_ids, relevant_ids, k=config.top_k),
        }
        return {m.value: available[m.value]() for m in wanted}
