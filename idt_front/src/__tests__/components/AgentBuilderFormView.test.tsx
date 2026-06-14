import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import AgentBuilderPage from '@/pages/AgentBuilderPage/index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderWithProviders = (ui: ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
};

describe('AgentBuilderPage — FormView 도구 연결', () => {
  it('로딩 중 스켈레톤 UI 를 표시한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, async () => {
        await new Promise((r) => setTimeout(r, 5000));
        return HttpResponse.json({ tools: [] });
      }),
    );

    renderWithProviders(<AgentBuilderPage />);

    const newBtn = screen.getByRole('button', { name: /새 에이전트/ });
    await userEvent.click(newBtn);

    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('도구 목록을 서버 데이터로 표시한다', async () => {
    renderWithProviders(<AgentBuilderPage />);

    const newBtn = screen.getByRole('button', { name: /새 에이전트/ });
    await userEvent.click(newBtn);

    expect(await screen.findByText('Excel 파일 생성')).toBeInTheDocument();
    expect(screen.getByText('search')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
  });

  it('도구 클릭 시 선택되고, 재클릭 시 해제된다', async () => {
    renderWithProviders(<AgentBuilderPage />);

    const newBtn = screen.getByRole('button', { name: /새 에이전트/ });
    await userEvent.click(newBtn);

    const excelTool = await screen.findByText('Excel 파일 생성');
    const toolButton = excelTool.closest('button')!;

    await userEvent.click(toolButton);
    expect(toolButton.className).toContain('border-violet');

    await userEvent.click(toolButton);
    expect(toolButton.className).not.toContain('border-violet-300');
  });

  it('도구를 선택하고 저장하면 tool_ids 로 서버에 전송된다', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            agent_id: 'new-agent-1',
            name: capturedBody.name,
            system_prompt: '',
            tool_ids: (capturedBody.tool_ids as string[]) ?? [],
            workers: [],
            flow_hint: '',
            llm_model_id: 'm-1',
            visibility: 'private',
            visibility_clamped: false,
            max_visibility: null,
            department_id: null,
            temperature: 0.7,
            created_at: '2026-05-31T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<AgentBuilderPage />);
    await userEvent.click(screen.getByRole('button', { name: /새 에이전트/ }));

    const nameInput = await screen.findByPlaceholderText('예: 문서 분석가');
    await userEvent.type(nameInput, '엑셀 도우미');

    const excelTool = (await screen.findByText('Excel 파일 생성')).closest('button')!;
    await userEvent.click(excelTool);

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.tool_ids).toEqual(['internal:excel_export']);
  });

  it('도구를 선택하지 않으면 tool_ids 가 전송되지 않는다 (AI 자동 선택)', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            agent_id: 'new-agent-2', name: capturedBody.name, system_prompt: '',
            tool_ids: [], workers: [], flow_hint: '', llm_model_id: 'm-1',
            visibility: 'private', visibility_clamped: false, max_visibility: null,
            department_id: null, temperature: 0.7, created_at: '2026-05-31T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<AgentBuilderPage />);
    await userEvent.click(screen.getByRole('button', { name: /새 에이전트/ }));

    const nameInput = await screen.findByPlaceholderText('예: 문서 분석가');
    await userEvent.type(nameInput, 'AI 자동 에이전트');

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.tool_ids).toBeUndefined();
  });

  it('생성 모드에서 MCP 도구는 선택이 비활성화된다', async () => {
    renderWithProviders(<AgentBuilderPage />);
    await userEvent.click(screen.getByRole('button', { name: /새 에이전트/ }));

    const mcpTool = (await screen.findByText('search')).closest('button')!;
    expect(mcpTool).toBeDisabled();
  });

  it('에러 상태에서 다시 시도 버튼을 표시한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 }),
      ),
    );

    renderWithProviders(<AgentBuilderPage />);

    const newBtn = screen.getByRole('button', { name: /새 에이전트/ });
    await userEvent.click(newBtn);

    expect(await screen.findByText('도구 목록을 불러올 수 없습니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /다시 시도/ })).toBeInTheDocument();
  });
});
