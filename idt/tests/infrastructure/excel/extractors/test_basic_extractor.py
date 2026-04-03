import pytest
import pandas as pd
from typing import List

from src.domain.excel.interfaces.data_extractor_interface import (
    DataExtractorInterface,
)
from src.domain.excel.value_objects.extract_config import ExtractConfig
from src.domain.excel.value_objects.filter_condition import (
    FilterCondition,
    FilterOperator,
)
from src.infrastructure.excel.extractors.basic_extractor import BasicDataExtractor


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "age": [25, 30, 35, 28, None],
        "city": ["NYC", "Boston", "NYC", "Boston", "Chicago"],
        "salary": [50000, 60000, 70000, 55000, 45000],
    })


@pytest.fixture
def extractor() -> BasicDataExtractor:
    return BasicDataExtractor()


class TestBasicDataExtractor:
    def test_implements_data_extractor_interface(self, extractor):
        assert isinstance(extractor, DataExtractorInterface)

    def test_get_extractor_name_returns_basic(self, extractor):
        assert extractor.get_extractor_name() == "basic"


class TestBasicDataExtractorExtractColumns:
    def test_extract_single_column(self, extractor, sample_df):
        result = extractor.extract_columns(sample_df, ["name"])
        assert list(result.columns) == ["name"]
        assert len(result) == 5

    def test_extract_multiple_columns(self, extractor, sample_df):
        result = extractor.extract_columns(sample_df, ["name", "age"])
        assert list(result.columns) == ["name", "age"]

    def test_extract_nonexistent_column_raises_error(self, extractor, sample_df):
        with pytest.raises(KeyError):
            extractor.extract_columns(sample_df, ["nonexistent"])

    def test_extract_columns_preserves_order(self, extractor, sample_df):
        result = extractor.extract_columns(sample_df, ["salary", "name", "age"])
        assert list(result.columns) == ["salary", "name", "age"]


class TestBasicDataExtractorExtractRows:
    def test_extract_rows_eq_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="city",
            operator=FilterOperator.EQ,
            value="NYC",
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert list(result["name"]) == ["Alice", "Charlie"]

    def test_extract_rows_ne_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="city",
            operator=FilterOperator.NE,
            value="NYC",
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 3
        assert "Alice" not in list(result["name"])

    def test_extract_rows_gt_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.GT,
            value=28,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Bob", "Charlie"}

    def test_extract_rows_lt_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.LT,
            value=30,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Alice", "Diana"}

    def test_extract_rows_gte_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.GTE,
            value=30,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Bob", "Charlie"}

    def test_extract_rows_lte_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.LTE,
            value=28,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Alice", "Diana"}

    def test_extract_rows_contains_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.CONTAINS,
            value="li",
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Alice", "Charlie"}

    def test_extract_rows_contains_case_insensitive(self, extractor, sample_df):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.CONTAINS,
            value="LI",
            case_sensitive=False,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 2
        assert set(result["name"]) == {"Alice", "Charlie"}

    def test_extract_rows_startswith_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.STARTSWITH,
            value="A",
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 1
        assert result["name"].iloc[0] == "Alice"

    def test_extract_rows_endswith_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.ENDSWITH,
            value="e",
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 3
        assert set(result["name"]) == {"Alice", "Charlie", "Eve"}

    def test_extract_rows_isin_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="city",
            operator=FilterOperator.ISIN,
            value=["NYC", "Chicago"],
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 3
        assert set(result["city"]) == {"NYC", "Chicago"}

    def test_extract_rows_notnull_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.NOTNULL,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 4
        assert "Eve" not in list(result["name"])

    def test_extract_rows_isnull_filter(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.ISNULL,
        )
        result = extractor.extract_rows(sample_df, [condition])
        assert len(result) == 1
        assert result["name"].iloc[0] == "Eve"

    def test_extract_rows_multiple_filters_and_condition(self, extractor, sample_df):
        conditions = [
            FilterCondition(column="city", operator=FilterOperator.EQ, value="NYC"),
            FilterCondition(column="age", operator=FilterOperator.GT, value=30),
        ]
        result = extractor.extract_rows(sample_df, conditions)
        assert len(result) == 1
        assert result["name"].iloc[0] == "Charlie"


class TestBasicDataExtractorExtract:
    def test_extract_with_columns_only(self, extractor, sample_df):
        config = ExtractConfig(columns=["name", "city"])
        result = extractor.extract(sample_df, config)
        assert list(result.columns) == ["name", "city"]
        assert len(result) == 5

    def test_extract_with_filters_only(self, extractor, sample_df):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.GT,
            value=25,
        )
        config = ExtractConfig(conditions=[condition])
        result = extractor.extract(sample_df, config)
        assert len(result) == 3

    def test_extract_with_columns_and_filters(self, extractor, sample_df):
        condition = FilterCondition(
            column="city",
            operator=FilterOperator.EQ,
            value="NYC",
        )
        config = ExtractConfig(columns=["name", "salary"], conditions=[condition])
        result = extractor.extract(sample_df, config)
        assert list(result.columns) == ["name", "salary"]
        assert len(result) == 2

    def test_extract_with_drop_duplicates(self, extractor):
        df = pd.DataFrame({
            "name": ["Alice", "Alice", "Bob"],
            "city": ["NYC", "NYC", "Boston"],
        })
        config = ExtractConfig(drop_duplicates=True)
        result = extractor.extract(df, config)
        assert len(result) == 2

    def test_extract_with_drop_na(self, extractor, sample_df):
        config = ExtractConfig(drop_na=True)
        result = extractor.extract(sample_df, config)
        assert len(result) == 4
        assert pd.notna(result["age"]).all()

    def test_extract_with_sort_ascending(self, extractor, sample_df):
        config = ExtractConfig(sort_by="age", sort_ascending=True)
        result = extractor.extract(sample_df, config)
        ages = result["age"].dropna().tolist()
        assert ages == sorted(ages)

    def test_extract_with_sort_descending(self, extractor, sample_df):
        config = ExtractConfig(sort_by="age", sort_ascending=False)
        result = extractor.extract(sample_df, config)
        ages = result["age"].dropna().tolist()
        assert ages == sorted(ages, reverse=True)

    def test_extract_empty_dataframe_returns_empty(self, extractor):
        df = pd.DataFrame(columns=["name", "age"])
        config = ExtractConfig(columns=["name"])
        result = extractor.extract(df, config)
        assert len(result) == 0
        assert list(result.columns) == ["name"]
