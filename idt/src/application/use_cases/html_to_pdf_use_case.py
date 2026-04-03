"""HTML → PDF 변환 UseCase.

converter.convert()는 sync 함수이므로 asyncio.to_thread()로 래핑한다.
"""
import asyncio

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_export.interfaces import HtmlToPdfConverterInterface
from src.domain.pdf_export.schemas import HtmlToPdfRequest, HtmlToPdfResult


class HtmlToPdfUseCase:
    """HTML 콘텐츠를 PDF bytes로 변환하는 UseCase."""

    def __init__(
        self,
        converter: HtmlToPdfConverterInterface,
        logger: LoggerInterface,
    ) -> None:
        self._converter = converter
        self._logger = logger

    async def convert(self, request: HtmlToPdfRequest) -> HtmlToPdfResult:
        """HTML → PDF 변환을 실행한다.

        Args:
            request: 변환 요청 (html_content, filename, css, base_url 포함)

        Returns:
            HtmlToPdfResult (pdf_bytes, size_bytes, converter_used 포함)

        Raises:
            RuntimeError: 변환 라이브러리 오류 발생 시
        """
        self._logger.info(
            "HTML to PDF conversion started",
            request_id=request.request_id,
            filename=request.filename,
            user_id=request.user_id,
            converter=self._converter.get_converter_name(),
        )

        try:
            pdf_bytes = await asyncio.to_thread(
                self._converter.convert,
                html_content=request.html_content,
                css_content=request.css_content,
                base_url=request.base_url,
            )

            self._logger.info(
                "HTML to PDF conversion completed",
                request_id=request.request_id,
                filename=request.filename,
                size_bytes=len(pdf_bytes),
            )

            return HtmlToPdfResult(
                filename=request.filename,
                user_id=request.user_id,
                request_id=request.request_id,
                pdf_bytes=pdf_bytes,
                size_bytes=len(pdf_bytes),
                converter_used=self._converter.get_converter_name(),
            )

        except Exception as exc:
            self._logger.error(
                "HTML to PDF conversion failed",
                exception=exc,
                request_id=request.request_id,
                filename=request.filename,
            )
            raise
