import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { WikiArticle } from '@/types/wiki';
import WikiDetailPanel from './WikiDetailPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const article: WikiArticle = {
  id: 'w1',
  agent_id: 'agent-1',
  title: '여신 한도 산정',
  content: '여신 한도는 ...',
  source_type: 'distilled',
  source_refs: ['doc:1#p3', 'doc:2#p1'],
  status: 'draft',
  confidence: 0.8,
  valid_until: null,
  version: 1,
  editor_id: null,
  reviewer_id: null,
  created_at: '2026-06-30T00:00:00Z',
  updated_at: '2026-06-30T00:00:00Z',
};

describe('WikiDetailPanel', () => {
  it('본문과 출처(source_refs)를 렌더한다', () => {
    render(
      <WikiDetailPanel article={article} currentUserId="admin" onClose={vi.fn()} />,
      { wrapper: createWrapper() },
    );
    expect(screen.getByText('여신 한도는 ...')).toBeInTheDocument();
    expect(screen.getByText('doc:1#p3')).toBeInTheDocument();
    expect(screen.getByText('doc:2#p1')).toBeInTheDocument();
  });

  it('편집 → 저장 시 useUpdateArticle가 호출되어 편집모드가 닫힌다', async () => {
    const user = userEvent.setup();
    render(
      <WikiDetailPanel article={article} currentUserId="admin" onClose={vi.fn()} />,
      { wrapper: createWrapper() },
    );
    await user.click(screen.getByRole('button', { name: '편집' }));
    const body = screen.getByLabelText('본문');
    await user.clear(body);
    await user.type(body, '수정된 본문');
    await user.click(screen.getByRole('button', { name: '저장' }));
    // 저장 성공 후 편집모드 종료 → '편집' 버튼이 다시 보인다
    expect(await screen.findByRole('button', { name: '편집' })).toBeInTheDocument();
  });

  it('currentUserId가 비면 저장 버튼이 비활성화된다', async () => {
    const user = userEvent.setup();
    render(
      <WikiDetailPanel article={article} currentUserId="" onClose={vi.fn()} />,
      { wrapper: createWrapper() },
    );
    await user.click(screen.getByRole('button', { name: '편집' }));
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });
});
