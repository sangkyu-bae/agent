import pytest
from abc import ABC
from typing import List, Any

from src.domain.excel.interfaces.data_extractor_interface import (
    DataExtractorInterface,
)
from src.domain.excel.value_objects.extract_config import ExtractConfig
from src.domain.excel.value_objects.filter_condition import (
    FilterCondition,
    FilterOperator,
)


class TestDataExtractorInterface:
    def test_is_abstract_class(self):
        assert issubclass(DataExtractorInterface, ABC)

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            DataExtractorInterface()

    def test_has_extract_method(self):
        assert hasattr(DataExtractorInterface, "extract")
        assert callable(getattr(DataExtractorInterface, "extract"))

    def test_has_extract_columns_method(self):
        assert hasattr(DataExtractorInterface, "extract_columns")
        assert callable(getattr(DataExtractorInterface, "extract_columns"))

    def test_has_extract_rows_method(self):
        assert hasattr(DataExtractorInterface, "extract_rows")
        assert callable(getattr(DataExtractorInterface, "extract_rows"))

    def test_has_get_extractor_name_method(self):
        assert hasattr(DataExtractorInterface, "get_extractor_name")
        assert callable(getattr(DataExtractorInterface, "get_extractor_name"))


class TestExtractConfigCreation:
    def test_create_config_with_defaults(self):
        config = ExtractConfig()
        assert config.columns is None
        assert config.conditions == []
        assert config.drop_duplicates is False
        assert config.drop_na is False
        assert config.sort_by is None
        assert config.sort_ascending is True

    def test_create_config_with_columns(self):
        config = ExtractConfig(columns=["name", "age"])
        assert config.columns == ["name", "age"]

    def test_create_config_with_conditions(self):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.GT,
            value=18,
        )
        config = ExtractConfig(conditions=[condition])
        assert len(config.conditions) == 1
        assert config.conditions[0] == condition

    def test_create_config_with_drop_duplicates(self):
        config = ExtractConfig(drop_duplicates=True)
        assert config.drop_duplicates is True

    def test_create_config_with_drop_na(self):
        config = ExtractConfig(drop_na=True)
        assert config.drop_na is True

    def test_create_config_with_sort(self):
        config = ExtractConfig(sort_by="name", sort_ascending=False)
        assert config.sort_by == "name"
        assert config.sort_ascending is False


class TestExtractConfigToDict:
    def test_to_dict_contains_all_fields(self):
        condition = FilterCondition(
            column="status",
            operator=FilterOperator.EQ,
            value="active",
        )
        config = ExtractConfig(
            columns=["name", "status"],
            conditions=[condition],
            drop_duplicates=True,
            drop_na=True,
            sort_by="name",
            sort_ascending=False,
        )
        result = config.to_dict()

        assert result["columns"] == ["name", "status"]
        assert len(result["conditions"]) == 1
        assert result["drop_duplicates"] is True
        assert result["drop_na"] is True
        assert result["sort_by"] == "name"
        assert result["sort_ascending"] is False
