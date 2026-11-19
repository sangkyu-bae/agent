// Design Ref: source-passage-viewer §3.3 — 백엔드 계약: idt/src/domain/source_viewer/models.py ViewerRef.to_payload

/** 원본 뷰어가 렌더할 수 있는 형식. null 이면 텍스트 뷰어. */
export const ORIGINAL_KIND = {
  PDF: 'pdf',
  DOCX: 'docx',
} as const;

export type OriginalKind = (typeof ORIGINAL_KIND)[keyof typeof ORIGINAL_KIND];

/** 패널이 쓰는 청크 조회 파라미터 — 텍스트 뷰어와 원본 매칭 텍스트가 같은 캐시를 공유한다. */
export const SOURCE_VIEWER_CHUNK_PARAMS = { source: 'qdrant', include_parent: true } as const;

export const VIEWER_MODE = {
  TEXT: 'text',
  ORIGINAL: 'original',
} as const;

export type ViewerMode = (typeof VIEWER_MODE)[keyof typeof VIEWER_MODE];

export interface SourceViewerPassage {
  chunk_id: string;
  parent_id: string | null;
  page: number | null;
  /** 검색 기록의 청크 앞부분 — 위치를 못 찾았을 때 표시·대체 매칭용 */
  excerpt: string;
}

/** 문서 칩의 `viewer` 객체. 없거나 null 이면 원문 보기 기능이 없는 칩이다. */
export interface SourceViewerRef {
  document_id: string;
  kb_id: string;
  original: OriginalKind | null;
  passages: SourceViewerPassage[];
}

export interface SourceViewerTarget {
  viewer: SourceViewerRef;
  filename: string;
}

/** 원문 범위 [start, end) — 텍스트 뷰어 문서 기준 */
export interface TextRange {
  start: number;
  end: number;
}
