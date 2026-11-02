// image-generation-tool Design §5.3 — fetchGeneratedFileBlob: 산출 파일을 인증 클라이언트로 blob 조회
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { documentExtractorService } from './documentExtractorService';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('documentExtractorService.fetchGeneratedFileBlob', () => {
  it('파일 엔드포인트를 blob 으로 받아 그대로 돌려준다', async () => {
    let requestedPath = '';
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE(':fileId')}`, ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        // jsdom XHR 은 비 ASCII 바이트를 UTF-8 로 재인코딩하므로 ASCII 4바이트로 검증
        return new HttpResponse('PNG!', {
          headers: { 'Content-Type': 'image/png' },
        });
      }),
    );
    const blob = await documentExtractorService.fetchGeneratedFileBlob('abc123');
    expect(requestedPath).toBe('/api/v1/document-extractor/files/abc123');
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBe(4);
  });

  it('404 는 예외로 전파한다 (호출 측이 폴백 링크로 전환)', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE(':fileId')}`, () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
    );
    await expect(documentExtractorService.fetchGeneratedFileBlob('missing')).rejects.toBeTruthy();
  });
});
