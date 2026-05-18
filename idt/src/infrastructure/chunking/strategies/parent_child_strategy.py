"""Parent-child chunking strategy implementation."""
import uuid
from typing import TYPE_CHECKING, List, Optional

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker

if TYPE_CHECKING:
    from src.infrastructure.chunking.table_flattening.preprocessor import (
        TableFlatteningPreprocessor,
    )


class ParentChildStrategy(ChunkingStrategy):
    """Chunking strategy that creates parent-child hierarchical chunks."""

    def __init__(
        self,
        parent_config: ChunkingConfig,
        child_config: ChunkingConfig,
        table_preprocessor: Optional["TableFlatteningPreprocessor"] = None,
    ):
        self._parent_config = parent_config
        self._child_config = child_config
        self._parent_chunker = BaseTokenChunker(parent_config)
        self._child_chunker = BaseTokenChunker(child_config)
        self._table_preprocessor = table_preprocessor

    def chunk(self, documents: List[Document]) -> List[Document]:
        """Split documents into parent-child hierarchical chunks."""
        if not documents:
            return []

        result = []
        for doc in documents:
            doc_chunks = self._chunk_document(doc)
            result.extend(doc_chunks)

        return result

    def _chunk_document(self, doc: Document) -> List[Document]:
        has_table = doc.metadata.get("has_table", False)

        if has_table and self._table_preprocessor:
            section_title = doc.metadata.get("section_title", "")
            preprocess = self._table_preprocessor.process(
                doc.page_content, section_title
            )
            if preprocess.table_count > 0:
                return self._chunk_with_table_flattening(doc, preprocess)

        return self._chunk_default(doc)

    def _chunk_default(self, doc: Document) -> List[Document]:
        content = doc.page_content
        if not content:
            return []

        result = []
        parent_texts = self._parent_chunker.split_by_tokens(content)

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = self._generate_chunk_id()
            child_texts = self._child_chunker.split_by_tokens(parent_text)
            children_ids = []
            child_docs = []

            for child_idx, child_text in enumerate(child_texts):
                child_id = self._generate_chunk_id()
                children_ids.append(child_id)

                child_metadata = self._parent_chunker.merge_metadata(
                    doc.metadata,
                    {
                        "chunk_type": "child",
                        "chunk_id": child_id,
                        "chunk_index": child_idx,
                        "total_chunks": len(child_texts),
                        "parent_id": parent_id,
                    },
                )
                child_docs.append(
                    Document(page_content=child_text, metadata=child_metadata)
                )

            parent_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "parent",
                    "chunk_id": parent_id,
                    "chunk_index": parent_idx,
                    "total_chunks": len(parent_texts),
                    "children_ids": children_ids,
                },
            )
            parent_doc = Document(page_content=parent_text, metadata=parent_metadata)

            result.append(parent_doc)
            result.extend(child_docs)

        children = [d for d in result if d.metadata.get("chunk_type") == "child"]
        for i, child in enumerate(children):
            child.metadata["chunk_index"] = i
        for child in children:
            child.metadata["total_chunks"] = len(children)

        return result

    def _chunk_with_table_flattening(
        self, doc: Document, preprocess
    ) -> List[Document]:
        """부모=원본 markdown, 자식=의미 문장 버전으로 청킹."""
        result = []

        parent_texts = self._parent_chunker.split_by_tokens(
            preprocess.parent_text
        )
        child_texts = self._child_chunker.split_by_tokens(
            preprocess.child_text
        )

        if len(parent_texts) == 1:
            result.extend(
                self._build_single_parent_group(
                    doc, parent_texts[0], child_texts, preprocess
                )
            )
        else:
            result.extend(
                self._build_multi_parent_groups(
                    doc, parent_texts, child_texts, preprocess
                )
            )

        return result

    def _build_single_parent_group(
        self, doc, parent_text, child_texts, preprocess
    ) -> List[Document]:
        result = []
        parent_id = self._generate_chunk_id()
        children_ids = []
        child_docs = []

        for child_idx, child_text in enumerate(child_texts):
            child_id = self._generate_chunk_id()
            children_ids.append(child_id)
            child_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "child",
                    "chunk_id": child_id,
                    "chunk_index": child_idx,
                    "total_chunks": len(child_texts),
                    "parent_id": parent_id,
                    "table_flattened": True,
                },
            )
            child_docs.append(
                Document(page_content=child_text, metadata=child_metadata)
            )

        parent_metadata = self._parent_chunker.merge_metadata(
            doc.metadata,
            {
                "chunk_type": "parent",
                "chunk_id": parent_id,
                "chunk_index": 0,
                "total_chunks": 1,
                "children_ids": children_ids,
                "table_count": preprocess.table_count,
                **preprocess.metadata,
            },
        )
        result.append(
            Document(page_content=parent_text, metadata=parent_metadata)
        )
        result.extend(child_docs)
        return result

    def _build_multi_parent_groups(
        self, doc, parent_texts, child_texts, preprocess
    ) -> List[Document]:
        result = []
        children_per_parent = max(1, len(child_texts) // len(parent_texts))
        child_offset = 0

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = self._generate_chunk_id()

            if parent_idx == len(parent_texts) - 1:
                assigned = child_texts[child_offset:]
            else:
                assigned = child_texts[
                    child_offset : child_offset + children_per_parent
                ]

            children_ids = []
            child_docs = []

            for local_idx, child_text in enumerate(assigned):
                child_id = self._generate_chunk_id()
                children_ids.append(child_id)
                child_metadata = self._parent_chunker.merge_metadata(
                    doc.metadata,
                    {
                        "chunk_type": "child",
                        "chunk_id": child_id,
                        "chunk_index": child_offset + local_idx,
                        "total_chunks": len(child_texts),
                        "parent_id": parent_id,
                        "table_flattened": True,
                    },
                )
                child_docs.append(
                    Document(page_content=child_text, metadata=child_metadata)
                )

            parent_metadata = self._parent_chunker.merge_metadata(
                doc.metadata,
                {
                    "chunk_type": "parent",
                    "chunk_id": parent_id,
                    "chunk_index": parent_idx,
                    "total_chunks": len(parent_texts),
                    "children_ids": children_ids,
                    "table_count": preprocess.table_count,
                    **preprocess.metadata,
                },
            )
            result.append(
                Document(page_content=parent_text, metadata=parent_metadata)
            )
            result.extend(child_docs)
            child_offset += len(assigned)

        return result

    def _generate_chunk_id(self) -> str:
        return str(uuid.uuid4())

    def get_strategy_name(self) -> str:
        return "parent_child"

    def get_chunk_size(self) -> int:
        return self._child_config.chunk_size
