// image-generation-tool Design §4.2 / §8.3 L2 #10 — 채팅·비전 드롭다운은 model_kind==='chat' 만
import { describe, expect, it } from 'vitest';
import type { LlmModel } from '@/types/llmModel';
import {
  filterActiveImageModels,
  filterChatModels,
  isChatModel,
  isImageModel,
} from './llmModelKind';

const base = (over: Partial<LlmModel>): LlmModel => ({
  id: 'm',
  provider: 'openai',
  model_name: 'x',
  display_name: 'X',
  description: null,
  max_tokens: null,
  is_active: true,
  is_default: false,
  ...over,
});

describe('llmModelKind', () => {
  it('model_kind 미존재(구버전 응답)는 chat 으로 간주한다', () => {
    expect(isChatModel(base({}))).toBe(true);
    expect(isImageModel(base({}))).toBe(false);
  });

  it('filterChatModels 는 image 종류를 제외한다', () => {
    const models = [
      base({ id: 'c1', model_kind: 'chat' }),
      base({ id: 'i1', model_kind: 'image' }),
      base({ id: 'legacy' }),
    ];
    expect(filterChatModels(models).map((m) => m.id)).toEqual(['c1', 'legacy']);
    expect(filterChatModels(undefined)).toEqual([]);
  });

  it('filterActiveImageModels 는 활성 image 종류만 남긴다', () => {
    const models = [
      base({ id: 'c1', model_kind: 'chat' }),
      base({ id: 'i1', model_kind: 'image' }),
      base({ id: 'i2', model_kind: 'image', is_active: false }),
    ];
    expect(filterActiveImageModels(models).map((m) => m.id)).toEqual(['i1']);
  });
});
