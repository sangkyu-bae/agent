"""문서→QA 초안 생성 UseCase (eval-hub Design A6).

draft만 반환하고 저장하지 않는다 — 사용자가 검토·수정 후 create API로 저장.
LLM 입력은 max_input_chars로 절단(doc-extractor 429 방지 선례).
"""
from typing import Callable, Protocol

from src.application.ragas.schemas import GeneratedTestsetDraft
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# (file_bytes, filename) -> 본문 텍스트. 실패는 ValueError.
DocumentTextExtractor = Callable[[bytes, str], str]


class QAGeneratorInterface(Protocol):
    async def generate(
        self, text: str, max_pairs: int, request_id: str
    ) -> list[dict]: ...


class TestsetGenerateUseCase:
    def __init__(
        self,
        text_extractor: DocumentTextExtractor,
        qa_generator: QAGeneratorInterface,
        logger: LoggerInterface,
        max_input_chars: int,
        max_pairs: int,
        max_file_bytes: int = 15 * 1024 * 1024,
    ) -> None:
        self._text_extractor = text_extractor
        self._qa_generator = qa_generator
        self._logger = logger
        self._max_input_chars = max_input_chars
        self._max_pairs = max_pairs
        self._max_file_bytes = max_file_bytes

    async def execute(
        self,
        file_bytes: bytes,
        filename: str,
        requested_pairs: int,
        request_id: str,
    ) -> GeneratedTestsetDraft:
        if len(file_bytes) > self._max_file_bytes:
            raise ValueError(
                f"파일이 너무 큽니다 (최대 {self._max_file_bytes // (1024 * 1024)}MB)"
            )
        text = self._text_extractor(file_bytes, filename)
        if not text or not text.strip():
            raise ValueError("문서에서 텍스트를 추출하지 못했습니다")

        truncated = text[: self._max_input_chars]
        if len(text) > self._max_input_chars:
            self._logger.info(
                "QA generation input truncated",
                request_id=request_id,
                original_chars=len(text),
                cap=self._max_input_chars,
            )

        effective_pairs = min(max(1, requested_pairs), self._max_pairs)
        items = await self._qa_generator.generate(
            text=truncated, max_pairs=effective_pairs, request_id=request_id
        )
        return GeneratedTestsetDraft(source_filename=filename, items=items)
