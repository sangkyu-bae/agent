import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import {
  useMultimodalSettings,
  useTestMultimodalConnection,
  useUpdateMultimodalSettings,
} from './useMultimodalSettings';
import { useMultimodalPreview } from './useMultimodalPreview';
import type { MultimodalSettingsRequest } from '@/types/multimodal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const req: MultimodalSettingsRequest = {
  enabled: true,
  vision_model_id: 'uuid-1',
  max_images_per_doc: 20,
  min_image_px: 100,
  min_area_ratio: 0.02,
  concurrency: 2,
  timeout_sec: 60,
  output_language: 'ko',
  detail_level: 'brief',
};

describe('useMultimodalSettings', () => {
  it('설정과 해석된 비전 모델을 조회한다', async () => {
    const { result } = renderHook(() => useMultimodalSettings(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.vision_model?.model_name).toBe('gpt-4o');
    expect(result.current.data!.concurrency).toBe(4);
  });

  it('PUT 성공 시 응답을 캐시에 반영한다', async () => {
    // 같은 React 루트에서 조회+뮤테이션 (별도 renderHook 루트 간에는 리렌더가 전파되지 않는다)
    const { result } = renderHook(
      () => ({ q: useMultimodalSettings(), m: useUpdateMultimodalSettings() }),
      { wrapper: createWrapper() }
    );
    await waitFor(() => expect(result.current.q.isSuccess).toBe(true));
    await result.current.m.mutateAsync(req);
    await waitFor(() => expect(result.current.q.data!.concurrency).toBe(2));
    expect(result.current.q.data!.detail_level).toBe('brief');
  });

  it('409(비전 미지원 모델)는 ApiError(status 409, 서버 메시지)로 전달된다', async () => {
    const { result } = renderHook(() => useUpdateMultimodalSettings(), { wrapper: createWrapper() });
    await expect(
      result.current.mutateAsync({ ...req, vision_model_id: 'uuid-3' })
    ).rejects.toMatchObject({ status: 409, message: '비전 미지원 모델' });
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
  });

  it('연결 테스트는 이미지 없이 호출 가능하고 draft를 돌려준다', async () => {
    const { result } = renderHook(() => useTestMultimodalConnection(), { wrapper: createWrapper() });
    const out = await result.current.mutateAsync(null);
    expect(out.ok).toBe(true);
    expect(out.draft?.detected_type).toBe('chart');
  });

  it('연결 테스트는 이미지 파일을 multipart image 필드로 보낸다', async () => {
    // jsdom/undici 에서 request.formData() 파싱이 깨지므로(기존 DatasetsTab 테스트와 동일) 헤더로 검증
    let contentType = '';
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_TEST}`, ({ request }) => {
        contentType = request.headers.get('content-type') ?? '';
        return HttpResponse.json({
          ok: false, provider: 'openai', model_name: 'gpt-4o', elapsed_ms: 5,
          degraded_output_mode: false, draft: null, error: 'RuntimeError: down',
        });
      })
    );
    const { result } = renderHook(() => useTestMultimodalConnection(), { wrapper: createWrapper() });
    const out = await result.current.mutateAsync(new File([new Uint8Array([1])], 'c.png', { type: 'image/png' }));
    expect(contentType).toMatch(/^multipart\/form-data/);
    expect(out.ok).toBe(false);
  });
});

describe('useMultimodalPreview', () => {
  it('debug 쿼리를 전달하고 dropped 를 받는다', async () => {
    const { result } = renderHook(() => useMultimodalPreview(), { wrapper: createWrapper() });
    const file = new File([new Uint8Array([37, 80, 68, 70])], 'a.pdf', { type: 'application/pdf' });
    const plain = await result.current.mutateAsync({ file, debug: false });
    expect(plain.elements).toHaveLength(3);
    expect(plain.dropped).toBeUndefined();
    const dbg = await result.current.mutateAsync({ file, debug: true });
    expect(dbg.dropped).toHaveLength(1);
  });

  it('409 MULTIMODAL_NOT_CONFIGURED 는 ApiError 로 전달된다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.PREVIEW_MULTIMODAL}`, () =>
        HttpResponse.json(
          { detail: { code: 'MULTIMODAL_NOT_CONFIGURED', message: 'vision_model_id is not set' } },
          { status: 409 }
        )
      )
    );
    const { result } = renderHook(() => useMultimodalPreview(), { wrapper: createWrapper() });
    const file = new File([new Uint8Array([1])], 'a.pdf', { type: 'application/pdf' });
    await expect(result.current.mutateAsync({ file, debug: false })).rejects.toMatchObject({
      status: 409,
    });
  });
});
