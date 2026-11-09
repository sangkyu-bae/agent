// extractor-template-preview Design §8.3 F1–F2: 저장 양식 조회 서비스
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import { agentBuilderService } from './agentBuilderService';
import type { AgentDocumentTemplateResponse } from '@/types/documentExtractor';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const TEMPLATE: AgentDocumentTemplateResponse = {
  template_id: 'tpl-1',
  name: '여신 승인 신청서',
  source_format: 'docx',
  html_skeleton: '<p>{{borrower_name}}</p>',
  slots: [
    {
      key: 'borrower_name',
      label: '차주명',
      slot_type: 'value',
      description: '',
      sample_value: '홍길동',
    },
  ],
  samples_hidden: false,
  is_inherited: false,
  updated_at: '2026-11-09T00:00:00',
};

describe('agentBuilderService.getDocumentTemplate', () => {
  it('F1: 저장 양식 엔드포인트 응답을 그대로 돌려준다', async () => {
    let requestedPath = '';
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_DOCUMENT_TEMPLATE(':agentId')}`, ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(TEMPLATE);
      }),
    );

    const result = await agentBuilderService.getDocumentTemplate('agent-1');

    expect(requestedPath).toBe('/api/v1/agents/agent-1/document-template');
    expect(result).toEqual(TEMPLATE);
  });

  it('F2: 404 는 null 로 바꾼다 (양식 없음)', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_DOCUMENT_TEMPLATE(':agentId')}`, () =>
        HttpResponse.json({ detail: 'Document template not found' }, { status: 404 }),
      ),
    );

    await expect(agentBuilderService.getDocumentTemplate('agent-1')).resolves.toBeNull();
  });

  it('404 외 오류는 그대로 던진다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.AGENT_DOCUMENT_TEMPLATE(':agentId')}`, () =>
        HttpResponse.json({ detail: '양식 조회 권한이 없습니다' }, { status: 403 }),
      ),
    );

    await expect(agentBuilderService.getDocumentTemplate('agent-1')).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
