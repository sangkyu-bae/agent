"""excel-preview config 키 테스트 (Design §8.2 #12, FR-03)."""
from src.config import Settings


class TestExcelPreviewSettings:
    def test_defaults(self):
        s = Settings(_env_file=None)
        assert s.excel_preview_max_rows == 100
        assert s.excel_preview_max_cols == 50

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EXCEL_PREVIEW_MAX_ROWS", "10")
        monkeypatch.setenv("EXCEL_PREVIEW_MAX_COLS", "5")
        s = Settings(_env_file=None)
        assert s.excel_preview_max_rows == 10
        assert s.excel_preview_max_cols == 5
