import { render, screen, within } from '@testing-library/react';
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

/** 목록 → "새 에이전트" 클릭으로 Studio 에디터 진입 */
const enterStudio = async () => {
  renderWithProviders(<AgentBuilderPage />);
  await userEvent.click(screen.getByRole('button', { name: /새 에이전트/ }));
};

/** 도구함 "도구" 버튼 클릭으로 도구 추가 모달 열기 */
const openToolModal = async () => {
  await userEvent.click(screen.getByRole('button', { name: '도구' }));
};

describe('AgentBuilderPage — Studio 도구 추가 모달', () => {
  it('도구 모달 로딩 중 스켈레톤 UI 를 표시한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, async () => {
        await new Promise((r) => setTimeout(r, 5000));
        return HttpResponse.json({ tools: [] });
      }),
    );

    await enterStudio();
    await openToolModal();

    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('도구 모달에서 서버 도구 목록을 표시한다', async () => {
    await enterStudio();
    await openToolModal();

    expect(await screen.findByText('Excel 파일 생성')).toBeInTheDocument();
    expect(screen.getByText('search')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
  });

  it('도구 클릭 시 선택되고, 재클릭 시 해제된다', async () => {
    await enterStudio();
    await openToolModal();

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

    await enterStudio();

    await userEvent.type(screen.getByLabelText('에이전트 이름'), '엑셀 도우미');

    await openToolModal();
    const excelTool = (await screen.findByText('Excel 파일 생성')).closest('button')!;
    await userEvent.click(excelTool);
    await userEvent.click(screen.getByRole('button', { name: '완료' }));

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.tool_ids).toEqual(['internal:excel_export']);
  });

  it('생성 모드에서 스킬을 토글하면 skill_ids 로 서버에 전송된다', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            agent_id: 'new-agent-skill', name: capturedBody.name, system_prompt: '',
            tool_ids: [], workers: [], flow_hint: '', llm_model_id: 'm-1',
            visibility: 'private', visibility_clamped: false, max_visibility: null,
            department_id: null, temperature: 0.7, created_at: '2026-05-31T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    await enterStudio();
    await userEvent.type(screen.getByLabelText('에이전트 이름'), '스킬 에이전트');

    // "스킬" 버튼은 좌측 추가버튼 + 우측 탭 2개 → 마지막(우측 탭) 클릭
    const skillButtons = screen.getAllByRole('button', { name: '스킬' });
    await userEvent.click(skillButtons[skillButtons.length - 1]);
    const toggle = await screen.findByRole('switch', { name: '환율 계산기 토글' });
    await userEvent.click(toggle);

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.skill_ids).toEqual(['skill-1']);
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

    await enterStudio();
    await userEvent.type(screen.getByLabelText('에이전트 이름'), 'AI 자동 에이전트');

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.tool_ids).toBeUndefined();
  });

  // fix-agent-composer FR-08: 생성 모드 MCP 차단 해제 + 저장 시 mcp_* 전송
  it('생성 모드에서도 MCP 도구를 선택하고 저장 시 tool_ids로 전송한다', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            agent_id: 'new-agent-mcp', name: capturedBody.name, system_prompt: '',
            tool_ids: (capturedBody.tool_ids as string[]) ?? [], workers: [],
            flow_hint: '', llm_model_id: 'm-1', visibility: 'private',
            visibility_clamped: false, max_visibility: null, department_id: null,
            temperature: 0.7, created_at: '2026-07-04T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    await enterStudio();
    await openToolModal();

    const mcpTool = (await screen.findByText('search')).closest('button')!;
    expect(mcpTool).not.toBeDisabled();
    await userEvent.click(mcpTool);
    await userEvent.click(screen.getByRole('button', { name: '완료' }));

    await userEvent.type(screen.getByLabelText('에이전트 이름'), 'MCP 에이전트');
    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });
    expect(capturedBody!.tool_ids).toEqual(['mcp:srv1:search']);
  });

  it('도구 모달 에러 상태에서 다시 시도 버튼을 표시한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 }),
      ),
    );

    await enterStudio();
    await openToolModal();

    expect(await screen.findByText('도구 목록을 불러올 수 없습니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /다시 시도/ })).toBeInTheDocument();
  });
});

describe('AgentBuilderPage — Fix 에이전트 탭 (fix-agent-composer)', () => {
  it('F11: Fix 에이전트 탭 클릭 시 FixAgentPanel이 렌더된다', async () => {
    await enterStudio();

    const fixTab = screen.getByRole('button', { name: 'Fix 에이전트' });
    expect(fixTab).not.toBeDisabled();
    await userEvent.click(fixTab);

    expect(screen.getByText('새 에이전트 수정')).toBeInTheDocument();
    expect(screen.getByText('자연어로 에이전트를 수정하세요')).toBeInTheDocument();
    expect(screen.getByLabelText('Fix 에이전트 입력')).toBeInTheDocument();
  });

  it('F9: 초안 [적용하기] 클릭 시 좌측 폼(이름/지침/온도)에 반영된다', async () => {
    await enterStudio();
    await userEvent.click(screen.getByRole('button', { name: 'Fix 에이전트' }));

    await userEvent.type(
      screen.getByLabelText('Fix 에이전트 입력'),
      '재무 에이전트 만들어줘{enter}',
    );
    await userEvent.click(await screen.findByRole('button', { name: '적용하기' }));

    // 기본 compose 핸들러 응답 (handlers.ts) 기준
    expect(screen.getByLabelText('에이전트 이름')).toHaveValue('재무 리포터');
    expect(screen.getByLabelText('지침')).toHaveValue(
      '당신은 재무 데이터 수집·보고 에이전트입니다.',
    );
    expect(screen.getByText('✓ 적용됨')).toBeInTheDocument();
  });

  // compose-tool-instructions FR-08: 저장 형식 tool_ids → 카탈로그 형식 변환 후 폼 반영
  it('초안 [적용하기] 시 도구가 도구함에 체크 표시된다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
        HttpResponse.json({
          coverage: 'full',
          name_suggestion: '엑셀 검색 도우미',
          system_prompt: '당신은 엑셀 검색 에이전트입니다.',
          tool_ids: ['excel_export', 'mcp_srv1'],
          workers: [],
          flow_hint: '',
          llm_model_id: 'model-default',
          temperature: 0.7,
          missing_capabilities: [],
          notes: '',
        }),
      ),
    );

    await enterStudio();
    // 도구 카탈로그 로딩 보장 (매핑에 필요)
    await openToolModal();
    await screen.findByText('Excel 파일 생성');
    await userEvent.click(screen.getByRole('button', { name: '완료' }));

    await userEvent.click(screen.getByRole('button', { name: 'Fix 에이전트' }));
    await userEvent.type(
      screen.getByLabelText('Fix 에이전트 입력'),
      '엑셀 검색 에이전트 만들어줘{enter}',
    );
    await userEvent.click(await screen.findByRole('button', { name: '적용하기' }));

    await openToolModal();
    const dialog = await screen.findByRole('dialog');
    const excelTool = within(dialog).getByText('Excel 파일 생성').closest('button')!;
    const mcpTool = within(dialog).getByText('search').closest('button')!;
    expect(excelTool.className).toContain('border-violet');
    expect(mcpTool.className).toContain('border-violet');
  });

  // compose-tool-instructions: RAG 도구 포함 초안 적용 시 toolConfigs 부수효과 회귀
  it('RAG 도구 포함 초안 적용 시 tool_configs가 세팅되어 저장에 포함된다', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
        HttpResponse.json({
          tools: [
            {
              tool_id: 'internal:internal_document_search',
              source: 'internal',
              name: '내부 문서 검색',
              description: '사내 문서 하이브리드 검색',
              mcp_server_id: null,
              mcp_server_name: null,
              requires_env: [],
            },
          ],
        }),
      ),
      http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
        HttpResponse.json({
          coverage: 'full',
          name_suggestion: '문서 도우미',
          system_prompt: '당신은 문서 검색 에이전트입니다.',
          tool_ids: ['internal_document_search'],
          workers: [],
          flow_hint: '',
          llm_model_id: 'model-default',
          temperature: 0.7,
          missing_capabilities: [],
          notes: '',
        }),
      ),
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            agent_id: 'new-agent-2',
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
            created_at: '2026-07-05T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    await enterStudio();
    // 도구 카탈로그 로딩 보장 (매핑에 필요)
    await openToolModal();
    await screen.findByText('내부 문서 검색');
    await userEvent.click(screen.getByRole('button', { name: '완료' }));

    await userEvent.click(screen.getByRole('button', { name: 'Fix 에이전트' }));
    await userEvent.type(
      screen.getByLabelText('Fix 에이전트 입력'),
      '문서 검색 에이전트 만들어줘{enter}',
    );
    await userEvent.click(await screen.findByRole('button', { name: '적용하기' }));

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));
    await vi.waitFor(() => {
      expect(capturedBody).not.toBeNull();
    });

    expect(capturedBody!.tool_ids).toEqual(['internal:internal_document_search']);
    // RAG_TOOL_ID 부수효과: DEFAULT_RAG_CONFIG가 toolConfigs에 세팅되어 전송
    expect(capturedBody!.tool_configs).toHaveProperty(
      'internal:internal_document_search',
    );
  });
});

describe('AgentBuilderPage — 스케줄 staged 일괄 등록 (agent-schedule)', () => {
  const mockCreateAgent = (agentId: string) =>
    http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        {
          agent_id: agentId, name: body.name, system_prompt: '',
          tool_ids: [], workers: [], flow_hint: '', llm_model_id: 'm-1',
          visibility: 'private', visibility_clamped: false, max_visibility: null,
          department_id: null, temperature: 0.7, created_at: '2026-07-03T00:00:00Z',
        },
        { status: 201 },
      );
    });

  /** 스케줄 탭에서 staged 스케줄 1건 추가 (시 드롭다운 값 지정) */
  const addStagedSchedule = async (hour: string, message: string) => {
    await userEvent.click(screen.getByRole('button', { name: /스케줄 추가/ }));
    await userEvent.selectOptions(screen.getByLabelText('시'), hour);
    await userEvent.type(screen.getByLabelText('실행 메시지'), message);
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
  };

  it('생성 성공 시 staged 스케줄 2건이 순차 POST된다', async () => {
    const captured: Array<{ agentId: string; body: Record<string, unknown> }> = [];
    server.use(
      mockCreateAgent('new-agent-sch'),
      http.post('*/api/v1/agents/:agentId/schedules', async ({ params, request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        captured.push({ agentId: params.agentId as string, body });
        return HttpResponse.json(
          { id: `sch-${captured.length}`, agent_id: params.agentId, ...body },
          { status: 201 },
        );
      }),
    );

    await enterStudio();
    await userEvent.type(screen.getByLabelText('에이전트 이름'), '스케줄 에이전트');

    await userEvent.click(screen.getByRole('button', { name: '스케줄' }));
    await addStagedSchedule('9', '아침 뉴스 요약');
    await addStagedSchedule('18', '저녁 리포트');
    expect(screen.getAllByText('등록 대기')).toHaveLength(2);

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    expect(
      await screen.findByText(/스케줄 2건이 함께 등록되었습니다/),
    ).toBeInTheDocument();
    expect(captured).toHaveLength(2);
    expect(captured.every((c) => c.agentId === 'new-agent-sch')).toBe(true);
    expect(captured[0].body).toMatchObject({
      name: '매일 09:00 실행',
      spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
      instruction: '아침 뉴스 요약',
      timezone: 'Asia/Seoul',
      enabled: true,
    });
    expect(captured[1].body).toMatchObject({ name: '매일 18:00 실행' });
  });

  it('일부 스케줄 등록 실패 시 결과 메시지에 실패 건수를 표시한다', async () => {
    let calls = 0;
    server.use(
      mockCreateAgent('new-agent-sch-fail'),
      http.post('*/api/v1/agents/:agentId/schedules', async ({ params, request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        calls += 1;
        if (calls === 2) {
          return HttpResponse.json(
            { detail: '연속 발화 간격이 10분 미만입니다.' },
            { status: 400 },
          );
        }
        return HttpResponse.json(
          { id: `sch-${calls}`, agent_id: params.agentId, ...body },
          { status: 201 },
        );
      }),
    );

    await enterStudio();
    await userEvent.type(screen.getByLabelText('에이전트 이름'), '부분 실패 에이전트');

    await userEvent.click(screen.getByRole('button', { name: '스케줄' }));
    await addStagedSchedule('9', '아침 뉴스 요약');
    await addStagedSchedule('18', '저녁 리포트');

    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    expect(
      await screen.findByText(/스케줄 2건 중 1건 등록에 실패했습니다/),
    ).toBeInTheDocument();
  });

  it('staged 스케줄이 없으면 스케줄 POST 없이 기본 메시지만 표시한다', async () => {
    let scheduleCalls = 0;
    server.use(
      mockCreateAgent('new-agent-nosch'),
      http.post('*/api/v1/agents/:agentId/schedules', () => {
        scheduleCalls += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    await enterStudio();
    await userEvent.type(screen.getByLabelText('에이전트 이름'), '무스케줄 에이전트');
    await userEvent.click(screen.getByRole('button', { name: /^저장$/ }));

    expect(
      await screen.findByText('에이전트가 성공적으로 등록되었습니다.'),
    ).toBeInTheDocument();
    expect(scheduleCalls).toBe(0);
  });
});

describe('AgentBuilderPage — Studio 레이아웃', () => {
  it('생성 모드에서 테스트 패널은 저장 후 사용 안내를 표시한다', async () => {
    await enterStudio();
    expect(
      await screen.findByText('저장 후 테스트할 수 있습니다'),
    ).toBeInTheDocument();
  });

  it('비활성 placeholder(서브에이전트/미들웨어)를 표시한다', async () => {
    await enterStudio();
    expect(screen.getByText('서브에이전트가 없습니다')).toBeInTheDocument();
    expect(screen.getByText('추가된 미들웨어가 없습니다')).toBeInTheDocument();
  });
});
