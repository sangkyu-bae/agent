"""섹션 구조를 인식하는 청킹 전략."""
from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker


class SectionAwareChunkingStrategy(ChunkingStrategy):
    """섹션/표 인식 청킹 전략.

    분할 우선순위:
    1. section_title 경계
    2. paragraph 단위 (\\n\\n)
    3. table 단독 chunk
    4. token limit 초과 시 토큰 기반 분할
    5. 짧은 chunk 병합
    """

    def __init__(
        self,
        config: ChunkingConfig,
        min_chunk_size: int = 100,
    ) -> None:
        self._config = config
        self._min_chunk_size = min_chunk_size
        self._chunker = BaseTokenChunker(config)

    def chunk(self, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        section_groups = self._group_by_section(documents)

        chunks: list[Document] = []
        for section_title, docs in section_groups:
            chunks.extend(self._chunk_section(docs))

        return self._merge_short_chunks(chunks)

    def _group_by_section(
        self, documents: list[Document]
    ) -> list[tuple[str, list[Document]]]:
        groups: list[tuple[str, list[Document]]] = []
        current_title = ""
        current_docs: list[Document] = []

        for doc in documents:
            title = doc.metadata.get("section_title", "")
            if title != current_title and current_docs:
                groups.append((current_title, current_docs))
                current_docs = []
            current_title = title
            current_docs.append(doc)

        if current_docs:
            groups.append((current_title, current_docs))

        return groups

    def _chunk_section(
        self, docs: list[Document]
    ) -> list[Document]:
        result: list[Document] = []
        for doc in docs:
            has_table = doc.metadata.get("has_table", False)
            block_type = doc.metadata.get("block_type", "paragraph")

            if block_type == "table" or has_table:
                result.append(doc)
            elif (
                self._chunker.count_tokens(doc.page_content)
                > self._config.chunk_size
            ):
                result.extend(self._split_large_document(doc))
            else:
                result.append(doc)

        return result

    def _split_large_document(
        self, doc: Document
    ) -> list[Document]:
        paragraphs = [
            p.strip()
            for p in doc.page_content.split("\n\n")
            if p.strip()
        ]

        if not paragraphs:
            return self._split_by_tokens(doc)

        chunks: list[Document] = []
        current_text = ""

        for para in paragraphs:
            candidate = (
                (current_text + "\n\n" + para).strip()
                if current_text
                else para
            )
            if (
                self._chunker.count_tokens(candidate)
                > self._config.chunk_size
            ):
                if current_text:
                    chunks.append(
                        self._create_chunk(doc, current_text, len(chunks))
                    )
                if (
                    self._chunker.count_tokens(para)
                    > self._config.chunk_size
                ):
                    for sub in self._chunker.split_by_tokens(para):
                        chunks.append(
                            self._create_chunk(doc, sub, len(chunks))
                        )
                    current_text = ""
                else:
                    current_text = para
            else:
                current_text = candidate

        if current_text:
            chunks.append(
                self._create_chunk(doc, current_text, len(chunks))
            )

        return chunks

    def _split_by_tokens(self, doc: Document) -> list[Document]:
        token_chunks = self._chunker.split_by_tokens(doc.page_content)
        return [
            self._create_chunk(doc, text, idx)
            for idx, text in enumerate(token_chunks)
        ]

    def _create_chunk(
        self, original: Document, text: str, chunk_index: int
    ) -> Document:
        meta = self._chunker.merge_metadata(
            original.metadata,
            {
                "chunk_type": "section_aware",
                "chunk_index": chunk_index,
            },
        )
        return Document(page_content=text, metadata=meta)

    def _merge_short_chunks(
        self, chunks: list[Document]
    ) -> list[Document]:
        if not chunks:
            return []

        merged: list[Document] = []
        current = chunks[0]

        for next_chunk in chunks[1:]:
            current_tokens = self._chunker.count_tokens(
                current.page_content
            )
            if current_tokens < self._min_chunk_size:
                current_section = current.metadata.get("section_title", "")
                next_section = next_chunk.metadata.get("section_title", "")
                if current_section == next_section:
                    merged_text = (
                        current.page_content
                        + "\n\n"
                        + next_chunk.page_content
                    )
                    current = Document(
                        page_content=merged_text,
                        metadata=current.metadata,
                    )
                    continue

            merged.append(current)
            current = next_chunk

        merged.append(current)
        return merged

    def get_strategy_name(self) -> str:
        return "section_aware"

    def get_chunk_size(self) -> int:
        return self._config.chunk_size
