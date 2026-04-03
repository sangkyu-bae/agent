import pytest
from datetime import datetime

from src.domain.excel.value_objects.excel_metadata import ExcelMetadata


class TestExcelMetadataCreation:
    def test_create_metadata_with_required_fields(self):
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=100,
            user_id="user-1",
        )
        assert metadata.file_id == "file-123"
        assert metadata.filename == "test.xlsx"
        assert metadata.sheet_names == ["Sheet1"]
        assert metadata.total_rows == 100
        assert metadata.user_id == "user-1"

    def test_parsed_at_auto_generated(self):
        before = datetime.now()
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
        )
        after = datetime.now()
        assert before <= metadata.parsed_at <= after

    def test_parsed_at_can_be_provided(self):
        custom_time = datetime(2025, 1, 1, 12, 0, 0)
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
            parsed_at=custom_time,
        )
        assert metadata.parsed_at == custom_time


class TestExcelMetadataValidation:
    def test_file_id_cannot_be_empty(self):
        with pytest.raises(ValueError):
            ExcelMetadata(
                file_id="",
                filename="test.xlsx",
                sheet_names=["Sheet1"],
                total_rows=0,
                user_id="user-1",
            )

    def test_filename_cannot_be_empty(self):
        with pytest.raises(ValueError):
            ExcelMetadata(
                file_id="file-123",
                filename="",
                sheet_names=["Sheet1"],
                total_rows=0,
                user_id="user-1",
            )

    def test_user_id_cannot_be_empty(self):
        with pytest.raises(ValueError):
            ExcelMetadata(
                file_id="file-123",
                filename="test.xlsx",
                sheet_names=["Sheet1"],
                total_rows=0,
                user_id="",
            )

    def test_total_rows_cannot_be_negative(self):
        with pytest.raises(ValueError):
            ExcelMetadata(
                file_id="file-123",
                filename="test.xlsx",
                sheet_names=["Sheet1"],
                total_rows=-1,
                user_id="user-1",
            )


class TestExcelMetadataProperties:
    def test_sheet_count(self):
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1", "Sheet2", "Sheet3"],
            total_rows=0,
            user_id="user-1",
        )
        assert metadata.sheet_count == 3

    def test_sheet_count_empty(self):
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=[],
            total_rows=0,
            user_id="user-1",
        )
        assert metadata.sheet_count == 0


class TestExcelMetadataToDict:
    def test_to_dict_contains_all_fields(self):
        parsed_time = datetime(2025, 6, 15, 10, 30, 0)
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1", "Sheet2"],
            total_rows=50,
            user_id="user-1",
            parsed_at=parsed_time,
        )
        result = metadata.to_dict()

        assert result["file_id"] == "file-123"
        assert result["filename"] == "test.xlsx"
        assert result["sheet_names"] == ["Sheet1", "Sheet2"]
        assert result["total_rows"] == 50
        assert result["user_id"] == "user-1"
        assert result["parsed_at"] == parsed_time.isoformat()
        assert result["sheet_count"] == 2


class TestExcelMetadataImmutability:
    def test_metadata_is_immutable(self):
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
        )
        with pytest.raises(AttributeError):
            metadata.file_id = "other"
