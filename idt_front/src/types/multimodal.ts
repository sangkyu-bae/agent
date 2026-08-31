// multimodal-extractor Design §4.2 — 백엔드 src/interfaces/schemas/multimodal.py 와 동기.
// ElementType/Status 값은 백엔드 StrEnum value (wire 계약 — 변경 금지).

export const ELEMENT_TYPES = {
  FIGURE: 'figure',
  CHART: 'chart',
  TABLE_IMAGE: 'table_image',
  PAGE_SCAN: 'page_scan',
} as const;
export type ElementType = (typeof ELEMENT_TYPES)[keyof typeof ELEMENT_TYPES];

export const ELEMENT_STATUSES = {
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const;
export type ElementStatus = (typeof ELEMENT_STATUSES)[keyof typeof ELEMENT_STATUSES];

export const OUTPUT_LANGUAGES = ['ko', 'en'] as const;
export type OutputLanguage = (typeof OUTPUT_LANGUAGES)[number];

export const DETAIL_LEVELS = ['brief', 'detailed'] as const;
export type DetailLevel = (typeof DETAIL_LEVELS)[number];

/** 설정 값 범위 — 도메인 VO MultimodalSettings 와 동일 숫자 (Design §3.1) */
export const MULTIMODAL_LIMITS = {
  max_images_per_doc: { min: 1, max: 500 },
  min_image_px: { min: 0, max: 4096 },
  min_area_ratio: { min: 0, max: 1, step: 0.005 },
  concurrency: { min: 1, max: 16 },
  timeout_sec: { min: 5, max: 600 },
} as const;

export const PREVIEW_MAX_FILE_BYTES = 30 * 1024 * 1024;

/** 유형/상태 한글 라벨 (UI 전용) */
export const ELEMENT_TYPE_LABELS: Record<ElementType, string> = {
  figure: '그림',
  chart: '차트',
  table_image: '이미지형 표',
  page_scan: '스캔 페이지',
};
export const ELEMENT_STATUS_LABELS: Record<ElementStatus, string> = {
  succeeded: '성공',
  failed: '실패',
  skipped: '건너뜀',
};

// ── settings ──────────────────────────────────────────────

export interface VisionModelSummary {
  id: string;
  provider: string;
  model_name: string;
  display_name: string;
  is_active: boolean;
  supports_vision: boolean;
}

/** PUT /api/v1/admin/multimodal/settings — 전체 교체, 전 필드 필수 */
export interface MultimodalSettingsRequest {
  enabled: boolean;
  vision_model_id: string | null;
  max_images_per_doc: number;
  min_image_px: number;
  min_area_ratio: number;
  concurrency: number;
  timeout_sec: number;
  output_language: OutputLanguage;
  detail_level: DetailLevel;
}

export interface MultimodalSettingsResponse extends MultimodalSettingsRequest {
  id: string;
  /** 소프트 참조 해석 결과 — 모델 삭제/비활성 시 null + warnings */
  vision_model: VisionModelSummary | null;
  warnings: string[];
  updated_at: string;
}

// ── connection test ──────────────────────────────────────

export interface DraftDataPoint {
  label: string;
  value: string;
}

export interface DraftChart {
  chart_type: string | null;
  x_axis: string | null;
  y_axis: string | null;
  series: string[];
  data_points: DraftDataPoint[];
  trend: string | null;
}

export interface DescriptionDraft {
  detected_type: ElementType;
  description: string;
  keywords: string[];
  markdown_table: string | null;
  chart: DraftChart | null;
  page_text: string | null;
}

export interface ConnectionTestResponse {
  ok: boolean;
  provider: string;
  model_name: string;
  elapsed_ms: number;
  degraded_output_mode: boolean;
  draft: DescriptionDraft | null;
  error: string | null;
}

// ── preview ──────────────────────────────────────────────

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface MultimodalElement {
  element_id: string;
  page: number;
  bbox: BBox;
  element_type: ElementType;
  status: ElementStatus;
  reason: string | null;
  description: string | null;
  keywords: string[];
  markdown_table: string | null;
  chart: DraftChart | null;
  page_text: string | null;
  mime: string;
  width: number;
  height: number;
  sha256: string;
  model_id: string | null;
  elapsed_ms: number | null;
  degraded_output_mode: boolean;
  /** ≤256px PNG base64 — 원본 바이트는 노출되지 않는다 (Design §7) */
  thumbnail_b64: string | null;
}

export interface DroppedCandidate {
  page: number;
  reason: string;
  width: number;
  height: number;
}

export interface MultimodalPreviewResponse {
  vision_model_id: string;
  provider: string;
  model_name: string;
  total_candidates: number;
  dropped_by_filter: number;
  skipped_by_limit: number;
  succeeded: number;
  failed: number;
  timings_ms: Record<string, number>;
  elements: MultimodalElement[];
  /** debug=true 일 때만 존재 */
  dropped?: DroppedCandidate[];
}
