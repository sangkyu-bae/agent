import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { API_ENDPOINTS } from '@/constants/api';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import WikiPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('WikiPage', () => {
  it('헤더와 빈 상태 안내가 렌더된다', () => {
    render(<WikiPage />, { wrapper: createWrapper() });
    expect(screen.getByText('위키 관리')).toBeInTheDocument();
    expect(
      screen.getByText(/에이전트를 선택하면 위키 목록이 표시됩니다/),
    ).toBeInTheDocument();
  });

  it('T3: 드롭다운으로 에이전트·컬렉션 선택 후 정제 실행 시 페이로드가 전송된다', async () => {
    let distillBody: unknown = null;
    server.use(
      http.post(`*${API_ENDPOINTS.WIKI_DISTILL}`, async ({ request }) => {
        distillBody = await request.json();
        return HttpResponse.json({
          agent_id: 'agent-1',
          created_count: 2,
          skipped_count: 0,
          items: [],
        });
      }),
    );

    const user = userEvent.setup();
    render(<WikiPage />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole('combobox', { name: '에이전트 선택' }),
    );
    await user.click(await screen.findByRole('option', { name: /문서 분석가/ }));

    await user.click(screen.getByRole('combobox', { name: '컬렉션 선택' }));
    await user.click(await screen.findByRole('option', { name: /전체 문서/ }));

    await user.click(screen.getByRole('button', { name: '정제 실행' }));

    expect(await screen.findByText(/2개 초안이 생성되었습니다/)).toBeInTheDocument();
    expect(distillBody).toEqual({
      agent_id: 'agent-1',
      collection_name: 'documents',
    });
  });

  it('T4: 에이전트·컬렉션 선택 전에는 정제 버튼이 비활성화된다', async () => {
    const user = userEvent.setup();
    render(<WikiPage />, { wrapper: createWrapper() });

    const distillButton = screen.getByRole('button', { name: '정제 실행' });
    expect(distillButton).toBeDisabled();

    await user.click(
      await screen.findByRole('combobox', { name: '에이전트 선택' }),
    );
    await user.click(await screen.findByRole('option', { name: /문서 분석가/ }));
    expect(distillButton).toBeDisabled();

    await user.click(screen.getByRole('combobox', { name: '컬렉션 선택' }));
    await user.click(await screen.findByRole('option', { name: /전체 문서/ }));
    expect(distillButton).toBeEnabled();
  });

  it('T5: 직접 입력 토글 시 텍스트 입력으로 에이전트 ID를 넣어 목록이 로드된다', async () => {
    const user = userEvent.setup();
    render(<WikiPage />, { wrapper: createWrapper() });

    await user.click(screen.getByRole('button', { name: '직접 입력' }));
    await user.type(screen.getByPlaceholderText('agent_id'), 'agent-1');
    expect(await screen.findByText('위키-w1')).toBeInTheDocument();
  });

  it('드롭다운으로 에이전트 선택 시 위키 목록이 로드된다', async () => {
    const user = userEvent.setup();
    render(<WikiPage />, { wrapper: createWrapper() });

    await user.click(
      await screen.findByRole('combobox', { name: '에이전트 선택' }),
    );
    await user.click(await screen.findByRole('option', { name: /문서 분석가/ }));
    expect(await screen.findByText('위키-w1')).toBeInTheDocument();
  });
});
