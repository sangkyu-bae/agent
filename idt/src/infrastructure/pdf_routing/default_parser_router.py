from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.interfaces import ParserRouterInterface
from src.domain.pdf_routing.policies import ParserRoutingPolicy
from src.domain.pdf_routing.schemas import RoutingDecision
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class DefaultParserRouter(ParserRouterInterface):

    def __init__(
        self,
        config: Optional[ParserRoutingConfig] = None,
    ) -> None:
        self._config = config or ParserRoutingConfig()

    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        effective_config = config or self._config
        return ParserRoutingPolicy.decide(analysis_result, effective_config)
