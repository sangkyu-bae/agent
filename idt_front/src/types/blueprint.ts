// golden-sample-blueprint Design §4.2 — 백엔드 src/interfaces/schemas/blueprint.py 와 동기.
// PatternKind/SlotKind 값은 백엔드 StrEnum value (wire 계약 — 변경 금지).

export const PATTERN_KINDS = [
  'cover',
  'toc',
  'section_lead',
  'text',
  'chart_with_notes',
  'table',
  'two_column',
  'image_with_notes',
  'closing',
  'unknown',
] as const;
export type PatternKind = (typeof PATTERN_KINDS)[number];

export const SLOT_KINDS = ['title', 'text', 'bullets', 'table', 'chart', 'image', 'footer'] as const;
export type SlotKind = (typeof SLOT_KINDS)[number];

export const ASSET_KINDS = ['logo', 'decoration', 'cover'] as const;
export type AssetKind = (typeof ASSET_KINDS)[number];

export const SOURCE_KINDS = ['pdf', 'pptx'] as const;
export type SourceKind = (typeof SOURCE_KINDS)[number];

export type BlueprintStatus = 'active' | 'inactive';

export const PATTERN_KIND_LABELS: Record<PatternKind, string> = {
  cover: '표지',
  toc: '목차',
  section_lead: '섹션 리드',
  text: '본문',
  chart_with_notes: '차트+해설',
  table: '표',
  two_column: '2단',
  image_with_notes: '이미지+해설',
  closing: '결론',
  unknown: '미분류',
};

export const SLOT_KIND_LABELS: Record<SlotKind, string> = {
  title: '제목',
  text: '텍스트',
  bullets: '불릿',
  table: '표',
  chart: '차트',
  image: '이미지',
  footer: '푸터',
};

export const ASSET_KIND_LABELS: Record<AssetKind, string> = {
  logo: '로고',
  decoration: '장식',
  cover: '표지',
};

/** 클라이언트 가드 — 백엔드 라우터/UseCase 와 동일 숫자 (Design §4.2 / §7) */
export const BLUEPRINT_LIMITS = {
  upload_max_bytes: 30 * 1024 * 1024,
  name_max: 100,
  description_max: 500,
  max_pages_default: 60,
  max_assets: 20,
} as const;

export const REQUIRED_PALETTE_KEYS = ['primary', 'accent1', 'text', 'bg'] as const;
export const REQUIRED_SIZE_KEYS = ['h1', 'h2', 'body', 'caption'] as const;
/** schema v2 옵션 크기 역할 (blueprint-style-fidelity DR-4) — 없으면 서버가 폴백 */
export const OPTIONAL_SIZE_KEYS = ['h3', 'subtitle'] as const;
export const CURRENT_BLUEPRINT_SCHEMA_VERSION = 2;
export type SlotAlign = 'left' | 'center' | 'right';

// ── blueprint 구조 (blueprint_to_dict 와 동형) ─────────────────

export interface RelBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface BlueprintSlot {
  id: string;
  kind: SlotKind;
  box: RelBox;
  role: string;
  max_chars: number | null;
  max_rows: number | null;
  asset_id: string | null;
  /** schema v2 — v1 응답에는 없을 수 있음 (서버 기본 'left') */
  align?: SlotAlign;
}

/** schema v2 — 서버 계산 장식 도형. LLM 이 채우지 않음 (읽기 전용 라운드트립). */
export interface BlueprintDecoration {
  id: string;
  shape: 'rect';
  box: RelBox;
  fill: string;
  line: string | null;
}

export interface BlueprintPattern {
  id: string;
  kind: PatternKind;
  slots: BlueprintSlot[];
  background: string | null;
  sample_page: number;
  notes: string;
  /** schema v2 */
  decorations?: BlueprintDecoration[];
}

export interface TableStyle {
  header_bg: string;
  header_text: string;
  border: string;
  zebra: boolean;
}

export interface HeaderFooter {
  logo_asset_id: string | null;
  page_number_format: string;
  footer_text: string;
  /** schema v2 */
  footer_box?: RelBox | null;
  page_number_box?: RelBox | null;
  footer_color?: string | null;
}

export interface BlueprintStyle {
  slide_size: number[];
  fonts: Record<string, string>;
  sizes: Record<string, number>;
  palette: Record<string, string>;
  table_style: TableStyle;
  header_footer: HeaderFooter;
  /** schema v2 — 비표지 전 슬라이드 공통 장식 */
  common_decorations?: BlueprintDecoration[];
}

export interface NarrativeSection {
  role: string;
  pattern_ids: string[];
  guidance: string;
}

export interface BlueprintNarrative {
  sections: NarrativeSection[];
  tone: string;
  language: string;
}

export interface BlueprintAsset {
  id: string;
  kind: AssetKind;
  mime: string;
  width: number;
  height: number;
  sha256: string;
  box: RelBox;
  adopted: boolean;
  /** schema v2 — 표지에서의 위치 (logo 전용) */
  cover_box?: RelBox | null;
}

/** 요청용 draft (타임스탬프 없음) — POST/PUT body.draft */
export interface BlueprintDraft {
  id: string;
  name: string;
  description: string;
  source_kind: SourceKind;
  page_count: number;
  schema_version: number;
  style: BlueprintStyle;
  patterns: BlueprintPattern[];
  narrative: BlueprintNarrative;
  assets: BlueprintAsset[];
  font_mapping: Record<string, string>;
  warnings: string[];
  status: BlueprintStatus;
}

export interface BlueprintResponse extends BlueprintDraft {
  created_at: string;
  updated_at: string;
}

export interface BlueprintSummary {
  id: string;
  name: string;
  source_kind: SourceKind;
  page_count: number;
  pattern_count: number;
  status: BlueprintStatus;
  updated_at: string;
}

export interface AssetPreview extends BlueprintAsset {
  thumbnail_b64: string | null;
  /** 추출 응답에만 포함 — 저장(POST) 시 되돌려 보내는 원본 바이트 */
  data_b64: string | null;
}

export interface BlueprintExtractResponse {
  draft: BlueprintResponse;
  assets: AssetPreview[];
  page_thumbnails: (string | null)[];
  classification: { succeeded: number; failed: number };
  timings_ms: Record<string, number>;
}

export interface BlueprintCreateRequest {
  draft: BlueprintDraft;
  /** 추출 응답 assets[].data_b64 를 그대로 되돌려 보낸다 */
  assets: { id: string; data_b64: string }[];
}

export interface BlueprintUpdateRequest {
  draft: BlueprintDraft;
}

export interface FontsResponse {
  installed: string[];
  default: string;
}

export interface BlueprintOption {
  id: string;
  name: string;
}

export interface BlueprintOptionsResponse {
  items: BlueprintOption[];
}
