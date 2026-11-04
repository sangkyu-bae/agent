import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/__tests__/mocks/server';
import { useAuthStore } from '@/store/authStore';
import AgentDetailModal from './AgentDetailModal';

// authClient 인터셉터가 getState() 로 토큰을 읽으므로 모듈 mock 대신 실제 스토어에 넣는다.
beforeAll(() => {
  server.listen();
  useAuthStore.setState({
    user: { id: 2, email: 'u@t.com', role: 'user', status: 'approved' } as never,
    isAuthenticated: true,
  });
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  server.close();
  useAuthStore.setState({ user: null, isAuthenticated: false });
});

const DETAIL = {
  agent_id: 'a1', name: '공개 에이전트', description: 'd', system_prompt: 'p',
  tool_ids: ['excel_export', 'python_code_executor'], workers: [], flow_hint: '',
  llm_model_id: 'm', status: 'active', visibility: 'public', department_id: null,
  department_name: null, temperature: 0.5, owner_user_id: '1',
  can_edit: false, can_delete: false, created_at: '', updated_at: '',
};

const FORK = {
  agent_id: 'f1', name: '공개 에이전트 (사본)', forked_from: 'a1', forked_at: '', system_prompt: 'p',
  workers: [], visibility: 'private', temperature: 0.5, llm_model_id: 'm',
};

const renderModal = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AgentDetailModal agentId="a1" isOpen onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const fork = async () => {
  await userEvent.click(await screen.findByRole('button', { name: '포크하기' }));
  await userEvent.click(screen.getByRole('button', { name: '확인' }));
};

describe('AgentDetailModal — 포크 권한 제외 안내 (tool-access-control FR-08)', () => {
  it('excluded_tools 가 있으면 제외된 도구를 알린다', async () => {
    server.use(
      http.get('*/api/v1/agents/a1', () => HttpResponse.json(DETAIL)),
      http.post('*/api/v1/agents/a1/fork', () =>
        HttpResponse.json(
          { ...FORK, excluded_tools: [{ tool_id: 'internal:python_code_executor', name: 'Python 코드 실행', reason: 'no_permission' }] },
          { status: 201 },
        ),
      ),
    );
    renderModal();
    await fork();
    expect(
      await screen.findByText('복제본에서 권한이 없는 도구를 제외했습니다: Python 코드 실행'),
    ).toBeInTheDocument();
  });

  it('제외 도구가 없으면 안내하지 않는다', async () => {
    server.use(
      http.get('*/api/v1/agents/a1', () => HttpResponse.json(DETAIL)),
      http.post('*/api/v1/agents/a1/fork', () => HttpResponse.json(FORK, { status: 201 })),
    );
    renderModal();
    await fork();
    await screen.findByRole('button', { name: '포크하기' });
    expect(screen.queryByText(/복제본에서 권한이 없는 도구/)).not.toBeInTheDocument();
  });
});
