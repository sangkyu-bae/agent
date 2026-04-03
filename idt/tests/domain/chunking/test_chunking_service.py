"""Tests for ChunkingService domain service.

Domain tests: no mocks. FakeLogger and StubStrategy are concrete implementations.
"""
import pytest
from typing import List

from langchain_core.documents import Document

from src.domain.chunking.services.chunking_service import ChunkingService
from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


# ── Test doubles (concrete, not mocks) ───────────────────────────────────────

class FakeLogger(LoggerInterface):
    """Concrete logger that captures calls for assertion."""

    def __init__(self):
        self.calls: list = []

    def debug(self, message: str, **kwargs) -> None:
        self.calls.append(("debug", message, kwargs))

    def info(self, message: str, **kwargs) -> None:
        self.calls.append(("info", message, kwargs))

    def warning(self, message: str, **kwargs) -> None:
        self.calls.append(("warning", message, kwargs))

    def error(self, message: str, exception: Exception | None = None, **kwargs) -> None:
        self.calls.append(("error", message, exception, kwargs))

    def critical(self, message: str, exception: Exception | None = None, **kwargs) -> None:
        self.calls.append(("critical", message, exception, kwargs))

    def info_messages(self) -> list[str]:
        return [msg for level, msg, *_ in self.calls if level == "info"]

    def error_messages(self) -> list[str]:
        return [msg for level, msg, *_ in self.calls if level == "error"]

    def error_exceptions(self) -> list:
        return [exc for level, msg, exc, *_ in self.calls if level == "error"]


class PassThroughStrategy(ChunkingStrategy):
    """Strategy that returns documents unchanged."""

    def chunk(self, documents: List[Document]) -> List[Document]:
        return documents

    def get_strategy_name(self) -> str:
        return "pass_through"

    def get_chunk_size(self) -> int:
        return 100


class DoubleChunkStrategy(ChunkingStrategy):
    """Strategy that duplicates each document."""

    def chunk(self, documents: List[Document]) -> List[Document]:
        return documents + documents

    def get_strategy_name(self) -> str:
        return "double"

    def get_chunk_size(self) -> int:
        return 100


class BrokenStrategy(ChunkingStrategy):
    """Strategy that always raises an exception."""

    def chunk(self, documents: List[Document]) -> List[Document]:
        raise RuntimeError("strategy failure")

    def get_strategy_name(self) -> str:
        return "broken"

    def get_chunk_size(self) -> int:
        return 100


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestChunkingService:
    """Tests for ChunkingService."""

    @pytest.fixture
    def logger(self):
        return FakeLogger()

    @pytest.fixture
    def service(self, logger):
        return ChunkingService(logger)

    @pytest.fixture
    def docs(self):
        return [
            Document(page_content="alpha content", metadata={"doc_id": "a"}),
            Document(page_content="beta content", metadata={"doc_id": "b"}),
        ]

    # ── 기본 위임 동작 ──────────────────────────────────────────────────────

    def test_returns_strategy_output(self, service, docs):
        """chunk_documents should return whatever the strategy produces."""
        result = service.chunk_documents(docs, PassThroughStrategy())
        assert result == docs

    def test_delegates_to_strategy_chunk(self, service, docs):
        """chunk_documents should produce result from strategy.chunk."""
        result = service.chunk_documents(docs, DoubleChunkStrategy())
        assert len(result) == len(docs) * 2

    def test_empty_document_list(self, service):
        """Empty document list should return empty list."""
        result = service.chunk_documents([], PassThroughStrategy())
        assert result == []

    # ── 로깅 ────────────────────────────────────────────────────────────────

    def test_logs_info_on_start(self, service, logger, docs):
        """Should log INFO when chunking starts."""
        service.chunk_documents(docs, PassThroughStrategy())
        assert any("start" in msg.lower() for msg in logger.info_messages())

    def test_logs_info_on_completion(self, service, logger, docs):
        """Should log INFO when chunking completes."""
        service.chunk_documents(docs, PassThroughStrategy())
        assert any("complet" in msg.lower() for msg in logger.info_messages())

    def test_logs_strategy_name_on_start(self, service, logger, docs):
        """Start log should include strategy name in kwargs."""
        service.chunk_documents(docs, PassThroughStrategy())
        start_calls = [
            kwargs for level, msg, kwargs in logger.calls
            if level == "info" and "start" in msg.lower()
        ]
        assert len(start_calls) >= 1
        assert start_calls[0].get("strategy") == "pass_through"

    def test_logs_chunk_count_on_completion(self, service, logger):
        """Completion log should include resulting chunk count in kwargs."""
        docs = [Document(page_content="a"), Document(page_content="b")]
        service.chunk_documents(docs, DoubleChunkStrategy())
        completion_calls = [
            kwargs for level, msg, kwargs in logger.calls
            if level == "info" and "complet" in msg.lower()
        ]
        assert len(completion_calls) >= 1
        assert completion_calls[0].get("chunk_count") == 4

    # ── 에러 처리 ────────────────────────────────────────────────────────────

    def test_reraises_exception_from_strategy(self, service, docs):
        """Exception from strategy should propagate after logging."""
        with pytest.raises(RuntimeError, match="strategy failure"):
            service.chunk_documents(docs, BrokenStrategy())

    def test_logs_error_with_exception_on_failure(self, service, logger, docs):
        """Should log ERROR with exception when strategy raises."""
        with pytest.raises(RuntimeError):
            service.chunk_documents(docs, BrokenStrategy())

        assert len(logger.error_messages()) >= 1
        exceptions = logger.error_exceptions()
        assert any(isinstance(exc, RuntimeError) for exc in exceptions)
