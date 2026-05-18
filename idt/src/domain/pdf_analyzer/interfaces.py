from abc import ABC, abstractmethod
from typing import Optional

from src.domain.pdf_analyzer.schemas import AnalysisResult
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class PDFAnalyzerInterface(ABC):

    @abstractmethod
    def analyze_bytes(
        self,
        file_bytes: bytes,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        pass

    @abstractmethod
    def analyze_path(
        self,
        file_path: str,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        pass
