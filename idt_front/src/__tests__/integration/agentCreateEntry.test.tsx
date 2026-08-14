// agent-create-entry Design §8.4 — 진입 화면 → 핸드오프 → 스튜디오 프리필 L3 통합 시나리오.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, afterEach, afterAll, beforeEach, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import AgentBuilderPage from '@/pages/AgentBuilderPage';
import AgentCreateEntryPage from '@/pages/AgentCreateEntryPage';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  navigateMock.mockClear();
  useAgentDraftStore.getState().clearPendingIntent();
});

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

const DRAFT = {
  status: 'draft',
  coverage: 'full',
  name_suggestion: '규정 봇',
  system_prompt: '너는 사내 규정 안내 봇이다.',
  tool_ids: ['tavily_search'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  temperature: 0.4,
  missing_capabilities: [],
  notes: '',
} as unknown as ComposeAgentDraftResponse;

/** @param delayMs 도구·모델 쿼리 응답 지연 (G5 검증용) */
const useBuilderHandlers = (delayMs = 0) => {
  server.use(
    http.get('*/api/v1/tool-catalog', async () => {
      if (delayMs) await delay(delayMs);
      return HttpResponse.json(CATALOG);
    }),
    http.get('*/api/v1/llm-models', async () => {
      if (delayMs) await delay(delayMs);
      // useLlmModels는 select로 data.models를 꺼낸다
      return HttpResponse.json({ models: LLM_MODELS, total: LLM_MODELS.length });
    }),
  );
};

const renderStudio = () =>
  render(
    <MemoryRouter>
      <AgentBuilderPage />
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

const nameInput = () => screen.getByPlaceholderText('새 에이전트');
const promptInput = () =>
  screen.getByPlaceholderText('에이전트의 시스템 프롬프트/지침을 입력하세요...');

describe('agent-create-entry L3 — 초안 핸드오프', () => {
  it('시나리오 1: 초안 의도를 적재하면 스튜디오가 create 뷰로 프리필된다', async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });

    renderStudio();

    await waitFor(() => expect(nameInput()).toHaveValue('규정 봇'));
    expect(promptInput()).toHaveValue('너는 사내 규정 안내 봇이다.');
    expect(await screen.findByText('Tavily 웹 검색')).toBeInTheDocument();

    // 모델은 id → model_name 역매핑 후 `provider:model_name`으로 표시된다
    expect(await screen.findByText(/gpt-4o/)).toBeInTheDocument();
  });

  it('시나리오 2 (G5): 도구·모델 쿼리가 지연돼도 도구 칩이 정상 반영된다', async () => {
    useBuilderHandlers(80);
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });

    renderStudio();

    // 쿼리 settled 전에는 소비하지 않는다 — 지연 해제 후 매핑 성공해야 한다
    expect(await screen.findByText('Tavily 웹 검색')).toBeInTheDocument();
    expect(nameInput()).toHaveValue('규정 봇');
  });

  it('시나리오 3 (G2/G4): 소비는 1회 — 리렌더해도 사용자의 수정이 덮이지 않는다', async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });
    const user = userEvent.setup();

    renderStudio();
    await waitFor(() => expect(nameInput()).toHaveValue('규정 봇'));
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();

    await user.clear(nameInput());
    await user.type(nameInput(), '내가 고친 이름');
    // 폼 상태 변경 → 리렌더 유발
    await user.type(promptInput(), ' 추가 지침');

    expect(nameInput()).toHaveValue('내가 고친 이름');
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  it('시나리오 4 (G3): 진입 화면 재진입 시 이전 초안이 남지 않는다', async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });

    const { unmount } = render(
      <MemoryRouter>
        <AgentCreateEntryPage />
      </MemoryRouter>,
      { wrapper: createWrapper() },
    );
    await waitFor(() =>
      expect(useAgentDraftStore.getState().pendingIntent).toBeNull(),
    );
    unmount();

    renderStudio();
    // 유령 초안이 적용되지 않고 목록 뷰로 남는다
    expect(await screen.findByRole('button', { name: '새 에이전트' })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('새 에이전트')).not.toBeInTheDocument();
  });

  it("시나리오 4-b: kind='blank' 의도는 빈 create 스튜디오로 진입한다", async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'blank' });

    renderStudio();

    await waitFor(() => expect(nameInput()).toBeInTheDocument());
    expect(nameInput()).toHaveValue('');
    expect(promptInput()).toHaveValue('');
  });

  it('시나리오 5 (FR-11): 진입 화면 경유 스튜디오의 [취소]는 진입 화면으로 돌아간다', async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });
    const user = userEvent.setup();

    renderStudio();
    await waitFor(() => expect(nameInput()).toHaveValue('규정 봇'));

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(navigateMock).toHaveBeenCalledWith('/agent-builder/new');
  });

  it('시나리오 6: 목록 헤더 [새 에이전트]는 기존대로 빈 스튜디오 직행 — 취소는 목록으로', async () => {
    useBuilderHandlers();
    const user = userEvent.setup();

    renderStudio();
    await user.click(await screen.findByRole('button', { name: '새 에이전트' }));

    expect(nameInput()).toHaveValue('');
    expect(navigateMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(await screen.findByRole('button', { name: '새 에이전트' })).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
