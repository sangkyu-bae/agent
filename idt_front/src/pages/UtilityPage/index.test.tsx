import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import UtilityPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ─── 픽스처 ─────────────────────────────────────────────────────────────────

const CATALOG = {
  tools: [
    {
      tool_id: 'internal:wiki_read',
      source: 'internal',
      name: '위키 열람',
      description: '에이전트 위키 문서를 열람합니다',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: [],
      is_builtin: true,
    },
    {
      tool_id: 'internal:tavily_search',
      source: 'internal',
      name: 'Tavily 웹 검색',
      description: '웹 검색을 수행합니다',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: ['TAVILY_API_KEY'],
      is_builtin: false,
    },
    {
      tool_id: 'mcp:srv-1:github_search',
      source: 'mcp',
      name: 'GitHub 검색',
      description: 'GitHub 저장소를 검색합니다',
      mcp_server_id: 'srv-1',
      mcp_server_name: 'GitHub MCP',
      requires_env: [],
      is_builtin: false,
    },
  ],
};

const MODELS = {
  models: [
    {
      id: 'm1',
      provider: 'openai',
      model_name: 'gpt-4o',
      display_name: 'GPT-4o',
      description: '범용 플래그십 모델',
      max_tokens: 128000,
      is_active: true,
      is_default: true,
    },
    {
      id: 'm2',
      provider: 'anthropic',
      model_name: 'claude-3-haiku',
      display_name: 'Claude 3 Haiku',
      description: null,
      max_tokens: 200000,
      is_active: false,
      is_default: false,
    },
  ],
};

const SKILLS = {
  skills: [
    {
      id: 's1',
      name: '보고서 요약 스킬',
      description: '주간 보고서를 요약합니다',
      script_type: 'none',
      visibility: 'public',
      owner_user_id: 'u1',
      forked_from: null,
      can_edit: false,
      can_delete: false,
      created_at: '2026-08-01T00:00:00Z',
    },
    {
      id: 's2',
      name: '데이터 정제 스킬',
      description: 'CSV 데이터를 정제합니다',
      script_type: 'python',
      visibility: 'private',
      owner_user_id: 'u1',
      forked_from: null,
      can_edit: true,
      can_delete: true,
      created_at: '2026-08-01T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  size: 100,
};

const useDefaultHandlers = () =>
  server.use(
    http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
    http.get('*/api/v1/llm-models', () => HttpResponse.json(MODELS)),
    http.post('*/api/v1/skills/list', () => HttpResponse.json(SKILLS)),
  );

const renderPage = () => render(<UtilityPage />, { wrapper: createWrapper() });

// ─── 테스트 ─────────────────────────────────────────────────────────────────

describe('UtilityPage', () => {
  it('T9: 헤더에 제목 유틸리티를 렌더한다', async () => {
    useDefaultHandlers();
    renderPage();
    expect(
      screen.getByRole('heading', { name: '유틸리티' }),
    ).toBeInTheDocument();
    await screen.findByText('위키 열람');
  });

  it('T1: 도구 탭 기본 렌더 — 카탈로그 3건과 유형 배지를 표시한다', async () => {
    useDefaultHandlers();
    renderPage();

    const wikiCard = await screen.findByRole('article', { name: '위키 열람' });
    expect(within(wikiCard).getByText('built-in')).toBeInTheDocument();

    const tavilyCard = screen.getByRole('article', { name: 'Tavily 웹 검색' });
    expect(within(tavilyCard).getByText('custom')).toBeInTheDocument();
    expect(within(tavilyCard).getByText(/TAVILY_API_KEY/)).toBeInTheDocument();

    const mcpCard = screen.getByRole('article', { name: 'GitHub 검색' });
    expect(within(mcpCard).getByText('mcp')).toBeInTheDocument();
    expect(within(mcpCard).getByText(/GitHub MCP/)).toBeInTheDocument();
  });

  it('T2: 유형 필터 — mcp 칩 클릭 시 mcp 도구만 남는다', async () => {
    useDefaultHandlers();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');

    await user.click(screen.getByRole('button', { name: 'mcp' }));
    expect(screen.getByText('GitHub 검색')).toBeInTheDocument();
    expect(screen.queryByText('위키 열람')).not.toBeInTheDocument();
    expect(screen.queryByText('Tavily 웹 검색')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '전체' }));
    expect(screen.getByText('위키 열람')).toBeInTheDocument();
  });

  it('T3: 검색 — 일치 카드만 남고 0건이면 안내 문구를 표시한다', async () => {
    useDefaultHandlers();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');

    const input = screen.getByPlaceholderText('검색...');
    await user.type(input, 'Tavily');
    expect(screen.getByText('Tavily 웹 검색')).toBeInTheDocument();
    expect(screen.queryByText('위키 열람')).not.toBeInTheDocument();

    await user.clear(input);
    await user.type(input, '존재하지않는도구');
    expect(screen.getByText('검색 결과가 없습니다')).toBeInTheDocument();
  });

  it('T4: 모델 탭 — 모델 목록과 비활성 배지를 렌더한다', async () => {
    useDefaultHandlers();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');

    await user.click(screen.getByRole('tab', { name: /모델/ }));

    const activeCard = await screen.findByRole('article', { name: 'GPT-4o' });
    expect(within(activeCard).getByText('openai')).toBeInTheDocument();
    expect(within(activeCard).getByText('기본')).toBeInTheDocument();

    const inactiveCard = screen.getByRole('article', { name: 'Claude 3 Haiku' });
    expect(within(inactiveCard).getByText('비활성')).toBeInTheDocument();
  });

  it('T5: 스킬 탭 — 스킬 목록과 배지를 렌더한다', async () => {
    useDefaultHandlers();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');

    await user.click(screen.getByRole('tab', { name: /스킬/ }));

    const publicCard = await screen.findByRole('article', {
      name: '보고서 요약 스킬',
    });
    expect(within(publicCard).getByText('public')).toBeInTheDocument();

    const pythonCard = screen.getByRole('article', { name: '데이터 정제 스킬' });
    expect(within(pythonCard).getByText('python')).toBeInTheDocument();
    expect(within(pythonCard).getByText('private')).toBeInTheDocument();
  });

  it('T6: 미들웨어 탭 — 준비 중 안내를 표시한다', async () => {
    useDefaultHandlers();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');

    await user.click(screen.getByRole('tab', { name: /미들웨어/ }));
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it('T7: 도구 API 실패 — 에러 문구와 다시 시도 버튼을 렌더한다', async () => {
    server.use(
      http.get('*/api/v1/tool-catalog', () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 }),
      ),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(MODELS)),
      http.post('*/api/v1/skills/list', () => HttpResponse.json(SKILLS)),
    );
    renderPage();

    expect(
      await screen.findByText('목록을 불러오지 못했습니다'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '다시 시도' }),
    ).toBeInTheDocument();
  });

  it('T8: 새로고침 — 버튼 클릭 시 목록을 재조회한다', async () => {
    let catalogCalls = 0;
    server.use(
      http.get('*/api/v1/tool-catalog', () => {
        catalogCalls += 1;
        return HttpResponse.json(CATALOG);
      }),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(MODELS)),
      http.post('*/api/v1/skills/list', () => HttpResponse.json(SKILLS)),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('위키 열람');
    expect(catalogCalls).toBe(1);

    await user.click(screen.getByRole('button', { name: '새로고침' }));
    await waitFor(() => expect(catalogCalls).toBe(2));
  });
});
