import { act, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { focusManager } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import type { WizardResult } from '@/store/agentDraftStore';
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

// agent-create-entry: 페이지가 [취소] 복귀 분기에 useNavigate를 쓰므로 Router가 필요
const renderPage = () =>
  render(
    <MemoryRouter>
      <AgentBuilderPage />
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

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
  // agent-token-limit: edit 프라임 검증용
  token_limit: 60000,
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

// ── doc-generator Design §5·§6: 문서 유형 왕복 (MSW 통합) ─────────

const GENERATOR_CATALOG = {
  tools: [
    ...CATALOG.tools,
    {
      tool_id: 'internal:document_generator',
      source: 'internal',
      name: '문서생성기',
      description: '문서 유형 기반 문서 작성',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: [],
      is_builtin: false,
    },
  ],
};

describe('AgentBuilderPage 문서생성기 (doc-generator)', () => {
  it('create: 도구 추가 → 유형 편집 → 저장 시 document_generation_type 전송', async () => {
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(GENERATOR_CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
    );
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/agents', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-1',
          name: '테스트 에이전트',
          system_prompt: '테스트 지침',
          tool_ids: ['document_generator'],
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

    // 도구함에서 문서생성기 추가 → 설정 모달 자동 오픈
    await user.click(screen.getByRole('button', { name: '도구' }));
    await user.click(await screen.findByRole('button', { name: /문서생성기/ }));
    expect(
      await screen.findByText('문서생성기 — 문서 유형'),
    ).toBeInTheDocument();

    // 유형 이름 + 섹션 1개 입력
    await user.type(screen.getByLabelText('문서 유형명'), '시장조사 보고서');
    await user.click(screen.getByRole('button', { name: '+ 섹션 추가' }));
    await user.type(screen.getByLabelText('섹션 1 제목'), '개요');
    await user.click(screen.getByRole('button', { name: '완료' }));

    // 도구함 배지에 요약 표시
    expect(screen.getByText(/시장조사 보고서 · 섹션 1/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.document_generation_type).toEqual({
      name: '시장조사 보고서',
      description: '',
      sections: [{ title: '개요', guidance: '' }],
      output_format: 'docx',
      mcp_html_to_doc_tool_id: '',
    });
  });

  it('create: 유형 미편집(섹션 0)이면 document_generation_type을 전송하지 않는다', async () => {
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
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.document_generation_type).toBeUndefined();
  });

  it('edit: detail 프리필 → 섹션 수정 저장 → 교체 payload 전송 (FR-12 왕복)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(GENERATOR_CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () =>
        HttpResponse.json({
          ...EDIT_DETAIL,
          tool_ids: ['document_generator'],
          workers: [
            {
              tool_id: 'document_generator',
              worker_id: 'document_generator_worker',
              description: '문서생성기',
              sort_order: 0,
              tool_config: {
                type_id: 't-1',
                mcp_html_to_doc_tool_id: 'mcp_h2d',
                output_format: 'docx',
              },
              worker_type: 'tool',
              ref_agent_id: null,
              ref_agent_name: null,
            },
          ],
          document_generation_type: {
            name: '시장조사 보고서',
            description: '시장 동향',
            sections: [
              { title: '개요', guidance: '' },
              { title: '시장 현황', guidance: '웹서치 근거 위주' },
            ],
            output_format: 'docx',
            mcp_html_to_doc_tool_id: 'mcp_h2d',
          },
        }),
      ),
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

    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    // 프리필 배지 확인 → 설정 열어 섹션 제목 수정
    expect(
      await screen.findByText(/시장조사 보고서 · 섹션 2/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '문서생성기 설정' }));
    const titleInput = screen.getByLabelText('섹션 2 제목');
    expect(titleInput).toHaveValue('시장 현황');
    await user.clear(titleInput);
    await user.type(titleInput, '경쟁 분석');
    await user.click(screen.getByRole('button', { name: '완료' }));

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.document_generation_type).toEqual({
      name: '시장조사 보고서',
      description: '시장 동향',
      sections: [
        { title: '개요', guidance: '' },
        { title: '경쟁 분석', guidance: '웹서치 근거 위주' },
      ],
      output_format: 'docx',
      mcp_html_to_doc_tool_id: 'mcp_h2d',
    });
  });
});

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
    // agent-token-limit D12: 토큰 예산 기본값도 함께 전송
    expect(captured!.token_limit).toBe(50000);
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

    // agent-token-limit D12: detail의 token_limit(60000) 프라임 → 70000으로 수정
    const tokenInput = screen.getByRole('spinbutton', { name: '토큰 예산' });
    expect(tokenInput).toHaveValue(60000);
    fireEvent.change(tokenInput, { target: { value: '70000' } });
    fireEvent.blur(tokenInput);

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.max_iterations).toBe(300);
    expect(captured!.token_limit).toBe(70000);
  });
});

// ── 위저드 핸드오프 (agent-create-wizard §2.2 / FR-F13) ─────────────────────

describe('AgentBuilderPage 위저드 핸드오프', () => {
  const WIZARD_RESULT: WizardResult = {
    systemPrompt: '당신은 사내 문서를 찾아 답하는 에이전트입니다.',
    promptEdited: false,
    toolIds: ['internal:tavily_search', 'internal:wiki_read'],
    suggestedName: '문서 Q&A 봇',
    sessionId: 'ps1',
    versionId: 'pv1',
  };

  const seedWizardIntent = (overrides: Partial<WizardResult> = {}) => {
    useAgentDraftStore.getState().setPendingIntent({
      kind: 'wizard',
      result: { ...WIZARD_RESULT, ...overrides },
    });
  };

  const stubCreate = () => {
    const calls: { versions: unknown[]; binds: unknown[] } = {
      versions: [],
      binds: [],
    };
    server.use(
      http.post('*/api/v1/agents', () =>
        HttpResponse.json({
          agent_id: 'a-w1',
          name: '문서 Q&A 봇',
          system_prompt: WIZARD_RESULT.systemPrompt,
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
        }),
      ),
      http.post('*/api/v1/prompt-composer/sessions/:id/versions', async ({ request }) => {
        calls.versions.push(await request.json());
        return HttpResponse.json(
          { session_id: 'ps1', version_id: 'pv2', version_no: 2, source: 'human' },
          { status: 201 },
        );
      }),
      http.patch('*/api/v1/prompt-composer/sessions/:id', async ({ request }) => {
        calls.binds.push(await request.json());
        return HttpResponse.json({ session_id: 'ps1', agent_id: 'a-w1' });
      }),
    );
    return calls;
  };

  afterEach(() => useAgentDraftStore.getState().clearPendingIntent());

  it('위저드 결과를 폼에 프리필한다', async () => {
    useBuilderHandlers();
    seedWizardIntent();
    renderPage();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    expect(
      screen.getByPlaceholderText('에이전트의 시스템 프롬프트/지침을 입력하세요...'),
    ).toHaveValue(WIZARD_RESULT.systemPrompt);
  });

  it('빌트인 도구는 칩으로 넣지 않는다', async () => {
    // internal:wiki_read 는 카탈로그상 빌트인이다 — 서버가 주입하므로 중복이다.
    useBuilderHandlers();
    seedWizardIntent();
    renderPage();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    expect(screen.getByText('Tavily 웹 검색')).toBeInTheDocument();
  });

  it('저장 성공 후 프롬프트 세션에 agent_id 를 바인딩한다', async () => {
    useBuilderHandlers();
    const calls = stubCreate();
    seedWizardIntent();
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    await waitFor(() => expect(calls.binds).toHaveLength(1));
    expect(calls.binds[0]).toEqual({ agent_id: 'a-w1' });
  });

  it('편집하지 않았으면 새 버전을 만들지 않는다', async () => {
    // 안 고쳤으면 LLM 원본이 이미 최신 버전이다 — 같은 내용을 또 쌓지 않는다.
    useBuilderHandlers();
    const calls = stubCreate();
    seedWizardIntent({ promptEdited: false });
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    await waitFor(() => expect(calls.binds).toHaveLength(1));
    expect(calls.versions).toHaveLength(0);
  });

  it('편집했으면 human 버전을 먼저 쌓는다', async () => {
    useBuilderHandlers();
    const calls = stubCreate();
    seedWizardIntent({
      promptEdited: true,
      systemPrompt: '사람이 고친 지침',
    });
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    await waitFor(() => expect(calls.versions).toHaveLength(1));
    expect(calls.versions[0]).toMatchObject({ assembled: '사람이 고친 지침' });
  });

  it('저장 403 TOOL_ACCESS_DENIED 면 권한 없는 도구 이름을 안내한다 (tool-access-control)', async () => {
    useBuilderHandlers();
    server.use(
      http.post('*/api/v1/agents', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'TOOL_ACCESS_DENIED',
              message: '권한이 없는 도구가 포함되어 있습니다',
              tool_ids: ['internal:tavily_search'],
            },
          },
          { status: 403 },
        ),
      ),
    );
    seedWizardIntent();
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    expect(
      await screen.findByText('권한이 없는 도구가 있어 저장할 수 없습니다: Tavily 웹 검색'),
    ).toBeInTheDocument();
  });

  it('바인딩이 409여도 저장은 성공으로 유지한다', async () => {
    // FR-F13 — 백필 실패가 생성 성공을 뒤집으면 안 된다.
    useBuilderHandlers();
    stubCreate();
    server.use(
      http.patch('*/api/v1/prompt-composer/sessions/:id', () =>
        HttpResponse.json({ detail: 'conflict' }, { status: 409 }),
      ),
    );
    seedWizardIntent();
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    expect(
      await screen.findByText(/에이전트가 성공적으로 등록되었습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/프롬프트 이력 연결에 실패/)).toBeInTheDocument();
  });

  it('세션이 없으면 부수 호출을 하지 않는다', async () => {
    useBuilderHandlers();
    const calls = stubCreate();
    seedWizardIntent({ sessionId: null, versionId: null });
    renderPage();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue('문서 Q&A 봇'),
    );
    await user.click(screen.getByRole('button', { name: /저장/ }));

    await screen.findByText(/에이전트가 성공적으로 등록되었습니다/);
    expect(calls.binds).toHaveLength(0);
    expect(calls.versions).toHaveLength(0);
  });

  it('blank 의도는 빈 폼으로 남는다 (회귀)', async () => {
    useBuilderHandlers();
    useAgentDraftStore.getState().setPendingIntent({ kind: 'blank' });
    renderPage();

    await waitFor(() =>
      expect(screen.getByPlaceholderText('새 에이전트')).toHaveValue(''),
    );
  });
});

// ── agent-update-tool-editing D §5: 수정 경로 도구 편집 (F-01/F-02/F-04) ──

describe('AgentBuilderPage 도구 편집 (agent-update-tool-editing)', () => {
  const editHandlers = (
    onPatch: (body: Record<string, unknown>) => void,
    detailOver: Record<string, unknown> = {},
    patchResponse: Record<string, unknown> = {},
  ) =>
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () =>
        HttpResponse.json({ ...EDIT_DETAIL, ...detailOver }),
      ),
      http.patch('*/api/v1/agents/a-9', async ({ request }) => {
        onPatch((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({
          agent_id: 'a-9',
          name: '수정용 봇',
          system_prompt: '기존 지침',
          updated_at: '2026-09-06T00:00:00Z',
          ...patchResponse,
        });
      }),
    );

  const openEdit = async (user: ReturnType<typeof userEvent.setup>) => {
    renderPage();
    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );
  };

  it('F-01: 수정 저장 시 tool_ids 를 카탈로그 표기로 전송한다', async () => {
    let captured: Record<string, unknown> | null = null;
    editHandlers((b) => { captured = b; }, {
      tool_ids: ['tavily_search'],
      workers: [
        {
          tool_id: 'tavily_search',
          worker_id: 'tavily_search_worker',
          description: '웹 검색',
          sort_order: 0,
          tool_config: null,
          worker_type: 'tool',
          ref_agent_id: null,
          ref_agent_name: null,
        },
      ],
    });
    const user = userEvent.setup();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.tool_ids).toEqual(['internal:tavily_search']);
  });

  it('F-01b: 도구가 없으면 빈 배열을 보낸다 (전부 해제 — undefined 와 구분)', async () => {
    let captured: Record<string, unknown> | null = null;
    editHandlers((b) => { captured = b; });
    const user = userEvent.setup();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.tool_ids).toEqual([]);
  });

  it('F-03: 빌트인은 tool_ids 에서 제외된다 (서버 재주입 + 도구 상한 제외)', async () => {
    let captured: Record<string, unknown> | null = null;
    editHandlers((b) => { captured = b; }, {
      tool_ids: ['tavily_search', 'wiki_read'],
      workers: [
        {
          tool_id: 'tavily_search',
          worker_id: 'tavily_search_worker',
          description: '웹 검색',
          sort_order: 0,
          tool_config: null,
          worker_type: 'tool',
          ref_agent_id: null,
          ref_agent_name: null,
        },
        {
          tool_id: 'wiki_read',
          worker_id: 'wiki_read_worker',
          description: '위키',
          sort_order: 1,
          tool_config: null,
          worker_type: 'tool',
          ref_agent_id: null,
          ref_agent_name: null,
        },
      ],
    });
    const user = userEvent.setup();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.tool_ids).toEqual(['internal:tavily_search']);
  });

  it('F-04: 응답이 clamp 를 알리면 안내 문구에 포함한다', async () => {
    editHandlers(() => {}, {}, {
      visibility: 'private',
      visibility_clamped: true,
      max_visibility: 'private',
    });
    const user = userEvent.setup();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(
      await screen.findByText(/공개 범위가 'private'로 조정되었습니다/),
    ).toBeInTheDocument();
  });

  it('F-04b: clamp 가 없으면 기본 성공 문구만 노출한다', async () => {
    editHandlers(() => {});
    const user = userEvent.setup();
    await openEdit(user);

    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(
      await screen.findByText('에이전트가 성공적으로 수정되었습니다.'),
    ).toBeInTheDocument();
  });
});

describe('AgentBuilderPage 도구 설정 전송 (agent-update-tool-editing F-02)', () => {
  const RAG_CATALOG = {
    tools: [
      ...CATALOG.tools,
      {
        tool_id: 'internal:internal_document_search',
        source: 'internal',
        name: '내부 문서 검색',
        description: 'RAG 검색',
        mcp_server_id: null,
        mcp_server_name: null,
        requires_env: [],
        is_builtin: false,
      },
    ],
  };

  it('RAG 설정을 카탈로그 표기 키로 tool_configs 에 실어 보낸다', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(RAG_CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () =>
        HttpResponse.json({
          ...EDIT_DETAIL,
          tool_ids: ['internal_document_search'],
          workers: [
            {
              tool_id: 'internal_document_search',
              worker_id: 'internal_document_search_worker',
              description: 'RAG',
              sort_order: 0,
              tool_config: { top_k: 9, search_mode: 'hybrid' },
              worker_type: 'tool',
              ref_agent_id: null,
              ref_agent_name: null,
            },
          ],
        }),
      ),
      http.patch('*/api/v1/agents/a-9', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          agent_id: 'a-9',
          name: '수정용 봇',
          system_prompt: '기존 지침',
          updated_at: '2026-09-06T00:00:00Z',
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.tool_ids).toEqual(['internal:internal_document_search']);
    const configs = captured!.tool_configs as Record<string, { top_k: number }>;
    expect(configs['internal:internal_document_search'].top_k).toBe(9);
  });
});


// ── agent-opener Design §8.3 #5·#6 — 오프너 탭 저장 페이로드·프라임 ─────────

describe('AgentBuilderPage 오프너 탭 (agent-opener)', () => {
  it('create 저장 → 빈 행은 제거되고 openers에 1건만 실린다', async () => {
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
          openers: ['첫 질문'],
          created_at: '2026-08-01T00:00:00Z',
          has_sub_agents: false,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    // 오프너 탭이 활성화되어 진입 가능하다 (placeholder 아님)
    await user.click(screen.getByRole('button', { name: '오프너' }));
    expect(screen.getByText('0/12')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '추가' }));
    await user.type(screen.getByRole('textbox', { name: '오프너 1' }), '첫 질문');
    await user.click(screen.getByRole('button', { name: '추가' }));
    expect(screen.getByText('2/12')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.openers).toEqual(['첫 질문']);
  });

  it('edit 프라임(2건) → 1건 삭제 후 저장 → update openers에 전체 교체 기준선이 실린다', async () => {
    useBuilderHandlers();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () =>
        HttpResponse.json({ ...EDIT_DETAIL, openers: ['질문 A', '질문 B'] }),
      ),
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

    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '오프너' }));
    expect(screen.getByRole('textbox', { name: '오프너 1' })).toHaveValue('질문 A');
    expect(screen.getByRole('textbox', { name: '오프너 2' })).toHaveValue('질문 B');

    await user.click(screen.getByRole('button', { name: '오프너 1 삭제' }));
    expect(screen.getByText('1/12')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.openers).toEqual(['질문 B']);
  });

  // Check G3 — Design §8.3 #7: 서버 422(중복) → 실패 메시지 표시, 입력 행 유지
  it('edit 저장 시 서버 422 → 메시지가 표시되고 오프너 행은 유지된다', async () => {
    useBuilderHandlers();
    server.use(
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', () =>
        HttpResponse.json({ ...EDIT_DETAIL, openers: ['질문 A', '질문 A'] }),
      ),
      http.patch('*/api/v1/agents/a-9', () =>
        HttpResponse.json(
          { detail: '오프너 2번째 항목이 앞의 항목과 중복됩니다' },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: '수정용 봇 수정' }));
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );
    await user.click(screen.getByRole('button', { name: '오프너' }));
    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(
      await screen.findByText(/오프너 2번째 항목이 앞의 항목과 중복됩니다/),
    ).toBeInTheDocument();
    // 행은 그대로 — 사용자가 고쳐서 다시 저장할 수 있어야 한다
    expect(screen.getByRole('textbox', { name: '오프너 1' })).toHaveValue('질문 A');
    expect(screen.getByRole('textbox', { name: '오프너 2' })).toHaveValue('질문 A');
  });
});

// ── image-generation-tool Design §5.1 / §8.3 L2 #7·#8·#10 ─────────────────

const IMAGE_CATALOG = {
  tools: [
    ...CATALOG.tools,
    {
      tool_id: 'internal:image_generate',
      source: 'internal',
      name: '이미지 생성',
      description: '이미지 생성 모델로 이미지를 만든다',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: [],
      is_builtin: false,
    },
  ],
};

const IMAGE_LLM_MODELS = [
  { ...LLM_MODELS[0], model_kind: 'chat', price_per_image_usd: null },
  {
    id: 'img-1',
    provider: 'openai',
    model_name: 'gpt-image-1',
    display_name: 'GPT Image 1',
    description: null,
    max_tokens: null,
    is_active: true,
    is_default: false,
    base_url: null,
    model_kind: 'image',
    price_per_image_usd: '0.0400',
    input_price_per_1k_usd: null,
    output_price_per_1k_usd: null,
    pricing_updated_at: null,
  },
];

const CREATED_IMAGE_AGENT = {
  agent_id: 'a-1',
  name: '테스트 에이전트',
  system_prompt: '테스트 지침',
  tool_ids: ['image_generate'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  visibility: 'private',
  temperature: 0.7,
  max_iterations: 25,
  created_at: '2026-08-01T00:00:00Z',
  has_sub_agents: false,
};

describe('AgentBuilderPage 이미지 생성 도구 (image-generation-tool)', () => {
  const useImageHandlers = () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(IMAGE_CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json({ models: IMAGE_LLM_MODELS })),
      http.post('*/api/v1/agents', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(CREATED_IMAGE_AGENT);
      }),
    );
    return () => captured;
  };

  it('#7 create: 도구 추가 → 모델·크기 선택 → 저장 시 image_generation 전송', async () => {
    const getCaptured = useImageHandlers();
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    await user.click(screen.getByRole('button', { name: '도구' }));
    await user.click(await screen.findByRole('button', { name: /이미지 생성/ }));
    expect(await screen.findByText('이미지 생성 — 모델·크기·품질')).toBeInTheDocument();

    await user.selectOptions(await screen.findByLabelText('이미지 모델'), 'img-1');
    await user.click(screen.getByLabelText(/1536×1024/));
    await user.click(screen.getByRole('button', { name: '완료' }));
    expect(screen.getByText(/GPT Image 1 · 1536×1024/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(getCaptured()).not.toBeNull());
    expect(getCaptured()!.image_generation).toEqual({
      llm_model_id: 'img-1',
      default_size: '1536x1024',
      quality: 'standard',
    });
    expect(getCaptured()!.tool_ids).toContain('internal:image_generate');
  });

  it('#8 도구 제거 시 설정이 삭제되어 image_generation 을 전송하지 않는다', async () => {
    const getCaptured = useImageHandlers();
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    await user.click(screen.getByRole('button', { name: '도구' }));
    await user.click(await screen.findByRole('button', { name: /이미지 생성/ }));
    await user.selectOptions(await screen.findByLabelText('이미지 모델'), 'img-1');
    await user.click(screen.getByRole('button', { name: '완료' }));
    await user.click(screen.getByRole('button', { name: '이미지 생성 제거' }));

    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(getCaptured()).not.toBeNull());
    expect(getCaptured()!.image_generation).toBeUndefined();
    expect(getCaptured()!.tool_ids ?? []).not.toContain('internal:image_generate');
  });

  it('#7b 도구는 부착했지만 모델 미선택이면 저장을 차단하고 안내한다', async () => {
    const getCaptured = useImageHandlers();
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    await user.click(screen.getByRole('button', { name: '도구' }));
    await user.click(await screen.findByRole('button', { name: /이미지 생성/ }));
    await screen.findByLabelText('이미지 모델');
    await user.click(screen.getByRole('button', { name: '완료' }));

    await user.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText(/이미지 생성 모델을 선택/)).toBeInTheDocument();
    expect(getCaptured()).toBeNull();
  });

  it('#10 에이전트 모델 설정 드롭다운에 이미지 모델이 노출되지 않는다', async () => {
    useImageHandlers();
    const user = userEvent.setup();
    renderPage();
    await enterCreateView(user);

    await user.click(screen.getByRole('button', { name: '모델 설정' }));
    // agent-kb-quick-setup: 도구함 지식 문서 블록에도 combobox 가 있어 이름으로 고른다
    await user.click(await screen.findByRole('combobox', { name: '모델' }));
    expect(await screen.findByRole('option', { name: /GPT-4o/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /GPT Image 1/ })).not.toBeInTheDocument();
  });
});

// ── agent-edit-entry Design §8.3 ─────────────────────────────

describe('AgentBuilderPage 편집 진입 (agent-edit-entry)', () => {
  const LocationDisplay = () => {
    const location = useLocation();
    return <div data-testid="location">{location.pathname + location.search}</div>;
  };

  /** 지정 경로로 진입. 빌더 밖 경로(/chatpage 등)로 이동하면 빌더는 언마운트된다 */
  const renderAt = (entry: string) =>
    render(
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/agent-builder" element={<AgentBuilderPage />} />
          <Route path="*" element={null} />
        </Routes>
        <LocationDisplay />
      </MemoryRouter>,
      { wrapper: createWrapper() },
    );

  const editEntryHandlers = (
    detail: () => Response = () => HttpResponse.json(EDIT_DETAIL),
  ) =>
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', detail),
      http.patch('*/api/v1/agents/a-9', () =>
        HttpResponse.json({
          agent_id: 'a-9',
          name: '수정용 봇',
          system_prompt: '기존 지침',
          updated_at: '2026-11-05T00:00:00Z',
        }),
      ),
    );

  const location = () => screen.getByTestId('location').textContent;
  const DENIED = '이 에이전트를 수정할 권한이 없거나 찾을 수 없습니다.';

  afterEach(() => useAgentDraftStore.getState().clearPendingIntent());

  it('C4: ?edit 로 들어오면 목록을 거치지 않고 해당 에이전트 편집 스튜디오를 연다', async () => {
    editEntryHandlers();
    renderAt('/agent-builder?edit=a-9');

    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );
    expect(screen.queryByRole('button', { name: '새 에이전트' })).not.toBeInTheDocument();
  });

  it('C5: 상세가 오기 전에는 로딩 문구를 보여준다', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
      http.get('*/api/v1/agents', () =>
        HttpResponse.json({ agents: [EDIT_SUMMARY], total: 1, page: 1, size: 20 }),
      ),
      http.get('*/api/v1/agents/a-9', async () => {
        await gate;
        return HttpResponse.json(EDIT_DETAIL);
      }),
    );
    renderAt('/agent-builder?edit=a-9');

    expect(await screen.findByText('에이전트를 불러오는 중…')).toBeInTheDocument();
    expect(screen.queryByLabelText('에이전트 이름')).not.toBeInTheDocument();
    release();
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );
  });

  it('C6: 상세의 can_edit=false 면 목록 + 권한 없음 배너, 스튜디오는 열지 않는다', async () => {
    editEntryHandlers(() => HttpResponse.json({ ...EDIT_DETAIL, can_edit: false }));
    renderAt('/agent-builder?edit=a-9&returnTo=%2Fchatpage');

    // 카탈로그·모델 settled → 소비 → 상세 조회 → 판정 순서라 전체 실행 부하에서 1초를 넘길 수 있다
    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent(DENIED);
    expect(screen.getByRole('button', { name: '새 에이전트' })).toBeInTheDocument();
    expect(screen.queryByLabelText('에이전트 이름')).not.toBeInTheDocument();
    // 배너 렌더와 URL replace 커밋은 같은 틱이 아닐 수 있다
    await waitFor(() => expect(location()).toBe('/agent-builder'));
  });

  it('C7: 상세 404 도 권한 없음 배너로 처리한다', async () => {
    editEntryHandlers(() => HttpResponse.json({ detail: 'not found' }, { status: 404 }));
    renderAt('/agent-builder?edit=a-9');

    expect(await screen.findByRole('alert', {}, { timeout: 3000 })).toHaveTextContent(DENIED);
    expect(screen.queryByLabelText('에이전트 이름')).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '안내 닫기' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('C8: returnTo 가 있으면 [뒤로(취소)] 시 그 경로로 돌아간다', async () => {
    editEntryHandlers();
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9&returnTo=%2Fchatpage');
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(location()).toBe('/chatpage');
  });

  it('C9: returnTo 가 있으면 저장 성공 [확인] 시 그 경로로 돌아간다', async () => {
    editEntryHandlers();
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9&returnTo=%2Fagents%2Fa-9%2Fworkspace');
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '저장' }));
    await screen.findByText('에이전트가 성공적으로 수정되었습니다.');
    await user.click(screen.getByRole('button', { name: '확인' }));

    expect(location()).toBe('/agents/a-9/workspace');
  });

  it('C10: returnTo 가 없으면 [취소] 시 목록으로 가고 URL 파라미터를 지운다', async () => {
    editEntryHandlers();
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9');
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(await screen.findByRole('button', { name: '새 에이전트' })).toBeInTheDocument();
    expect(location()).toBe('/agent-builder');
  });

  it('C11: 외부 URL returnTo 는 무시하고 목록으로 간다', async () => {
    editEntryHandlers();
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9&returnTo=https%3A%2F%2Fevil.com');
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(await screen.findByRole('button', { name: '새 에이전트' })).toBeInTheDocument();
    expect(location()).toBe('/agent-builder');
  });

  it('C12: 위저드 intent 가 있으면 ?edit 보다 우선한다 (create 뷰)', async () => {
    editEntryHandlers();
    useAgentDraftStore.getState().setPendingIntent({
      kind: 'wizard',
      result: {
        systemPrompt: '위저드 지침',
        promptEdited: false,
        toolIds: [],
        suggestedName: '위저드 봇',
        sessionId: 'ps1',
        versionId: 'pv1',
      },
    });
    renderAt('/agent-builder?edit=a-9');

    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('위저드 봇'),
    );
    // intent 가 이기면 남은 ?edit 는 지운다 (새로고침 시 편집으로 바뀌지 않게)
    await waitFor(() => expect(location()).toBe('/agent-builder'));
  });

  // ── Check 갭 보완 ──

  it('C14: 편집 중 상세 재조회가 실패해도 권한 없음으로 튕기지 않는다', async () => {
    let calls = 0;
    editEntryHandlers(() => {
      calls += 1;
      return calls === 1
        ? HttpResponse.json(EDIT_DETAIL)
        : HttpResponse.json({ detail: 'boom' }, { status: 500 });
    });
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9&returnTo=%2Fchatpage');
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );

    // 배경 재조회(앱에서는 저장 후 무효화·포커스 복귀) 실패를 포커스 복귀로 재현한다.
    // 저장 무효화는 전역 queryClient 대상이라 테스트 래퍼의 클라이언트에는 닿지 않는다.
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    await new Promise((r) => setTimeout(r, 200));
    act(() => focusManager.setFocused(undefined));

    // 스튜디오 내부 패널(승인 게이트 등)의 자체 alert 는 무관 — 권한 없음 배너만 확인
    expect(screen.queryByText(DENIED)).not.toBeInTheDocument();
    expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇');
    await user.click(screen.getByRole('button', { name: '뒤로' }));
    expect(location()).toBe('/chatpage');
  });

  it('C15: 카탈로그 로딩 중 ?edit 진입은 목록 대신 로딩 문구를 보여준다', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    editEntryHandlers();
    server.use(
      http.get('*/api/v1/tool-catalog', async () => {
        await gate;
        return HttpResponse.json(CATALOG);
      }),
    );
    renderAt('/agent-builder?edit=a-9');

    expect(await screen.findByText('에이전트를 불러오는 중…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '새 에이전트' })).not.toBeInTheDocument();
    release();
    await waitFor(() =>
      expect(screen.getByLabelText('에이전트 이름')).toHaveValue('수정용 봇'),
    );
  });

  it('C16: 로딩 화면의 [뒤로]는 returnTo 로 돌아간다', async () => {
    const gate = new Promise<void>(() => {});
    editEntryHandlers(() => HttpResponse.json(EDIT_DETAIL));
    server.use(
      http.get('*/api/v1/agents/a-9', async () => {
        await gate;
        return HttpResponse.json(EDIT_DETAIL);
      }),
    );
    const user = userEvent.setup();
    renderAt('/agent-builder?edit=a-9&returnTo=%2Fchatpage');

    await screen.findByText('에이전트를 불러오는 중…');
    await user.click(screen.getByRole('button', { name: '뒤로' }));

    expect(location()).toBe('/chatpage');
  });
});
