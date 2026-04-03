"""Parent-Child retriever implementation.

Extends QdrantRetriever with Parent-Child hierarchy search support.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from qdrant_client import AsyncQdrantClient

from src.infrastructure.retriever.qdrant_retriever import QdrantRetriever
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.vector.interfaces import EmbeddingInterface
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId


@dataclass
class ParentChildResult:
    """Result containing child document with its parent.

    Attributes:
        child: The retrieved child chunk
        parent: The parent document containing this child
        score: Similarity score of the child
        sibling_count: Number of children sharing the same parent
    """

    child: Document
    parent: Document
    score: float
    sibling_count: int


class ParentChildRetriever(QdrantRetriever):
    """Retriever with Parent-Child hierarchy support.

    Extends QdrantRetriever to support:
    - Child-first retrieval with parent document fetching
    - Sibling count calculation
    - Parent-based children retrieval
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
        embedding: EmbeddingInterface,
        score_threshold: Optional[float] = None,
    ) -> None:
        """Initialize ParentChildRetriever.

        Args:
            client: Async Qdrant client
            collection_name: Name of the Qdrant collection
            embedding: Embedding interface for text conversion
            score_threshold: Optional minimum similarity score (0-1)
        """
        super().__init__(client, collection_name, embedding, score_threshold)

    def get_retriever_name(self) -> str:
        """Get the name of this retriever implementation.

        Returns:
            Name identifying this retriever
        """
        return "parent-child-retriever"

    async def retrieve_with_parent(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
    ) -> List[ParentChildResult]:
        """Retrieve children and fetch their parent documents.

        Searches for child chunks first, then fetches their parent documents.
        Multiple children with the same parent share the parent instance.

        Args:
            query: The search query text
            top_k: Maximum number of child documents to return (default: 10)
            filters: Optional metadata filters to apply

        Returns:
            List of ParentChildResult sorted by child similarity score
        """
        # Force search on children only
        child_filters = self._merge_child_filter(filters)

        # Search for children
        children_with_scores = await self.retrieve_with_scores(
            query, top_k, child_filters
        )

        if not children_with_scores:
            return []

        # Extract unique parent IDs and count siblings
        parent_id_to_children: Dict[str, List[Tuple[Document, float]]] = defaultdict(
            list
        )
        for child, score in children_with_scores:
            parent_id = child.metadata.get("parent_id")
            if parent_id:
                parent_id_to_children[parent_id].append((child, score))

        # Fetch parent documents
        parent_ids = list(parent_id_to_children.keys())
        parents = await self._fetch_parents(parent_ids)

        # Build results
        results: List[ParentChildResult] = []
        for parent_id, children in parent_id_to_children.items():
            parent = parents.get(parent_id)
            if parent is None:
                # Create placeholder parent if not found
                parent = Document(
                    id=DocumentId(parent_id),
                    content="[Parent not found]",
                    vector=[0.0] * self._embedding.get_dimension(),
                    metadata={"chunk_type": "parent"},
                )

            sibling_count = len(children)
            for child, score in children:
                results.append(
                    ParentChildResult(
                        child=child,
                        parent=parent,
                        score=score,
                        sibling_count=sibling_count,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def retrieve_children_by_parent(
        self,
        parent_id: str,
        top_k: int = 10,
    ) -> List[Document]:
        """Retrieve all children for a specific parent.

        Args:
            parent_id: The parent document ID
            top_k: Maximum number of children to return (default: 10)

        Returns:
            List of child documents belonging to the parent
        """
        filters = MetadataFilter(parent_id=parent_id, chunk_type="child")
        return await self.retrieve_by_metadata(filters, top_k)

    def _merge_child_filter(
        self, filters: Optional[MetadataFilter]
    ) -> MetadataFilter:
        """Merge user filters with child chunk type filter.

        Args:
            filters: Optional user-provided filters

        Returns:
            Filters with chunk_type set to 'child'
        """
        child_filter = MetadataFilter(chunk_type="child")
        if filters is not None:
            return filters.merge(child_filter)
        return child_filter

    async def _fetch_parents(
        self, parent_ids: List[str]
    ) -> Dict[str, Document]:
        """Fetch parent documents by their IDs.

        Args:
            parent_ids: List of parent document IDs

        Returns:
            Dict mapping parent_id to Document
        """
        if not parent_ids:
            return {}

        parents: Dict[str, Document] = {}

        # Try to retrieve all parents by their IDs directly
        try:
            results = await self._client.retrieve(
                collection_name=self._collection_name,
                ids=parent_ids,
                with_vectors=True,
            )
            for record in results:
                record_id = str(record.id)
                parents[record_id] = self._record_to_document(record)
        except Exception:
            # Fallback to scroll if retrieve fails
            records, _ = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=MetadataFilter(chunk_type="parent").to_qdrant_filter(),
                limit=len(parent_ids) * 2,
                with_vectors=True,
            )
            for record in records:
                record_id = str(record.id)
                if record_id in parent_ids:
                    parents[record_id] = self._record_to_document(record)

        return parents
