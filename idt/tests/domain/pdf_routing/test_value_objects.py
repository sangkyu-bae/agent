import pytest

from src.domain.pdf_routing.value_objects import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_FALLBACK_PARSER,
    DEFAULT_ROUTING_MAP,
    ParserRoutingConfig,
)


class TestParserRoutingConfig:

    def test_default_config(self) -> None:
        config = ParserRoutingConfig()
        assert config.routing_map == DEFAULT_ROUTING_MAP
        assert config.fallback_parser == DEFAULT_FALLBACK_PARSER
        assert config.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD

    def test_default_routing_map_entries(self) -> None:
        assert DEFAULT_ROUTING_MAP["text_heavy"] == "pymupdf"
        assert DEFAULT_ROUTING_MAP["ocr_heavy"] == "llamaparser"
        assert DEFAULT_ROUTING_MAP["table_heavy"] == "pymupdf4llm"
        assert DEFAULT_ROUTING_MAP["multimodal"] == "llamaparser"

    def test_custom_config(self) -> None:
        custom_map = {"text_heavy": "docling", "ocr_heavy": "llamaparser"}
        config = ParserRoutingConfig(
            routing_map=custom_map,
            fallback_parser="pymupdf4llm",
            confidence_threshold=0.7,
        )
        assert config.routing_map == custom_map
        assert config.fallback_parser == "pymupdf4llm"
        assert config.confidence_threshold == 0.7

    def test_invalid_threshold_below_zero(self) -> None:
        with pytest.raises(ValueError, match="confidence_threshold"):
            ParserRoutingConfig(confidence_threshold=-0.1)

    def test_invalid_threshold_above_one(self) -> None:
        with pytest.raises(ValueError, match="confidence_threshold"):
            ParserRoutingConfig(confidence_threshold=1.1)

    def test_threshold_at_zero(self) -> None:
        config = ParserRoutingConfig(confidence_threshold=0.0)
        assert config.confidence_threshold == 0.0

    def test_threshold_at_one(self) -> None:
        config = ParserRoutingConfig(confidence_threshold=1.0)
        assert config.confidence_threshold == 1.0

    def test_empty_fallback_parser(self) -> None:
        with pytest.raises(ValueError, match="fallback_parser"):
            ParserRoutingConfig(fallback_parser="")

    def test_whitespace_fallback_parser(self) -> None:
        with pytest.raises(ValueError, match="fallback_parser"):
            ParserRoutingConfig(fallback_parser="  ")

    def test_frozen(self) -> None:
        config = ParserRoutingConfig()
        with pytest.raises(AttributeError):
            config.fallback_parser = "docling"

    def test_custom_routing_map_with_new_parser(self) -> None:
        config = ParserRoutingConfig(
            routing_map={"text_heavy": "docling", "table_heavy": "camelot"}
        )
        assert config.routing_map["text_heavy"] == "docling"
        assert config.routing_map["table_heavy"] == "camelot"

    def test_default_config_does_not_share_mutable_state(self) -> None:
        config_a = ParserRoutingConfig()
        config_b = ParserRoutingConfig()
        assert config_a.routing_map is not config_b.routing_map
