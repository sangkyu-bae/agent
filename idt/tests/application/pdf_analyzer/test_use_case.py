from unittest.mock import Mock

import pytest

from src.application.pdf_analyzer.schemas import AnalyzePDFRequest
from src.application.pdf_analyzer.use_case import AnalyzePDFUseCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


def _make_mock_result() -> AnalysisResult:
    return AnalysisResult(
        document_type=PDFDocumentType.TEXT_HEAVY,
        confidence=0.95,
        total_pages=10,
        sampled_pages=5,
        page_features=[
            PageFeatures(
                page_number=i,
                text_char_count=1500,
                image_count=0,
                image_area_ratio=0.0,
                table_count=0,
                has_extractable_text=True,
            )
            for i in range(1, 6)
        ],
        summary_metrics=SummaryMetrics(
            avg_text_chars=1500.0,
            avg_image_count=0.0,
            avg_image_area_ratio=0.0,
            avg_table_count=0.0,
            extractable_text_ratio=1.0,
        ),
    )


@pytest.fixture
def mock_analyzer():
    analyzer = Mock(spec=PDFAnalyzerInterface)
    analyzer.analyze_bytes.return_value = _make_mock_result()
    analyzer.analyze_path.return_value = _make_mock_result()
    return analyzer


@pytest.fixture
def mock_logger():
    return Mock(spec=LoggerInterface)


class TestAnalyzePDFUseCase:
    @pytest.mark.asyncio
    async def test_execute_bytes_success(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
        )
        response = await use_case.execute(request)
        assert response.document_type == "text_heavy"
        assert response.confidence == 0.95
        assert response.total_pages == 10
        assert response.sampled_pages == 5
        assert response.request_id == "req1"
        mock_analyzer.analyze_bytes.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_path_success(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_path="/tmp/test.pdf",
        )
        response = await use_case.execute(request)
        assert response.document_type == "text_heavy"
        mock_analyzer.analyze_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_logging(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
        )
        await use_case.execute(request)
        assert mock_logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_error_logging(self, mock_logger):
        analyzer = Mock(spec=PDFAnalyzerInterface)
        analyzer.analyze_bytes.side_effect = RuntimeError("parse error")
        use_case = AnalyzePDFUseCase(analyzer=analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
        )
        with pytest.raises(RuntimeError, match="parse error"):
            await use_case.execute(request)
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_no_input_raises(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
        )
        with pytest.raises(ValueError, match="Either file_bytes or file_path"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_with_sample_pages(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
            sample_pages=3,
        )
        await use_case.execute(request)
        call_kwargs = mock_analyzer.analyze_bytes.call_args
        config = call_kwargs.kwargs.get("config")
        assert config is not None
        assert config.sample_pages == 3

    @pytest.mark.asyncio
    async def test_execute_with_explicit_config(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
        )
        config = AnalysisConfig(sample_pages=7)
        await use_case.execute(request, config=config)
        call_kwargs = mock_analyzer.analyze_bytes.call_args
        passed_config = call_kwargs.kwargs.get("config")
        assert passed_config.sample_pages == 7

    @pytest.mark.asyncio
    async def test_response_flat_metrics(self, mock_analyzer, mock_logger):
        use_case = AnalyzePDFUseCase(analyzer=mock_analyzer, logger=mock_logger)
        request = AnalyzePDFRequest(
            filename="test.pdf",
            user_id="user1",
            request_id="req1",
            file_bytes=b"fake-pdf",
        )
        response = await use_case.execute(request)
        assert response.avg_text_chars == 1500.0
        assert response.avg_image_count == 0.0
        assert response.avg_image_area_ratio == 0.0
        assert response.avg_table_count == 0.0
        assert response.extractable_text_ratio == 1.0
