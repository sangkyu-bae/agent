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
      category: null,
      max_tool_calls: null,
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
      category: 'search',
      max_tool_calls: null,
    },
    {
      tool_id: 'mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape',
      source: 'mcp',
      name: 'scrape',
      description: '웹 페이지 수집',
      mcp_server_id: '3f2a1b4c-0000-1111-2222-333344445555',
      mcp_server_name: 'scraper',
      requires_env: [],
      is_builtin: false,
      category: 'collect',
      max_tool_calls: 2,
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

describe('AdminToolsPage 카테고리·호출 상한 (mcp-tool-category-routing FR-13)', () => {
  it('도구별 현재 분류와 호출 상한을 표시한다', async () => {
    useCatalog();
    renderPage();
    await screen.findByText('scrape');

    expect(
      screen.getByRole('combobox', { name: 'scrape 분류' }),
    ).toHaveValue('collect');
    expect(
      screen.getByRole('combobox', { name: '에이전트 위키 열람 분류' }),
    ).toHaveValue('');
    expect(
      screen.getByRole('spinbutton', { name: 'scrape 호출 상한' }),
    ).toHaveValue(2);
  });

  it('분류 변경 시 PATCH /metadata 로 tool_id·category만 전송한다', async () => {
    useCatalog();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/tool-catalog/metadata', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          tool_id: captured.tool_id,
          category: captured.category,
          max_tool_calls: 2,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('scrape');

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'scrape 분류' }),
      'search',
    );

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({
      tool_id: 'mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape',
      category: 'search',
    });
  });

  it('분류를 미분류로 되돌리면 category: null 을 명시적으로 전송한다', async () => {
    useCatalog();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/tool-catalog/metadata', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          tool_id: captured.tool_id,
          category: null,
          max_tool_calls: 2,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('scrape');

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'scrape 분류' }),
      '',
    );

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toHaveProperty('category', null);
    expect(captured).not.toHaveProperty('max_tool_calls');
  });

  it('호출 상한 변경 시 max_tool_calls만 전송한다', async () => {
    useCatalog();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/tool-catalog/metadata', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          tool_id: captured.tool_id,
          category: 'collect',
          max_tool_calls: captured.max_tool_calls,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('scrape');

    const input = screen.getByRole('spinbutton', { name: 'scrape 호출 상한' });
    await user.clear(input);
    await user.type(input, '5');
    await user.tab();

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({
      tool_id: 'mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape',
      max_tool_calls: 5,
    });
  });

  it('서버 단위 MCP 도구에 collect 지정 시 400 메시지를 노출한다 (D-04)', async () => {
    useCatalog();
    server.use(
      http.patch('*/api/v1/tool-catalog/metadata', () =>
        HttpResponse.json(
          { detail: 'collect category requires a single-tool reference' },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('scrape');

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'scrape 분류' }),
      'analysis',
    );

    expect(
      await screen.findByText(
        /single-tool reference|분류 변경에 실패했습니다/,
      ),
    ).toBeInTheDocument();
  });
});
