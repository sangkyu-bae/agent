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

export type ExcelPreviewTrigger = 'button' | 'link';

/**
 * 진입 방식 스위치 (FR-09, Design §5.3).
 * 'button': 링크 클릭=다운로드(기존), 링크 옆 버튼=프리뷰
 * 'link'  : 링크 클릭=프리뷰, 다운로드는 모달 안에서만
 * 전환은 이 상수 1곳 변경으로 끝난다. 런타임 상수는 컴포넌트 파일 export 금지 규칙에
 * 따라 types/에 둔다.
 */
export const EXCEL_PREVIEW_TRIGGER: ExcelPreviewTrigger = 'button';
