/**
 * agentAttachmentService 단위 테스트 — ws-agent-excel-attachment.
 * 엑셀 multipart 업로드 → file_id 발급 응답 매핑.
 */
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import agentAttachmentService from '@/services/agentAttachmentService';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('agentAttachmentService.uploadExcel', () => {
  it('업로드 응답(file_id/type/filename/size)을 반환한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_ATTACHMENT_UPLOAD}`, () =>
        HttpResponse.json(
          {
            file_id: 'abc123',
            type: 'excel',
            filename: 'sales.xlsx',
            size: 2048,
          },
          { status: 201 },
        ),
      ),
    );

    const file = new File([new Uint8Array([1, 2, 3])], 'sales.xlsx', {
      type: 'application/vnd.ms-excel',
    });
    const res = await agentAttachmentService.uploadExcel(file);

    expect(res.file_id).toBe('abc123');
    expect(res.type).toBe('excel');
    expect(res.filename).toBe('sales.xlsx');
    expect(res.size).toBe(2048);
  });
});
