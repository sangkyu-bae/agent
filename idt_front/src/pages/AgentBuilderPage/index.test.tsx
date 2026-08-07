import { render, screen, waitFor, fireEvent } from '@testing-library/react';
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

// ── agent-settings-tab Design §5-3 ─────────────────────────────

const EDIT_SUMMARY = {
  agent_id: 'a-9',
  name: '수정용 봇',
  description: '설명',
  visibility: 'private',
  department_name: null,
  owner_user_id: 'u1',
  owner_email: null,
  temperature: 0.7,
  can_edit: true,
  can_delete: true,
  created_at: '2026-08-01T00:00:00Z',
};

const EDIT_DETAIL = {
  agent_id: 'a-9',
  name: '수정용 봇',
  description: '설명',
  system_prompt: '기존 지침',
  tool_ids: [],
  skill_ids: [],
  middleware_types: [],
  max_iterations: 500,
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  status: 'active',
  visibility: 'private',
  department_id: null,
  department_name: null,
  temperature: 0.7,
  owner_user_id: 'u1',
  can_edit: true,
  can_delete: true,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
};

describe('AgentBuilderPage 설정 탭 (agent-settings-tab)', () => {
  it('create 저장 → max_iterations 기본값 25가 전송된다', async () => {
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

    // 설정 탭이 활성화되어 진입 가능하다
    await user.click(screen.getByRole('button', { name: '설정' }));
    expect(
      screen.getByRole('spinbutton', { name: '최대 반복 횟수' }),
    ).toHaveValue(25);

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.max_iterations).toBe(25);
  });

  it('edit 프라임(500) → 300으로 수정 저장 → update에 max_iterations가 실린다', async () => {
    useBuilderHandlers();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () => HttpResponse.json(EDIT_DETAIL)),
      http.patch('*/api/v1/agents/a-9', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-9',
          name: '수정용 봇',
          system_prompt: '기존 지침',
          updated_at: '2026-08-02T00:00:00Z',
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    // list → edit 진입 → detail 프라임 대기 (이름 입력이 채워짐)
    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    // 설정 탭 — detail의 max_iterations(500)가 프라임되어 표시된다
    await user.click(screen.getByRole('button', { name: '설정' }));
    const input = screen.getByRole('spinbutton', { name: '최대 반복 횟수' });
    expect(input).toHaveValue(500);

    fireEvent.change(input, { target: { value: '300' } });
    fireEvent.blur(input);

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.max_iterations).toBe(300);
  });
});
