from src.domain.pdf_analyzer.schemas import PDFDocumentType
from src.domain.pdf_routing.policies import ParserRoutingPolicy
from src.domain.pdf_routing.schemas import RoutingReason
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from tests.domain.pdf_routing.conftest import make_analysis_result


class TestParserRoutingPolicy:

    def test_text_heavy_routes_to_pymupdf(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH
        assert decision.is_fallback is False

    def test_ocr_heavy_routes_to_llamaparser(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.OCR_HEAVY, confidence=0.9
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "llamaparser"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH

    def test_table_heavy_routes_to_pymupdf4llm(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.TABLE_HEAVY, confidence=0.7
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf4llm"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH

    def test_multimodal_routes_to_llamaparser(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.MULTIMODAL, confidence=0.6
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "llamaparser"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH

    def test_low_confidence_fallback(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.OCR_HEAVY, confidence=0.3
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf"
        assert decision.reason == RoutingReason.LOW_CONFIDENCE_FALLBACK
        assert decision.is_fallback is True

    def test_no_analysis_fallback(self) -> None:
        decision = ParserRoutingPolicy.decide(None, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf"
        assert decision.reason == RoutingReason.NO_ANALYSIS_FALLBACK
        assert decision.is_fallback is True
        assert decision.document_type is None
        assert decision.confidence == 0.0

    def test_boundary_confidence_at_threshold(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.TABLE_HEAVY, confidence=0.5
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf4llm"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH
        assert decision.is_fallback is False

    def test_boundary_confidence_below_threshold(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.TABLE_HEAVY, confidence=0.49
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.parser_type == "pymupdf"
        assert decision.reason == RoutingReason.LOW_CONFIDENCE_FALLBACK
        assert decision.is_fallback is True

    def test_custom_config_override(self) -> None:
        config = ParserRoutingConfig(
            routing_map={"text_heavy": "docling"},
            fallback_parser="pymupdf",
        )
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = ParserRoutingPolicy.decide(result, config)
        assert decision.parser_type == "docling"

    def test_custom_fallback_parser(self) -> None:
        config = ParserRoutingConfig(fallback_parser="pymupdf4llm")
        decision = ParserRoutingPolicy.decide(None, config)
        assert decision.parser_type == "pymupdf4llm"

    def test_custom_threshold(self) -> None:
        config = ParserRoutingConfig(confidence_threshold=0.8)
        result = make_analysis_result(
            document_type=PDFDocumentType.OCR_HEAVY, confidence=0.6
        )
        decision = ParserRoutingPolicy.decide(result, config)
        assert decision.parser_type == "pymupdf"
        assert decision.is_fallback is True

    def test_unknown_document_type_fallback(self) -> None:
        config = ParserRoutingConfig(routing_map={"text_heavy": "pymupdf"})
        result = make_analysis_result(
            document_type=PDFDocumentType.OCR_HEAVY, confidence=0.9
        )
        decision = ParserRoutingPolicy.decide(result, config)
        assert decision.parser_type == "pymupdf"
        assert decision.is_fallback is True

    def test_decision_preserves_document_type(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.MULTIMODAL, confidence=0.7
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.document_type == "multimodal"

    def test_decision_preserves_confidence(self) -> None:
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.85
        )
        decision = ParserRoutingPolicy.decide(result, ParserRoutingConfig())
        assert decision.confidence == 0.85
