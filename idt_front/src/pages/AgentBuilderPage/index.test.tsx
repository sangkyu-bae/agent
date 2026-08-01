import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AgentBuilderPage from './index';

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
      requires_env: [],
      is_builtin: false,
    },
  ],
};

const LLM_MODELS = [
  {
    id: 'model-1',
    provider: 'openai',
    model_name: 'gpt-4o',
    display_name: 'GPT-4o',
    description: null,
    max_tokens: null,
    is_active: true,
    is_default: true,
    base_url: null,
    input_price_per_1k_usd: null,
    output_price_per_1k_usd: null,
    pricing_updated_at: null,
  },
];

/** builtin-tools D8 페이지 검증용 공통 핸들러 */
const useBuilderHandlers = () => {
  server.use(
    http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
    http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
  );
};

const renderPage = () =>
  render(<AgentBuilderPage />, { wrapper: createWrapper() });

/** list → create 진입 + 필수값(이름·지침) 입력 */
const enterCreateView = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await screen.findByRole('button', { name: '새 에이전트' }));
  await user.type(screen.getByPlaceholderText('새 에이전트'), '테스트 에이전트');
  await user.type(
    screen.getByPlaceholderText('에이전트의 시스템 프롬프트/지침을 입력하세요...'),
    '테스트 지침',
  );
};

describe('AgentBuilderPage 빌트인 도구 (builtin-tools D8)', () => {
  it('빌트인 미해제 저장 → exclude_builtin_tool_ids를 전송하지 않는다', async () => {
    useBuilderHandlers();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/agents', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-1',
          name: '테스트 에이전트',
          system_prompt: '테스트 지침',
          tool_ids: ['wiki_read', 'wiki_list'],
          workers: [],
          flow_hint: '',
          llm_model_id: 'model-1',
          visibility: 'private',
          temperature: 0.7,
          max_iterations: 25,
          created_at: '2026-08-01T00:00:00Z',
          has_sub_agents: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    // 빌트인 칩이 기본 표시된다
    expect(screen.getByText('에이전트 위키 열람')).toBeInTheDocument();
    expect(screen.getAllByText('기본').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.exclude_builtin_tool_ids).toBeUndefined();
  });

  it('Fix 초안 적용 → 빌트인은 form.tools 미혼입 + excluded 불변 (G1: 채팅 우회 차단)', async () => {
    useBuilderHandlers();
    let captured: Record<string, unknown> | null = null;
    server.use(
      // 초안이 빌트인(wiki_read)을 포함해 와도 폼/전송에 혼입되면 안 된다
      http.post('*/api/v1/agents/compose', () =>
        HttpResponse.json({
          coverage: 'full',
          name_suggestion: '뉴스 수집기',
          system_prompt: '초안 지침',
          tool_ids: ['wiki_read', 'tavily_search'],
          workers: [],
          flow_hint: 'tavily_search',
          llm_model_id: 'model-1',
          temperature: 0.7,
          missing_capabilities: [],
          notes: [],
        }),
      ),
      http.post('*/api/v1/agents', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-1',
          name: '뉴스 수집기',
          system_prompt: '초안 지침',
          tool_ids: ['tavily_search', 'wiki_read', 'wiki_list'],
          workers: [],
          flow_hint: 'tavily_search',
          llm_model_id: 'model-1',
          visibility: 'private',
          temperature: 0.7,
          max_iterations: 25,
          created_at: '2026-08-01T00:00:00Z',
          has_sub_agents: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    // Fix 탭 → 채팅 → 초안 적용
    await user.click(screen.getByRole('button', { name: 'Fix 에이전트' }));
    await user.type(
      screen.getByLabelText('Fix 에이전트 입력'),
      '뉴스 수집 에이전트로 바꿔줘{Enter}',
    );
    await user.click(await screen.findByRole('button', { name: '적용하기' }));

    // 빌트인 칩은 여전히 표시된다 (excluded 불변)
    expect(screen.getAllByText('에이전트 위키 열람').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    // 초안의 wiki_read는 tool_ids에서 필터링되고, exclude도 생기지 않는다
    expect(captured!.tool_ids).toEqual(['internal:tavily_search']);
    expect(captured!.exclude_builtin_tool_ids).toBeUndefined();
  });

  it('빌트인 칩 제거 후 저장 → exclude_builtin_tool_ids로 전송된다', async () => {
    useBuilderHandlers();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/agents', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-1',
          name: '테스트 에이전트',
          system_prompt: '테스트 지침',
          tool_ids: [],
          workers: [],
          flow_hint: '',
          llm_model_id: 'model-1',
          visibility: 'private',
          temperature: 0.7,
          max_iterations: 25,
          created_at: '2026-08-01T00:00:00Z',
          has_sub_agents: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    await user.click(
      screen.getByRole('button', { name: '에이전트 위키 열람 제거' }),
    );
    // 해제 후 빌트인 칩이 사라진다
    expect(screen.queryByText('에이전트 위키 열람')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.exclude_builtin_tool_ids).toEqual(['internal:wiki_read']);
  });
});
