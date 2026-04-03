import io
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.domain.excel.interfaces.excel_parser_interface import ExcelParserInterface
from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.value_objects.excel_metadata import ExcelMetadata


class PandasExcelParser(ExcelParserInterface):
    def parse(self, file_path: str, user_id: str) -> ExcelData:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        excel_file = pd.ExcelFile(file_path)
        sheets = self._parse_all_sheets(excel_file)
        filename = path.name
        file_id = str(uuid.uuid4())
        total_rows = sum(sheet.row_count for sheet in sheets.values())

        metadata = ExcelMetadata(
            file_id=file_id,
            filename=filename,
            sheet_names=list(sheets.keys()),
            total_rows=total_rows,
            user_id=user_id,
        )

        return ExcelData(
            file_id=file_id,
            filename=filename,
            sheets=sheets,
            metadata=metadata,
        )

    def parse_bytes(
        self, file_bytes: bytes, filename: str, user_id: str
    ) -> ExcelData:
        try:
            buffer = io.BytesIO(file_bytes)
            excel_file = pd.ExcelFile(buffer)
        except Exception as e:
            raise ValueError(f"Invalid Excel format: {e}")

        sheets = self._parse_all_sheets(excel_file)
        file_id = str(uuid.uuid4())
        total_rows = sum(sheet.row_count for sheet in sheets.values())

        metadata = ExcelMetadata(
            file_id=file_id,
            filename=filename,
            sheet_names=list(sheets.keys()),
            total_rows=total_rows,
            user_id=user_id,
        )

        return ExcelData(
            file_id=file_id,
            filename=filename,
            sheets=sheets,
            metadata=metadata,
        )

    def parse_sheet(
        self, file_path: str, sheet_name: str, user_id: str
    ) -> SheetData:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        excel_file = pd.ExcelFile(file_path)
        if sheet_name not in excel_file.sheet_names:
            raise ValueError(f"Sheet not found: {sheet_name}")

        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        return self._dataframe_to_sheet_data(sheet_name, df)

    def get_sheet_names(self, file_path: str) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        excel_file = pd.ExcelFile(file_path)
        return list(excel_file.sheet_names)

    def get_parser_name(self) -> str:
        return "pandas"

    def _parse_all_sheets(
        self, excel_file: pd.ExcelFile
    ) -> Dict[str, SheetData]:
        sheets: Dict[str, SheetData] = {}
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            sheets[sheet_name] = self._dataframe_to_sheet_data(sheet_name, df)
        return sheets

    def _dataframe_to_sheet_data(
        self, sheet_name: str, df: pd.DataFrame
    ) -> SheetData:
        columns = list(df.columns)
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
        data = df.to_dict(orient="records")

        return SheetData(
            sheet_name=sheet_name,
            data=data,
            columns=columns,
            dtypes=dtypes,
        )
