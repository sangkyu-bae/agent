// agent-create-wizard Design §8.5 — L3: 위저드 완주 → 핸드오프 → 스튜디오 저장 →
// 프롬프트 세션 append/bind 까지의 통합 시나리오.
//
// 구 `agentCreateEntry.test.tsx`(Design §11.1 [제거])가 담당하던 회귀 —
// 스튜디오 프리필 · 1회 소비(G2/G4) · 재진입 시 유령 초안 제거(G3) ·
// 진입 경유 [뒤로] 복귀 — 를 여기로 흡수했다.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import type {
  AgentPipelineResponse,
  PipelineStage,
  PipelineStageStatus,
  PipelineStepOut,
} from '@/types/agentPipeline';
import AgentBuilderPage from '@/pages/AgentBuilderPage';
import AgentCreateEntryPage from '@/pages/AgentCreateEntryPage';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useAgentDraftStore.getState().clearPendingIntent();
});
afterAll(() => server.close());

beforeEach(() => {
  navigateMock.mockClear();
  useAgentDraftStore.getState().clearPendingIntent();
});

// ── 픽스처 ──────────────────────────────────────────────────────────────────

const TOOLS = [
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
  {
    tool_id: 'internal:excel_export',
    source: 'internal',
    name: '엑셀 내보내기',
    description: '표를 저장한다',
    mcp_server_id: null,
    mcp_server_name: null,
    requires_env: [],
    is_builtin: false,
  },
];

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

const LLM_PROMPT = '당신은 사내 문서를 찾아 답하는 에이전트입니다.';

const STAGES: readonly PipelineStage[] = [
  'intent',
  'tools',
  'prompt',
  'create',
  'bind',
];

const steps = (
  reached: Partial<Record<PipelineStage, PipelineStageStatus>>,
): PipelineStepOut[] =>
  STAGES.map((stage) => ({
    stage,
    status: reached[stage] ?? 'skipped',
    reason: null,
    elapsed_ms: 1,
  }));

const result = (
  partial: Partial<AgentPipelineResponse>,
): AgentPipelineResponse => ({
  status: 'created',
  round: 0,
  steps: steps({}),
  degraded_stages: [],
  questions: [],
  intent: null,
  recommended_tool_ids: [],
  final_tool_ids: [],
  unknown_tool_ids: [],
  session_id: null,
  version_id: null,
  agent_id: null,
  agent_name: null,
  assembled_prompt: null,
  suggested_name: null,
  prompt_clamp_reason: null,
  bind_ok: null,
  ...partial,
});

const NEED_INPUT = result({
  status: 'need_input',
  round: 1,
  steps: steps({ intent: 'ok' }),
  questions: [
    {
      slot_key: 'purpose',
      question: '이 에이전트의 핵심 용도는 무엇인가요?',
      options: ['문서 Q&A', '보고서 작성'],
      allow_free_text: true,
    },
  ],
  intent: {
    label: null,
    filled_slots: {},
    missing_slots: ['purpose'],
    degraded: false,
  },
});

const TOOLS_PROPOSED = result({
  status: 'tools_proposed',
  round: 1,
  steps: steps({ intent: 'ok', tools: 'ok' }),
  recommended_tool_ids: ['internal:tavily_search', 'internal:excel_export'],
  final_tool_ids: ['internal:tavily_search', 'internal:excel_export'],
  suggested_name: '문서 Q&A 봇',
  intent: {
    label: 'agent_build',
    filled_slots: { purpose: '문서 Q&A' },
    missing_slots: [],
    degraded: false,
  },
});

const PROMPT_READY = result({
  status: 'prompt_ready',
  round: 1,
  steps: steps({ intent: 'ok', tools: 'ok', prompt: 'ok' }),
  recommended_tool_ids: ['internal:tavily_search'],
  final_tool_ids: ['internal:tavily_search'],
  session_id: 'ps1',
  version_id: 'pv1',
  assembled_prompt: LLM_PROMPT,
  suggested_name: '문서 Q&A 봇',
});

const CREATED_AGENT = {
  agent_id: 'a-w1',
  name: '문서 Q&A 봇',
  system_prompt: LLM_PROMPT,
  tool_ids: ['tavily_search'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  visibility: 'private',
  visibility_clamped: false,
  max_visibility: 'public',
  department_id: null,
  temperature: 0.7,
  max_iterations: 25,
  created_at: '2026-08-20T00:00:00Z',
  has_sub_agents: false,
};

// ── MSW ────────────────────────────────────────────────────────────────────

const sseBody = (
  payload: AgentPipelineResponse,
  reached: readonly PipelineStage[],
) => {
  let seq = 0;
  const block = (event: string, data: unknown) =>
    `event: ${event}\nid: ${seq++}\ndata: ${JSON.stringify(data)}\n\n`;
  const parts = reached.flatMap((stage) => [
    block('stage_started', { stage }),
    block('stage_completed', {
      stage,
      status: 'ok',
      reason: null,
      elapsed_ms: 1,
    }),
  ]);
  parts.push(block('pipeline_result', payload));
  return parts.join('');
};

/** @param delayMs 카탈로그·모델 응답 지연 (핸드오프 G5 검증용) */
const stubCatalog = (delayMs = 0) =>
  server.use(
    http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, async () => {
      if (delayMs) await delay(delayMs);
      return HttpResponse.json({ tools: TOOLS });
    }),
    http.get(`*${API_ENDPOINTS.LLM_MODELS}`, async () => {
      if (delayMs) await delay(delayMs);
      return HttpResponse.json({ models: LLM_MODELS, total: LLM_MODELS.length });
    }),
  );

/** 파이프라인 SSE — 호출 순서대로 응답하고 요청 본문을 기록한다. */
const stubPipeline = (payloads: string[]) => {
  const requests: Record<string, unknown>[] = [];
  let call = 0;
  server.use(
    http.post(`*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`, async ({ request }) => {
      requests.push((await request.json()) as Record<string, unknown>);
      const body = payloads[Math.min(call, payloads.length - 1)];
      call += 1;
      return new HttpResponse(body, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }),
  );
  return requests;
};

interface SaveCalls {
  creates: Record<string, unknown>[];
  versions: Record<string, unknown>[];
  binds: Record<string, unknown>[];
}

const stubSave = (bindStatus = 200): SaveCalls => {
  const calls: SaveCalls = { creates: [], versions: [], binds: [] };
  server.use(
    http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
      calls.creates.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json(CREATED_AGENT);
    }),
    http.post(
      '*/api/v1/prompt-composer/sessions/:id/versions',
      async ({ request }) => {
        calls.versions.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { session_id: 'ps1', version_id: 'pv2', version_no: 2, source: 'human' },
          { status: 201 },
        );
      },
    ),
    http.patch(
      '*/api/v1/prompt-composer/sessions/:id',
      async ({ request }) => {
        calls.binds.push((await request.json()) as Record<string, unknown>);
        return bindStatus === 200
          ? HttpResponse.json({ session_id: 'ps1', agent_id: 'a-w1' })
          : HttpResponse.json({ detail: 'conflict' }, { status: bindStatus });
      },
    ),
  );
  return calls;
};

// ── 헬퍼 ────────────────────────────────────────────────────────────────────

const renderWizard = () =>
  render(
    <MemoryRouter>
      <AgentCreateEntryPage />
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

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

/**
 * ① 설명 → ② 답변 → ③ 도구 확정(엑셀 해제) → ④ 프롬프트 까지 진행한다.
 * @returns 파이프라인 요청 본문 기록 + user
 */
const runWizardToPrompt = async () => {
  stubCatalog();
  const requests = stubPipeline([
    sseBody(NEED_INPUT, ['intent']),
    sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
    sseBody(PROMPT_READY, ['intent', 'tools', 'prompt']),
  ]);
  const { unmount } = renderWizard();
  const user = userEvent.setup();

  await user.type(
    screen.getByLabelText('에이전트 설명'),
    '사내 문서를 찾아주는 에이전트',
  );
  await user.click(screen.getByRole('button', { name: '에이전트 설명 전송' }));

  // ② 되묻기
  await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
  await user.click(screen.getByText('문서 Q&A'));
  await user.click(screen.getByRole('button', { name: '제출' }));

  // ③ 도구 확인 — 엑셀은 해제한다 (해제가 살아남는지 끝까지 본다)
  await screen.findByText('이 도구들을 사용할까요?');
  await screen.findByText('엑셀 내보내기');
  await user.click(
    screen
      .getByText('엑셀 내보내기')
      .closest('label')!
      .querySelector('input')!,
  );
  await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));

  // ④ 프롬프트
  await screen.findByText('시스템 프롬프트를 확인해주세요');
  return { requests, user, unmount };
};

/**
 * [스튜디오로 보내기] → 위저드 언마운트 → 스튜디오 렌더.
 *
 * 위저드를 반드시 먼저 언마운트한다: 실제로는 라우트가 바뀌어 한 화면만 살아
 * 있는데, 두 화면이 같은 문서에 남으면 도구 칩 같은 텍스트가 중복 매칭돼
 * 스튜디오가 아직 목록인 것도 통과해버린다.
 */
const handOffToStudio = async (
  user: ReturnType<typeof userEvent.setup>,
  unmount: () => void,
  catalogDelayMs = 0,
) => {
  await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));
  unmount();
  if (catalogDelayMs) stubCatalog(catalogDelayMs);
  renderStudio();
};

// ── 시나리오 1: 완주 ────────────────────────────────────────────────────────

describe('L3 #1 — 4스텝 완주 후 스튜디오 프리필', () => {
  it('설명 한 문장이 이름·지침·도구 칩까지 도달한다', async () => {
    const { requests, user, unmount } = await runWizardToPrompt();
    stubSave();

    // 단계별 정지 계약이 지켜졌는지 (왕복 3회)
    expect(requests).toHaveLength(3);
    expect(requests[0]).toMatchObject({ stop_after: 'tools' });
    expect(requests[1]).toMatchObject({
      stop_after: 'tools',
      round: 1,
      answers: [{ slot_key: 'purpose', value: '문서 Q&A' }],
    });
    expect(requests[2]).toMatchObject({
      stop_after: 'prompt',
      tools_confirmed: true,
      tool_ids: ['internal:tavily_search'],
    });

    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));

    expect(navigateMock).toHaveBeenCalledWith('/agent-builder');
    expect(useAgentDraftStore.getState().pendingIntent).toMatchObject({
      kind: 'wizard',
      result: {
        systemPrompt: LLM_PROMPT,
        promptEdited: false,
        toolIds: ['internal:tavily_search'],
        suggestedName: '문서 Q&A 봇',
        sessionId: 'ps1',
        versionId: 'pv1',
      },
    });

    // 라우터 이동 대신 스튜디오를 직접 렌더한다 — 핸드오프는 스토어 경유다.
    unmount();
    renderStudio();

    await waitFor(() => expect(nameInput()).toHaveValue('문서 Q&A 봇'));
    expect(promptInput()).toHaveValue(LLM_PROMPT);
    expect(await screen.findByText('Tavily 웹 검색')).toBeInTheDocument();
    // 해제한 도구는 스튜디오까지 살아 돌아오지 않는다 (D1 프론트 절반)
    expect(screen.queryByText('엑셀 내보내기')).not.toBeInTheDocument();
    // 소비는 1회 — 리렌더로 사용자의 수정이 덮이지 않는다 (G2/G4)
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  it('카탈로그 응답이 늦어도 도구 칩이 반영된다 (G5)', async () => {
    // 쿼리 settled 전에 의도를 소비하면 도구 매핑이 조용히 빈 칩으로 끝난다.
    const { user, unmount } = await runWizardToPrompt();

    await handOffToStudio(user, unmount, 80);

    expect(await screen.findByText('Tavily 웹 검색')).toBeInTheDocument();
    expect(nameInput()).toHaveValue('문서 Q&A 봇');
  });
});

// ── 시나리오 3: 저장 + 바인딩 ───────────────────────────────────────────────

describe('L3 #3 — 저장 후 프롬프트 세션 바인딩', () => {
  it('POST /agents 성공 후 PATCH /sessions/{id} 를 호출한다', async () => {
    const { user, unmount } = await runWizardToPrompt();
    const calls = stubSave();

    await handOffToStudio(user, unmount);
    await waitFor(() => expect(nameInput()).toHaveValue('문서 Q&A 봇'));
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(calls.binds).toHaveLength(1));
    expect(calls.binds[0]).toEqual({ agent_id: 'a-w1' });
    expect(calls.creates[0]).toMatchObject({
      name: '문서 Q&A 봇',
      system_prompt: LLM_PROMPT,
      tool_ids: ['internal:tavily_search'],
    });
    // 편집하지 않았으면 LLM 원본이 이미 최신 버전이다
    expect(calls.versions).toHaveLength(0);
    expect(
      await screen.findByText(/에이전트가 성공적으로 등록되었습니다/),
    ).toBeInTheDocument();
  });
});

// ── 시나리오 4: 프롬프트 편집 저장 ──────────────────────────────────────────

describe('L3 #4 — 사람이 편집한 프롬프트', () => {
  it('편집본으로 저장하고 human 버전을 append 한다', async () => {
    const { user, unmount } = await runWizardToPrompt();
    const calls = stubSave();

    await user.type(screen.getByLabelText('시스템 프롬프트'), ' 추가 지침.');
    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));

    expect(useAgentDraftStore.getState().pendingIntent).toMatchObject({
      kind: 'wizard',
      result: { promptEdited: true },
    });

    unmount();
    renderStudio();
    await waitFor(() => expect(nameInput()).toHaveValue('문서 Q&A 봇'));
    const edited = `${LLM_PROMPT} 추가 지침.`;
    expect(promptInput()).toHaveValue(edited);

    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(calls.versions).toHaveLength(1));
    expect(calls.versions[0]).toMatchObject({
      assembled: edited,
      tool_ids: ['internal:tavily_search'],
    });
    expect(calls.creates[0]).toMatchObject({ system_prompt: edited });
    await waitFor(() => expect(calls.binds).toHaveLength(1));
  });
});

// ── 시나리오 5: 바인딩 실패 내성 ────────────────────────────────────────────

describe('L3 #5 — 바인딩 실패 내성', () => {
  it('PATCH 가 409여도 저장은 성공으로 남고 경고만 붙는다', async () => {
    // 이미 쓸 수 있는 결과(저장된 에이전트)가 있으므로 백필 실패가 뒤집으면 안 된다.
    const { user, unmount } = await runWizardToPrompt();
    const calls = stubSave(409);

    await handOffToStudio(user, unmount);
    await waitFor(() => expect(nameInput()).toHaveValue('문서 Q&A 봇'));
    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(
      await screen.findByText(/에이전트가 성공적으로 등록되었습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/프롬프트 이력 연결에 실패/)).toBeInTheDocument();
    expect(calls.creates).toHaveLength(1);
  });
});

// ── 기존 경로 회귀 (구 agentCreateEntry.test.tsx 흡수) ──────────────────────

describe('L3 #7 — 기존 핸드오프 경로 회귀', () => {
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

  it("Fix 탭 경로(kind:'draft')의 스튜디오 프리필은 그대로다", async () => {
    stubCatalog();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });

    renderStudio();

    await waitFor(() => expect(nameInput()).toHaveValue('규정 봇'));
    expect(promptInput()).toHaveValue('너는 사내 규정 안내 봇이다.');
    expect(await screen.findByText('Tavily 웹 검색')).toBeInTheDocument();
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  it('진입 화면에 재진입하면 이전 초안이 남지 않는다 (G3)', async () => {
    stubCatalog();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft: DRAFT });

    const { unmount } = renderWizard();
    await waitFor(() =>
      expect(useAgentDraftStore.getState().pendingIntent).toBeNull(),
    );
    unmount();

    renderStudio();

    // 유령 초안이 적용되지 않고 목록 뷰로 남는다
    expect(
      await screen.findByRole('button', { name: '새 에이전트' }),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('새 에이전트')).not.toBeInTheDocument();
  });

  it('위저드 경유 스튜디오의 [뒤로]는 진입 화면으로 돌아간다', async () => {
    const { user, unmount } = await runWizardToPrompt();

    await handOffToStudio(user, unmount);
    navigateMock.mockClear();
    await waitFor(() => expect(nameInput()).toHaveValue('문서 Q&A 봇'));

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(navigateMock).toHaveBeenCalledWith('/agent-builder/new');
  });

  it('목록 헤더 [새 에이전트]는 빈 스튜디오 직행 — 취소는 목록으로', async () => {
    stubCatalog();
    const user = userEvent.setup();

    renderStudio();
    await user.click(await screen.findByRole('button', { name: '새 에이전트' }));

    expect(nameInput()).toHaveValue('');
    expect(navigateMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(
      await screen.findByRole('button', { name: '새 에이전트' }),
    ).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
