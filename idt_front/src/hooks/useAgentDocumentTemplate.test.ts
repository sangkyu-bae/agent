// extractor-template-preview Design §8.3 F3: 저장 양식 조회 훅 enabled 조건
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { useAgentDocumentTemplate } from '@/hooks/useAgentBuilder';
import { queryKeys } from '@/lib/queryKeys';
import { agentBuilderService } from '@/services/agentBuilderService';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { AgentDocumentTemplateResponse } from '@/types/documentExtractor';

afterEach(() => {
  vi.restoreAllMocks();
});

const TEMPLATE = {
  template_id: 'tpl-1',
  name: '여신 승인 신청서',
  source_format: 'docx',
  html_skeleton: '<p>{{borrower_name}}</p>',
  slots: [],
  samples_hidden: false,
  is_inherited: false,
  updated_at: '2026-11-09T00:00:00',
} satisfies AgentDocumentTemplateResponse;

describe('useAgentDocumentTemplate', () => {
  it('agentId 가 있고 enabled 면 조회한다', async () => {
    const spy = vi
      .spyOn(agentBuilderService, 'getDocumentTemplate')
      .mockResolvedValue(TEMPLATE);

    const { result } = renderHook(() => useAgentDocumentTemplate('agent-1', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('agent-1');
    expect(result.current.data?.name).toBe('여신 승인 신청서');
  });

  it('F3: agentId 가 없으면 요청하지 않는다', () => {
    const spy = vi.spyOn(agentBuilderService, 'getDocumentTemplate');

    renderHook(() => useAgentDocumentTemplate(null, true), { wrapper: createWrapper() });

    expect(spy).not.toHaveBeenCalled();
  });

  it('F3: enabled=false(드래프트 있음·저장 양식 없음)면 요청하지 않는다', () => {
    const spy = vi.spyOn(agentBuilderService, 'getDocumentTemplate');

    renderHook(() => useAgentDocumentTemplate('agent-1', false), {
      wrapper: createWrapper(),
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it('쿼리 키는 agentBuilder.all 아래 있어 저장 성공 무효화에 함께 갱신된다', () => {
    expect(queryKeys.agentBuilder.documentTemplate('agent-1').slice(0, 1)).toEqual(
      queryKeys.agentBuilder.all,
    );
  });
});
