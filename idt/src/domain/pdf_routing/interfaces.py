from abc import ABC, abstractmethod
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_routing.schemas import RoutingDecision
from src.domain.pdf_routing.value_objects import ParserRoutingConfig


class ParserRouterInterface(ABC):

    @abstractmethod
    def route(
        self,
        analysis_result: Optional[AnalysisResult],
        config: Optional[ParserRoutingConfig] = None,
    ) -> RoutingDecision:
        pass
