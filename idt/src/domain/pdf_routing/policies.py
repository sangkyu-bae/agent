from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class ParserRoutingPolicy:

    @staticmethod
    def decide(
        analysis_result: Optional[AnalysisResult],
        config: ParserRoutingConfig,
    ) -> RoutingDecision:
        if analysis_result is None:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=None,
                confidence=0.0,
                reason=RoutingReason.NO_ANALYSIS_FALLBACK,
                is_fallback=True,
            )

        if analysis_result.confidence < config.confidence_threshold:
            return RoutingDecision(
                parser_type=config.fallback_parser,
                document_type=analysis_result.document_type.value,
                confidence=analysis_result.confidence,
                reason=RoutingReason.LOW_CONFIDENCE_FALLBACK,
                is_fallback=True,
            )

        doc_type_value = analysis_result.document_type.value
        matched_parser = config.routing_map.get(
            doc_type_value, config.fallback_parser
        )
        is_fallback = doc_type_value not in config.routing_map

        return RoutingDecision(
            parser_type=matched_parser,
            document_type=doc_type_value,
            confidence=analysis_result.confidence,
            reason=(
                RoutingReason.DOCUMENT_TYPE_MATCH
                if not is_fallback
                else RoutingReason.LOW_CONFIDENCE_FALLBACK
            ),
            is_fallback=is_fallback,
        )
