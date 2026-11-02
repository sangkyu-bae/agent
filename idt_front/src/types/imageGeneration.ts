// image-generation-tool Design §4.2 / §5.3 — image_generate 워커 설정 (발표자료 설정 동형).
// 백엔드 ImageGenerationConfigRequest / ImageGenerationToolConfig 와 동기.

/** 카탈로그 표기 tool_id (internal:presentation_generator 와 동형) */
export const IMAGE_GENERATE_TOOL_ID = 'internal:image_generate';
/** 에이전트 상세 workers[].tool_id 표기(카탈로그 접두어 없음) */
export const IMAGE_GENERATE_WORKER_TOOL_ID = 'image_generate';

export const IMAGE_GENERATION_SIZE = {
  SQUARE: '1024x1024',
  LANDSCAPE: '1536x1024',
  PORTRAIT: '1024x1536',
} as const;
export type ImageGenerationSize =
  (typeof IMAGE_GENERATION_SIZE)[keyof typeof IMAGE_GENERATION_SIZE];

export const IMAGE_GENERATION_QUALITY = {
  STANDARD: 'standard',
  HD: 'hd',
} as const;
export type ImageGenerationQuality =
  (typeof IMAGE_GENERATION_QUALITY)[keyof typeof IMAGE_GENERATION_QUALITY];

export const IMAGE_SIZE_OPTIONS: ReadonlyArray<{ value: ImageGenerationSize; label: string }> = [
  { value: IMAGE_GENERATION_SIZE.SQUARE, label: '1024×1024 정사각' },
  { value: IMAGE_GENERATION_SIZE.LANDSCAPE, label: '1536×1024 가로' },
  { value: IMAGE_GENERATION_SIZE.PORTRAIT, label: '1024×1536 세로' },
];

export const IMAGE_QUALITY_OPTIONS: ReadonlyArray<{ value: ImageGenerationQuality; label: string }> = [
  { value: IMAGE_GENERATION_QUALITY.STANDARD, label: '표준' },
  { value: IMAGE_GENERATION_QUALITY.HD, label: '고품질' },
];

/** 에이전트 생성·수정 요청의 image_generation 전용 필드 */
export interface ImageGenerationConfigRequest {
  llm_model_id: string;
  default_size: ImageGenerationSize;
  quality: ImageGenerationQuality;
}

/** 프론트 보유 드래프트 — 저장 시 image_generation 으로 전송 */
export interface ImageGenerationDraft {
  llmModelId: string;
  defaultSize: ImageGenerationSize;
  quality: ImageGenerationQuality;
}

export const EMPTY_IMAGE_GENERATION_DRAFT: ImageGenerationDraft = {
  llmModelId: '',
  defaultSize: IMAGE_GENERATION_SIZE.SQUARE,
  quality: IMAGE_GENERATION_QUALITY.STANDARD,
};

/** 에이전트 저장 422 메시지 접두 코드 (Design §6.1) */
export const IMAGE_GENERATION_ERROR_CODES = {
  MODEL_INVALID: 'IMAGE_MODEL_INVALID',
  CONFIG_INVALID: 'IMAGE_CONFIG_INVALID',
  /** 에이전트(대화)·비전 모델에 이미지 종류를 고른 경우 */
  MODEL_KIND_MISMATCH: 'MODEL_KIND_MISMATCH',
} as const;
