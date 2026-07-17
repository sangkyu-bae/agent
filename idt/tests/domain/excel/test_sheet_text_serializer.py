"""sheet_to_text — 시트 직렬화 공용 함수 (kb-excel-upload D5).

형식 고정: 기존 ExcelUploadUseCase._sheet_to_text와 동일해야 한다
("col1: val1 | col2: val2" 행 단위, 개행 결합).
"""
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.services.sheet_text_serializer import sheet_to_text


def _sheet(data, columns) -> SheetData:
    return SheetData(sheet_name="시트1", data=data, columns=columns)


class TestSheetToText:
    def test_row_format_is_pipe_joined_key_values(self):
        sheet = _sheet(
            data=[{"상품": "주담대", "한도": 500}, {"상품": "신용", "한도": 100}],
            columns=["상품", "한도"],
        )
        assert sheet_to_text(sheet) == (
            "상품: 주담대 | 한도: 500\n상품: 신용 | 한도: 100"
        )

    def test_missing_column_value_becomes_empty_string(self):
        sheet = _sheet(data=[{"a": 1}], columns=["a", "b"])
        assert sheet_to_text(sheet) == "a: 1 | b: "

    def test_empty_sheet_returns_empty_string(self):
        sheet = _sheet(data=[], columns=["a"])
        assert sheet_to_text(sheet) == ""

    def test_column_order_follows_columns_list(self):
        sheet = _sheet(data=[{"b": 2, "a": 1}], columns=["b", "a"])
        assert sheet_to_text(sheet) == "b: 2 | a: 1"
