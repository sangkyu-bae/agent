// Design Ref: document-file-preview §3.1 — 산출 파일 미리보기 공통 타입·상수
// 런타임 상수는 컴포넌트 파일 export 금지 규칙에 따라 types/에 둔다.

export type PreviewKind = 'xlsx' | 'docx' | 'pdf';

/** 문서 모달(DocumentPreviewModal)이 맡는 종류. xlsx는 ExcelPreviewModal이 맡는다. */
export type DocumentPreviewKind = Exclude<PreviewKind, 'xlsx'>;

export type FilePreviewTrigger = 'button' | 'link';

/**
 * 진입 방식 스위치 — 엑셀·Word·PDF 공통 (Plan FR-11, excel-preview FR-09에서 이관).
 * 'button': 링크 클릭=다운로드(기존), 링크 옆 버튼=미리보기
 * 'link'  : 링크 클릭=미리보기, 다운로드는 모달 안에서만
 * 전환은 이 상수 1곳 변경으로 끝난다.
 */
export const FILE_PREVIEW_TRIGGER: FilePreviewTrigger = 'button';

/** docx-preview 렌더 상한 — 초과 시 렌더를 건너뛰고 다운로드를 안내한다 (Design §6.1). */
export const DOCX_PREVIEW_MAX_BYTES = 10 * 1024 * 1024;
