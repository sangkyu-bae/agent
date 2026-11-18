"""OpenAIEntityEmbedder — 엔티티 이름 임베딩(차원 지정).

Design Ref: graph-rag-foundation §3.2·§11.4 V5 — 기존 OpenAIEmbedding 래퍼는 차원을
지정할 수 없어 그래프 전용으로 둔다. Aura Free 용량 때문에 512차원(설정값)을 쓰며,
Neo4j 벡터 인덱스 차원과 같아야 한다.
"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from src.domain.graph_rag.interfaces import EntityEmbedderPort


class OpenAIEntityEmbedder(EntityEmbedderPort):
    def __init__(
        self, model_name: str, dimensions: int, *, api_key: str | None = None
    ) -> None:
        kwargs = {"model": model_name, "dimensions": dimensions}
        if api_key:
            kwargs["api_key"] = api_key
        self._embeddings = OpenAIEmbeddings(**kwargs)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embeddings.aembed_documents(texts)
