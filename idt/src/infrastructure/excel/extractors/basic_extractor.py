from typing import List

import pandas as pd

from src.domain.excel.interfaces.data_extractor_interface import (
    DataExtractorInterface,
)
from src.domain.excel.value_objects.extract_config import ExtractConfig
from src.domain.excel.value_objects.filter_condition import (
    FilterCondition,
    FilterOperator,
)


class BasicDataExtractor(DataExtractorInterface):
    def extract(self, data: pd.DataFrame, config: ExtractConfig) -> pd.DataFrame:
        result = data.copy()

        if config.conditions:
            result = self.extract_rows(result, config.conditions)

        if config.columns:
            result = self.extract_columns(result, config.columns)

        if config.drop_na:
            result = result.dropna()

        if config.drop_duplicates:
            result = result.drop_duplicates()

        if config.sort_by:
            result = result.sort_values(
                by=config.sort_by,
                ascending=config.sort_ascending,
                na_position="last",
            )

        return result

    def extract_columns(
        self, data: pd.DataFrame, columns: List[str]
    ) -> pd.DataFrame:
        return data[columns]

    def extract_rows(
        self, data: pd.DataFrame, conditions: List[FilterCondition]
    ) -> pd.DataFrame:
        result = data.copy()
        for condition in conditions:
            result = self._apply_filter(result, condition)
        return result

    def get_extractor_name(self) -> str:
        return "basic"

    def _apply_filter(
        self, df: pd.DataFrame, condition: FilterCondition
    ) -> pd.DataFrame:
        column = condition.column
        value = condition.value
        operator = condition.operator

        if operator == FilterOperator.EQ:
            return df[df[column] == value]
        elif operator == FilterOperator.NE:
            return df[df[column] != value]
        elif operator == FilterOperator.GT:
            return df[df[column] > value]
        elif operator == FilterOperator.LT:
            return df[df[column] < value]
        elif operator == FilterOperator.GTE:
            return df[df[column] >= value]
        elif operator == FilterOperator.LTE:
            return df[df[column] <= value]
        elif operator == FilterOperator.CONTAINS:
            return self._apply_string_filter(
                df, column, "contains", value, condition.case_sensitive
            )
        elif operator == FilterOperator.STARTSWITH:
            return self._apply_string_filter(
                df, column, "startswith", value, condition.case_sensitive
            )
        elif operator == FilterOperator.ENDSWITH:
            return self._apply_string_filter(
                df, column, "endswith", value, condition.case_sensitive
            )
        elif operator == FilterOperator.ISIN:
            return df[df[column].isin(value)]
        elif operator == FilterOperator.NOTNULL:
            return df[df[column].notna()]
        elif operator == FilterOperator.ISNULL:
            return df[df[column].isna()]
        else:
            raise ValueError(f"Unknown operator: {operator}")

    def _apply_string_filter(
        self,
        df: pd.DataFrame,
        column: str,
        method: str,
        value: str,
        case_sensitive: bool,
    ) -> pd.DataFrame:
        str_accessor = df[column].astype(str).str
        if method == "contains":
            mask = str_accessor.contains(value, case=case_sensitive, na=False)
        elif method == "startswith":
            if not case_sensitive:
                mask = str_accessor.lower().str.startswith(value.lower())
            else:
                mask = str_accessor.startswith(value)
        elif method == "endswith":
            if not case_sensitive:
                mask = str_accessor.lower().str.endswith(value.lower())
            else:
                mask = str_accessor.endswith(value)
        else:
            raise ValueError(f"Unknown string method: {method}")

        return df[mask]
