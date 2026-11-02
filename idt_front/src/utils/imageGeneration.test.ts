// image-generation-tool Design §4.2 / §8.3 L2 #7 — 드래프트 ⇄ 요청 변환·검증 (순수 함수)
import { describe, expect, it } from 'vitest';
import {
  EMPTY_IMAGE_GENERATION_DRAFT,
  IMAGE_GENERATION_ERROR_CODES,
  type ImageGenerationDraft,
} from '@/types/imageGeneration';
import {
  buildImageGenerationRequest,
  draftFromImageWorkerToolConfig,
  imageGenerationSaveErrorMessage,
  validateImageGenerationDraft,
} from './imageGeneration';

const DRAFT: ImageGenerationDraft = {
  llmModelId: 'img-1',
  defaultSize: '1536x1024',
  quality: 'hd',
};

describe('buildImageGenerationRequest', () => {
  it('모델이 선택된 드래프트를 image_generation 요청 필드로 변환한다', () => {
    expect(buildImageGenerationRequest(DRAFT)).toEqual({
      llm_model_id: 'img-1',
      default_size: '1536x1024',
      quality: 'hd',
    });
  });

  it('모델 미선택·null 드래프트는 undefined (= 전송 안 함 / 변경 안 함)', () => {
    expect(buildImageGenerationRequest(null)).toBeUndefined();
    expect(buildImageGenerationRequest(EMPTY_IMAGE_GENERATION_DRAFT)).toBeUndefined();
  });
});

describe('draftFromImageWorkerToolConfig', () => {
  it('워커 tool_config 를 드래프트로 프리필한다', () => {
    expect(
      draftFromImageWorkerToolConfig({
        llm_model_id: 'img-1',
        default_size: '1024x1536',
        quality: 'standard',
      }),
    ).toEqual({ llmModelId: 'img-1', defaultSize: '1024x1536', quality: 'standard' });
  });

  it('허용 밖 size/quality 는 기본값으로 보정한다', () => {
    expect(
      draftFromImageWorkerToolConfig({ llm_model_id: 'img-1', default_size: '512x512', quality: 'ultra' }),
    ).toEqual({ llmModelId: 'img-1', defaultSize: '1024x1024', quality: 'standard' });
  });

  it('llm_model_id 가 없으면 null', () => {
    expect(draftFromImageWorkerToolConfig(null)).toBeNull();
    expect(draftFromImageWorkerToolConfig({})).toBeNull();
  });
});

describe('validateImageGenerationDraft', () => {
  it('이미지 모델이 하나도 없으면 관리자 등록 안내', () => {
    expect(validateImageGenerationDraft(DRAFT, { hasImageModels: false })).toMatch(/관리자/);
  });

  it('모델 미선택이면 선택 안내, 정상이면 null', () => {
    expect(validateImageGenerationDraft(EMPTY_IMAGE_GENERATION_DRAFT, { hasImageModels: true })).toMatch(
      /모델/,
    );
    expect(validateImageGenerationDraft(DRAFT, { hasImageModels: true })).toBeNull();
  });
});

describe('imageGenerationSaveErrorMessage', () => {
  it('서버 422 접두 코드별 안내로 바꾼다 (Design §6.1)', () => {
    expect(
      imageGenerationSaveErrorMessage(`${IMAGE_GENERATION_ERROR_CODES.MODEL_INVALID}: 모델을 찾을 수 없습니다`),
    ).toMatch(/이미지 생성 모델/);
    expect(
      imageGenerationSaveErrorMessage(`${IMAGE_GENERATION_ERROR_CODES.CONFIG_INVALID}: size 오류`),
    ).toMatch(/크기|품질/);
    expect(
      imageGenerationSaveErrorMessage(`${IMAGE_GENERATION_ERROR_CODES.MODEL_KIND_MISMATCH}: 'X' 은 이미지 모델`),
    ).toMatch(/대화 모델/);
  });

  it('관련 없는 메시지는 그대로 돌려준다', () => {
    expect(imageGenerationSaveErrorMessage('지침을 입력하세요')).toBe('지침을 입력하세요');
  });
});
