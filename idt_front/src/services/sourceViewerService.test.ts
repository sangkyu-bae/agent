// Design Ref: source-passage-viewer §4.1 — 원본 blob 조회 (module-6 원본 뷰어가 소비)
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';

import { sourceViewerService } from './sourceViewerService';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const URL = `*${API_ENDPOINTS.SOURCE_VIEWER_ORIGINAL('kb-1', 'doc-1')}`;

describe('sourceViewerService.fetchOriginal', () => {
  it('원본을 blob 으로 받는다', async () => {
    server.use(
      http.get(URL, () =>
        new HttpResponse(new Uint8Array([37, 80, 68, 70]), {
          headers: { 'Content-Type': 'application/pdf' },
        }),
      ),
    );
    const blob = await sourceViewerService.fetchOriginal('kb-1', 'doc-1');
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBe(4);
  });

  it('404 는 status 를 가진 ApiError', async () => {
    server.use(
      http.get(URL, () => HttpResponse.json({ detail: 'ORIGINAL_NOT_AVAILABLE' }, { status: 404 })),
    );
    await expect(sourceViewerService.fetchOriginal('kb-1', 'doc-1')).rejects.toMatchObject({
      status: 404,
    });
    await expect(sourceViewerService.fetchOriginal('kb-1', 'doc-1')).rejects.toBeInstanceOf(ApiError);
  });
});
