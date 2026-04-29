"""Qdrant vector store implementation.

Implements VectorStoreInterface for Qdrant database.
"""
from typing import Dict, List, Optional
from uuid import uuid4

from qdrant_client import AsyncQdrantClient, models

from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId, SearchFilter
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class QdrantVectorStore(VectorStoreInterface):
    """Qdrant implementation of VectorStoreInterface."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        embedding: EmbeddingInterface,
        collection_name: str,
    ) -> None:
        self._client = client
        self._embedding = embedding
        self._collection_name = collection_name

    async def ensure_collection(self, vector_size: int) -> None:
        """Ensure collection exists, create if not."""
        collections = await self._client.get_collections()
        existing_names = [c.name for c in collections.collections]

        if self._collection_name not in existing_names:
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    async def add_documents(self, documents: List[Document]) -> List[DocumentId]:
        """Add documents to the vector store."""
        if not documents:
            return []

        # 첫 문서의 벡터 크기로 컬렉션 생성
        await self.ensure_collection(len(documents[0].vector))

        points = []
        doc_ids = []

        for doc in documents:
            doc_id = doc.id.value if doc.id is not None else str(uuid4())
            doc_ids.append(DocumentId(doc_id))

            payload = {"content": doc.content, **doc.metadata}
            point = models.PointStruct(id=doc_id, vector=doc.vector, payload=payload)
            points.append(point)

        try:
            await self._client.upsert(
                collection_name=self._collection_name, points=points
            )
        except Exception as e:
            logger.error(
                "Failed to add documents",
                exception=e,
                collection=self._collection_name,
                count=len(documents),
            )
            raise

        return doc_ids

    async def search_by_vector(
        self,
        vector: List[float],
        top_k: int = 10,
        filter: Optional[SearchFilter] = None,
    ) -> List[Document]:
        """Search for similar documents using a vector."""
        query_filter = self._build_qdrant_filter(filter) if filter else None

        try:
            response = await self._client.query_points(
                collection_name=self._collection_name,
                query=vector,
                limit=top_k,
                query_filter=query_filter,
                with_vectors=True,
            )
            return [self._point_to_document(point) for point in response.points]
        except Exception as e:
            logger.error(
                "Vector search failed", exception=e, collection=self._collection_name
            )
            raise

    async def search_by_text(
        self,
        text: str,
        top_k: int = 10,
        filter: Optional[SearchFilter] = None,
    ) -> List[Document]:
        """Search for similar documents using text."""
        vector = await self._embedding.embed_text(text)
        return await self.search_by_vector(vector, top_k, filter)

    async def delete_by_ids(self, ids: List[DocumentId]) -> int:
        """Delete documents by their IDs."""
        id_values = [doc_id.value for doc_id in ids]

        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(points=id_values),
            )
        except Exception as e:
            logger.error(
                "Failed to delete by IDs",
                exception=e,
                collection=self._collection_name,
            )
            raise

        return len(ids)

    async def delete_by_metadata(self, metadata_filter: Dict[str, str]) -> int:
        """Delete documents matching metadata criteria."""
        conditions = [
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in metadata_filter.items()
        ]
        qdrant_filter = models.Filter(must=conditions)

        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(filter=qdrant_filter),
        )
        return 0

    async def get_by_id(self, doc_id: DocumentId) -> Optional[Document]:
        """Retrieve a single document by its ID."""
        results = await self._client.retrieve(
            collection_name=self._collection_name,
            ids=[doc_id.value],
            with_vectors=True,
        )

        if not results:
            return None
        return self._point_to_document(results[0], include_score=False)

    def _build_qdrant_filter(self, search_filter: SearchFilter) -> models.Filter:
        conditions = []

        if search_filter.document_type is not None:
            conditions.append(
                models.FieldCondition(
                    key="document_type",
                    match=models.MatchValue(value=search_filter.document_type.value),
                )
            )

        for key, value in search_filter.metadata.items():
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )

        return models.Filter(must=conditions) if conditions else None

    def _point_to_document(self, point, include_score: bool = True) -> Document:
        payload = point.payload or {}
        content = payload.pop("content", "")
        metadata = {k: str(v) for k, v in payload.items()}
        score = point.score if include_score and hasattr(point, "score") else None

        return Document(
            id=DocumentId(str(point.id)),
            content=content,
            vector=list(point.vector) if point.vector else [],
            metadata=metadata,
            score=score,
        )
