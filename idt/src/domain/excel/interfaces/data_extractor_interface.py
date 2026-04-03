from abc import ABC, abstractmethod
from typing import Any, List

from src.domain.excel.value_objects.extract_config import ExtractConfig
from src.domain.excel.value_objects.filter_condition import FilterCondition


class DataExtractorInterface(ABC):
    @abstractmethod
    def extract(self, data: Any, config: ExtractConfig) -> Any:
        pass

    @abstractmethod
    def extract_columns(self, data: Any, columns: List[str]) -> Any:
        pass

    @abstractmethod
    def extract_rows(
        self, data: Any, conditions: List[FilterCondition]
    ) -> Any:
        pass

    @abstractmethod
    def get_extractor_name(self) -> str:
        pass
