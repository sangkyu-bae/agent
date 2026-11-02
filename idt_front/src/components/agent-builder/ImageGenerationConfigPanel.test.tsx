// image-generation-tool Design §5.1 / §8.3 L2 #5~#7 — image·활성 모델만, 모델 없음 안내, 크기·품질 선택
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { ImageGenerationDraft } from '@/types/imageGeneration';
import ImageGenerationConfigPanel from './ImageGenerationConfigPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const model = (over: Record<string, unknown>) => ({
  id: 'm',
  provider: 'openai',
  model_name: 'x',
  display_name: 'X',
  description: null,
  max_tokens: null,
  is_active: true,
  is_default: false,
  base_url: null,
  supports_vision: false,
  model_kind: 'chat',
  price_per_image_usd: null,
  ...over,
});

const MIXED = [
  model({ id: 'chat-1', model_name: 'gpt-4o', display_name: 'GPT-4o', is_default: true }),
  model({
    id: 'img-1', model_name: 'gpt-image-1', display_name: 'GPT Image 1',
    model_kind: 'image', price_per_image_usd: '0.0400',
  }),
  model({ id: 'img-off', model_name: 'dall-e-2', display_name: 'DALL-E 2', model_kind: 'image', is_active: false }),
];

const useModels = (models: unknown[]) =>
  server.use(http.get(`*${API_ENDPOINTS.LLM_MODELS}`, () => HttpResponse.json({ models })));

const renderPanel = (draft: ImageGenerationDraft | null, onChange = vi.fn()) => {
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <ImageGenerationConfigPanel draft={draft} onChange={onChange} />
    </Wrapper>,
  );
  return onChange;
};

describe('ImageGenerationConfigPanel', () => {
  it('#5 chat·image 혼재 목록에서 image·활성 모델만 옵션으로 노출한다', async () => {
    useModels(MIXED);
    renderPanel(null);
    expect(await screen.findByRole('option', { name: /GPT Image 1/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /GPT-4o/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /DALL-E 2/ })).not.toBeInTheDocument();
  });

  it('#6 이미지 모델이 없으면 관리자 등록 안내를 보여준다', async () => {
    useModels([MIXED[0]]);
    renderPanel(null);
    expect(await screen.findByText(/관리자 > LLM 모델/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/관리자/);
  });

  it('#7a 모델 선택이 기본 크기·품질과 함께 onChange 로 반영된다', async () => {
    useModels(MIXED);
    const onChange = renderPanel(null);
    await screen.findByRole('option', { name: /GPT Image 1/ });
    const select = screen.getByLabelText('이미지 모델') as HTMLSelectElement;
    await userEvent.selectOptions(select, 'img-1');
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ llmModelId: 'img-1', defaultSize: '1024x1024', quality: 'standard' }),
    );
  });

  it('#7b 크기·품질 라디오 선택이 onChange 로 반영되고 선택 모델의 단가 안내가 보인다', async () => {
    useModels(MIXED);
    const draft: ImageGenerationDraft = { llmModelId: 'img-1', defaultSize: '1024x1024', quality: 'standard' };
    const onChange = renderPanel(draft);
    await screen.findByRole('option', { name: /GPT Image 1/ });
    await userEvent.click(screen.getByLabelText(/1536×1024/));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ defaultSize: '1536x1024' }));
    await userEvent.click(screen.getByLabelText('고품질'));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ quality: 'hd' }));
    expect(screen.getByText(/\$0\.0400\/장/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
