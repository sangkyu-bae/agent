import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminToolsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CATALOG = {
  tools: [
    {
      tool_id: 'internal:wiki_read',
      source: 'internal',
      name: '에이전트 위키 열람',
      description: '위키 문서 열람',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: [],
      is_builtin: true,
    },
    {
      tool_id: 'internal:tavily_search',
      source: 'internal',
      name: 'Tavily 웹 검색',
      description: '웹 검색',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: ['TAVILY_API_KEY'],
      is_builtin: false,
    },
  ],
};

const useCatalog = () =>
  server.use(
    http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
  );

const renderPage = () =>
  render(<AdminToolsPage />, { wrapper: createWrapper() });

describe('AdminToolsPage (builtin-tools D9)', () => {
  it('카탈로그 목록과 빌트인 상태를 렌더한다', async () => {
    useCatalog();
    renderPage();
    expect(await screen.findByText('에이전트 위키 열람')).toBeInTheDocument();
    expect(screen.getByText('Tavily 웹 검색')).toBeInTheDocument();
    // 빌트인 행에만 "기본" 배지
    expect(screen.getAllByText('기본')).toHaveLength(1);
    expect(
      screen.getByRole('switch', { name: '에이전트 위키 열람 빌트인' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(
      screen.getByRole('switch', { name: 'Tavily 웹 검색 빌트인' }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  it('스위치 토글 시 PATCH 바디로 tool_id·반전값을 전송한다', async () => {
    useCatalog();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/tool-catalog/builtin', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          tool_id: captured.tool_id,
          is_builtin: captured.is_builtin,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tavily 웹 검색');

    await user.click(
      screen.getByRole('switch', { name: 'Tavily 웹 검색 빌트인' }),
    );
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      tool_id: 'internal:tavily_search',
      is_builtin: true,
    });
  });

  it('토글 실패 시 에러 배너를 표시한다', async () => {
    useCatalog();
    server.use(
      http.patch('*/api/v1/tool-catalog/builtin', () =>
        HttpResponse.json({ detail: '권한이 없습니다' }, { status: 403 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Tavily 웹 검색');

    await user.click(
      screen.getByRole('switch', { name: 'Tavily 웹 검색 빌트인' }),
    );
    expect(
      await screen.findByText(/권한이 없습니다|빌트인 설정 변경에 실패했습니다/),
    ).toBeInTheDocument();
  });
});
