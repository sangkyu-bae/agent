"""Excel upload use case: parse → convert → chunk → store."""
from typing import List

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.excel.interfaces.excel_parser_interface import ExcelParserInterface
from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pipeline.schemas.excel_upload_schema import ExcelUploadResponse
from src.domain.vector.entities import Document as VectorDocument
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface


class ExcelUploadUseCase:
    """Orchestrates Excel file upload: parse → chunk → store in vector DB.

    Responsibilities:
    - Parse Excel bytes via ExcelParserInterface
    - Convert each sheet to LangChain Documents
    - Apply chunking strategy
    - Embed and store chunks in vector store
    """

    def __init__(
        self,
        excel_parser: ExcelParserInterface,
        chunking_strategy: ChunkingStrategy,
        vectorstore: VectorStoreInterface,
        embedding: EmbeddingInterface,
        logger: LoggerInterface,
    ) -> None:
        self._parser = excel_parser
        self._chunking_strategy = chunking_strategy
        self._vectorstore = vectorstore
        self._embedding = embedding
        self._logger = logger

    async def execute(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        request_id: str,
    ) -> ExcelUploadResponse:
        """Execute the Excel upload pipeline.

        Args:
            file_bytes: Raw bytes of the uploaded Excel file.
            filename: Original filename.
            user_id: Owner of the document.
            request_id: Trace ID for logging.

        Returns:
            ExcelUploadResponse with processing results.
        """
        self._logger.info(
            "Excel upload started",
            request_id=request_id,
            filename=filename,
            user_id=user_id,
        )

        try:
            excel_data = self._parser.parse_bytes(file_bytes, filename, user_id)
            documents = self._convert_to_documents(excel_data, user_id)
            chunks = self._chunking_strategy.chunk(documents)
            stored_ids = await self._store_chunks(chunks, user_id)

            self._logger.info(
                "Excel upload completed",
                request_id=request_id,
                filename=filename,
                sheet_count=len(excel_data.sheets),
                chunk_count=len(chunks),
            )

            return ExcelUploadResponse(
                document_id=excel_data.file_id,
                filename=filename,
                sheet_count=len(excel_data.sheets),
                chunk_count=len(chunks),
                stored_ids=stored_ids,
                status="completed",
            )

        except Exception as e:
            self._logger.error(
                "Excel upload failed",
                exception=e,
                request_id=request_id,
                filename=filename,
            )
            return ExcelUploadResponse(
                document_id="",
                filename=filename,
                sheet_count=0,
                chunk_count=0,
                stored_ids=[],
                status="failed",
                errors=[str(e)],
            )

    def _convert_to_documents(
        self, excel_data: ExcelData, user_id: str
    ) -> List[Document]:
        """Convert each sheet in ExcelData to a LangChain Document.

        Each sheet becomes one Document where content is a line-per-row
        key-value text representation.
        """
        docs = []
        for sheet_name, sheet in excel_data.sheets.items():
            content = self._sheet_to_text(sheet)
            doc = Document(
                page_content=content,
                metadata={
                    "file_id": excel_data.file_id,
                    "filename": excel_data.filename,
                    "sheet_name": sheet_name,
                    "user_id": user_id,
                    "row_count": sheet.row_count,
                },
            )
            docs.append(doc)
        return docs

    def _sheet_to_text(self, sheet: SheetData) -> str:
        """Serialize sheet rows to text.

        Format: "col1: val1 | col2: val2" per row, newline-separated.
        """
        lines = []
        for row in sheet.data:
            parts = [f"{col}: {row.get(col, '')}" for col in sheet.columns]
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    async def _store_chunks(
        self, chunks: List[Document], user_id: str
    ) -> List[str]:
        """Embed and store chunks in vector store.

        Returns list of stored document ID strings.
        """
        if not chunks:
            return []

        texts = [chunk.page_content for chunk in chunks]
        vectors = await self._embedding.embed_documents(texts)

        vector_docs = []
        for chunk, vector in zip(chunks, vectors):
            metadata = dict(chunk.metadata)
            metadata["user_id"] = user_id
            vector_docs.append(
                VectorDocument(id=None, content=chunk.page_content, vector=vector, metadata=metadata)
            )

        stored_ids = await self._vectorstore.add_documents(vector_docs)
        return [doc_id.value for doc_id in stored_ids]
