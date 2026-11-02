// image-generation-tool Design §4.2 / §6.1 — 드래프트 ⇄ 요청/워커 tool_config 변환·검증 (순수 함수)
import {
  IMAGE_GENERATION_ERROR_CODES,
  IMAGE_GENERATION_QUALITY,
  IMAGE_GENERATION_SIZE,
  type ImageGenerationConfigRequest,
  type ImageGenerationDraft,
  type ImageGenerationQuality,
  type ImageGenerationSize,
} from '@/types/imageGeneration';

const SIZES: readonly string[] = Object.values(IMAGE_GENERATION_SIZE);
const QUALITIES: readonly string[] = Object.values(IMAGE_GENERATION_QUALITY);

const toSize = (v: unknown): ImageGenerationSize =>
  typeof v === 'string' && SIZES.includes(v) ? (v as ImageGenerationSize) : IMAGE_GENERATION_SIZE.SQUARE;

const toQuality = (v: unknown): ImageGenerationQuality =>
  typeof v === 'string' && QUALITIES.includes(v)
    ? (v as ImageGenerationQuality)
    : IMAGE_GENERATION_QUALITY.STANDARD;

/** 모델 미선택이면 undefined (= 전송 안 함 / 변경 안 함) */
export const buildImageGenerationRequest = (
  draft: ImageGenerationDraft | null | undefined,
): ImageGenerationConfigRequest | undefined => {
  if (!draft || !draft.llmModelId) return undefined;
  return {
    llm_model_id: draft.llmModelId,
    default_size: draft.defaultSize,
    quality: draft.quality,
  };
};

/** 에이전트 상세의 image_generate 워커 tool_config → 드래프트 (edit 프리필) */
export const draftFromImageWorkerToolConfig = (
  toolConfig: Record<string, unknown> | null | undefined,
): ImageGenerationDraft | null => {
  if (!toolConfig || typeof toolConfig.llm_model_id !== 'string' || !toolConfig.llm_model_id) {
    return null;
  }
  return {
    llmModelId: toolConfig.llm_model_id,
    defaultSize: toSize(toolConfig.default_size),
    quality: toQuality(toolConfig.quality),
  };
};

export const IMAGE_MODEL_MISSING_NOTICE =
  "관리자 > LLM 모델에서 종류 '이미지 생성' 모델을 먼저 등록하세요.";

/** 로컬 검증 — 최종 검증은 백엔드(IMAGE_MODEL_INVALID / IMAGE_CONFIG_INVALID). */
export const validateImageGenerationDraft = (
  draft: ImageGenerationDraft | null | undefined,
  ctx: { hasImageModels: boolean },
): string | null => {
  if (!ctx.hasImageModels) return IMAGE_MODEL_MISSING_NOTICE;
  if (!draft || !draft.llmModelId) return '이미지 생성 모델을 선택하세요.';
  return null;
};

/** 서버 422 접두 코드를 사용자 안내로 바꾼다. 관련 없는 메시지는 그대로. */
export const imageGenerationSaveErrorMessage = (message: string): string => {
  if (message.startsWith(IMAGE_GENERATION_ERROR_CODES.MODEL_INVALID)) {
    return '이미지 생성 모델이 없거나 비활성이거나 이미지 종류가 아닙니다. 이미지 생성 설정에서 모델을 다시 선택하세요.';
  }
  if (message.startsWith(IMAGE_GENERATION_ERROR_CODES.CONFIG_INVALID)) {
    return '이미지 생성 설정의 크기 또는 품질 값이 올바르지 않습니다. 설정을 다시 선택하세요.';
  }
  if (message.startsWith(IMAGE_GENERATION_ERROR_CODES.MODEL_KIND_MISMATCH)) {
    return '이미지 생성 모델은 에이전트 대화 모델로 쓸 수 없습니다. 모델 설정에서 대화 모델을 선택하세요.';
  }
  return message;
};
