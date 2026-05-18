from src.domain.pdf_analyzer.schemas import PDFDocumentType
from src.domain.pdf_routing.schemas import RoutingReason
from src.domain.pdf_routing.value_objects import ParserRoutingConfig
from src.infrastructure.pdf_routing.default_parser_router import DefaultParserRouter
from tests.domain.pdf_routing.conftest import make_analysis_result


class TestDefaultParserRouter:

    def test_route_with_default_config(self) -> None:
        router = DefaultParserRouter()
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = router.route(result)
        assert decision.parser_type == "pymupdf"
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH

    def test_route_without_analysis(self) -> None:
        router = DefaultParserRouter()
        decision = router.route(None)
        assert decision.parser_type == "pymupdf"
        assert decision.is_fallback is True
        assert decision.reason == RoutingReason.NO_ANALYSIS_FALLBACK

    def test_route_with_constructor_config(self) -> None:
        config = ParserRoutingConfig(
            routing_map={"text_heavy": "docling"},
        )
        router = DefaultParserRouter(config=config)
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = router.route(result)
        assert decision.parser_type == "docling"

    def test_route_with_call_config_override(self) -> None:
        router = DefaultParserRouter()
        override_config = ParserRoutingConfig(
            routing_map={"text_heavy": "docling"},
        )
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = router.route(result, config=override_config)
        assert decision.parser_type == "docling"

    def test_route_config_precedence(self) -> None:
        constructor_config = ParserRoutingConfig(
            routing_map={"text_heavy": "pymupdf4llm"},
        )
        call_config = ParserRoutingConfig(
            routing_map={"text_heavy": "llamaparser"},
        )
        router = DefaultParserRouter(config=constructor_config)
        result = make_analysis_result(
            document_type=PDFDocumentType.TEXT_HEAVY, confidence=0.8
        )
        decision = router.route(result, config=call_config)
        assert decision.parser_type == "llamaparser"

    def test_route_all_document_types(self) -> None:
        router = DefaultParserRouter()
        expected = {
            PDFDocumentType.TEXT_HEAVY: "pymupdf",
            PDFDocumentType.OCR_HEAVY: "llamaparser",
            PDFDocumentType.TABLE_HEAVY: "pymupdf4llm",
            PDFDocumentType.MULTIMODAL: "llamaparser",
        }
        for doc_type, expected_parser in expected.items():
            result = make_analysis_result(
                document_type=doc_type, confidence=0.8
            )
            decision = router.route(result)
            assert decision.parser_type == expected_parser, (
                f"{doc_type} should route to {expected_parser}"
            )
