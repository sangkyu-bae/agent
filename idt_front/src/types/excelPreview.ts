// excel-preview Design §3.2 — 백엔드 ExcelPreviewResponse(pydantic)와 필드 동일 (FR-14)

export interface ExcelPreviewSheet {
  name: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
  total_cols: number;
  truncated: boolean;
}

export interface ExcelPreviewResponse {
  file_id: string;
  filename: string;
  max_rows: number;
  max_cols: number;
  sheets: ExcelPreviewSheet[];
}

// 진입 방식 스위치(EXCEL_PREVIEW_TRIGGER)는 document-file-preview에서
// types/filePreview.ts 의 FILE_PREVIEW_TRIGGER 로 이관했다 (엑셀·Word·PDF 공통).
