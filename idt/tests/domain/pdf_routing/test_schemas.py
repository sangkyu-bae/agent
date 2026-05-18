import pytest
from pydantic import ValidationError

from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason


class TestRoutingReason:

    def test_document_type_match_value(self) -> None:
        assert RoutingReason.DOCUMENT_TYPE_MATCH == "document_type_match"

    def test_low_confidence_fallback_value(self) -> None:
        assert RoutingReason.LOW_CONFIDENCE_FALLBACK == "low_confidence_fallback"

    def test_no_analysis_fallback_value(self) -> None:
        assert RoutingReason.NO_ANALYSIS_FALLBACK == "no_analysis_fallback"

    def test_config_override_value(self) -> None:
        assert RoutingReason.CONFIG_OVERRIDE == "config_override"


class TestRoutingDecision:

    def test_creation_with_all_fields(self) -> None:
        decision = RoutingDecision(
            parser_type="pymupdf",
            document_type="text_heavy",
            confidence=0.8,
            reason=RoutingReason.DOCUMENT_TYPE_MATCH,
            is_fallback=False,
        )
        assert decision.parser_type == "pymupdf"
        assert decision.document_type == "text_heavy"
        assert decision.confidence == 0.8
        assert decision.reason == RoutingReason.DOCUMENT_TYPE_MATCH
        assert decision.is_fallback is False

    def test_creation_with_none_document_type(self) -> None:
        decision = RoutingDecision(
            parser_type="pymupdf",
            document_type=None,
            confidence=0.0,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            is_fallback=True,
        )
        assert decision.document_type is None

    def test_frozen_model(self) -> None:
        decision = RoutingDecision(
            parser_type="pymupdf",
            confidence=0.5,
            reason=RoutingReason.DOCUMENT_TYPE_MATCH,
            is_fallback=False,
        )
        with pytest.raises(ValidationError):
            decision.parser_type = "llamaparser"

    def test_confidence_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            RoutingDecision(
                parser_type="pymupdf",
                confidence=-0.1,
                reason=RoutingReason.DOCUMENT_TYPE_MATCH,
                is_fallback=False,
            )

    def test_confidence_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            RoutingDecision(
                parser_type="pymupdf",
                confidence=1.1,
                reason=RoutingReason.DOCUMENT_TYPE_MATCH,
                is_fallback=False,
            )

    def test_confidence_at_zero(self) -> None:
        decision = RoutingDecision(
            parser_type="pymupdf",
            confidence=0.0,
            reason=RoutingReason.NO_ANALYSIS_FALLBACK,
            is_fallback=True,
        )
        assert decision.confidence == 0.0

    def test_confidence_at_one(self) -> None:
        decision = RoutingDecision(
            parser_type="pymupdf",
            confidence=1.0,
            reason=RoutingReason.DOCUMENT_TYPE_MATCH,
            is_fallback=False,
        )
        assert decision.confidence == 1.0
