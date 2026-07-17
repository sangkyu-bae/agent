"""시트→텍스트 직렬화 공용 함수 (kb-excel-upload D5).

ExcelUploadUseCase와 ExcelDocumentParserAdapter가 공유한다.
형식: 행마다 "col1: val1 | col2: val2", 개행 결합 — 변경 시 기존
벡터 저장 텍스트와 형식이 어긋나므로 테스트로 고정한다.
"""
from src.domain.excel.entities.sheet_data import SheetData


def sheet_to_text(sheet: SheetData) -> str:
    """시트 데이터를 행 단위 key-value 텍스트로 직렬화한다."""
    lines = []
    for row in sheet.data:
        parts = [f"{col}: {row.get(col, '')}" for col in sheet.columns]
        lines.append(" | ".join(parts))
    return "\n".join(lines)
