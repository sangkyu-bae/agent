// agent-create-wizard Design §8.4 — 위저드 L2 시나리오.
//
// 파이프라인은 SSE(POST + fetch-stream)라 MSW 가 ReadableStream 본문을 돌려준다.
// 각 시나리오는 "서버가 어떤 status 를 주면 화면이 어느 단계로 가는가"를 본다.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useAgentDraftStore } from '@/store/agentDraftStore';
import {
  MAX_ASSEMBLED_CHARS,
  PIPELINE_STAGE_STATUS,
} from '@/types/agentPipeline';
import type {
  AgentPipelineResponse,
  PipelineStage,
  PipelineStageStatus,
  PipelineStepOut,
} from '@/types/agentPipeline';
import AgentCreateEntryPage from './index';

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

// ── SSE 픽스처 ──────────────────────────────────────────────────────────────

const STAGES = ['intent', 'tools', 'prompt', 'create', 'bind'] as const;

const steps = (
  overrides: Partial<Record<PipelineStage, PipelineStageStatus>> = {},
  reasons: Partial<Record<PipelineStage, string>> = {},
): PipelineStepOut[] =>
  STAGES.map((stage) => ({
    stage,
    status: overrides[stage] ?? PIPELINE_STAGE_STATUS.SKIPPED,
    reason: reasons[stage] ?? null,
    elapsed_ms: 0,
  }));

const baseResult = (
  partial: Partial<AgentPipelineResponse>,
): AgentPipelineResponse => ({
  status: 'created',
  round: 0,
  steps: steps(),
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

/** stage_started/completed 몇 개 + pipeline_result 로 구성된 SSE 본문. */
const sseBody = (
  result: AgentPipelineResponse,
  reached: readonly string[] = ['intent'],
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
  parts.push(block('pipeline_result', result));
  return parts.join('');
};

const sseResponse = (body: string) =>
  new HttpResponse(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });

/** 호출 순서대로 다른 응답을 돌려주는 핸들러. 요청 본문을 기록한다. */
const stubStream = (
  bodies: string[],
): { requests: Record<string, unknown>[] } => {
  const requests: Record<string, unknown>[] = [];
  let call = 0;
  server.use(
    http.post(`*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`, async ({ request }) => {
      requests.push((await request.json()) as Record<string, unknown>);
      const body = bodies[Math.min(call, bodies.length - 1)];
      call += 1;
      return sseResponse(body);
    }),
  );
  return { requests };
};

const stubToolCatalog = () =>
  server.use(
    http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
      HttpResponse.json({
        tools: [
          {
            tool_id: 'internal:a',
            source: 'internal',
            name: '문서 검색',
            description: '사내 문서를 찾는다',
            mcp_server_id: null,
            mcp_server_name: null,
            requires_env: [],
            is_builtin: false,
          },
          {
            tool_id: 'internal:b',
            source: 'internal',
            name: '엑셀 내보내기',
            description: '표를 저장한다',
            mcp_server_id: null,
            mcp_server_name: null,
            requires_env: [],
            is_builtin: false,
          },
        ],
      }),
    ),
  );

const NEED_INPUT = baseResult({
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

const TOOLS_PROPOSED = baseResult({
  status: 'tools_proposed',
  round: 1,
  steps: steps({ intent: 'ok', tools: 'ok' }),
  recommended_tool_ids: ['internal:a', 'internal:b'],
  final_tool_ids: ['internal:a', 'internal:b'],
  suggested_name: '문서 Q&A 봇',
  intent: {
    label: 'agent_build',
    filled_slots: { purpose: '문서 Q&A' },
    missing_slots: [],
    degraded: false,
  },
});

const PROMPT_READY = baseResult({
  status: 'prompt_ready',
  round: 1,
  steps: steps({ intent: 'ok', tools: 'ok', prompt: 'ok' }),
  recommended_tool_ids: ['internal:a'],
  final_tool_ids: ['internal:a'],
  session_id: 'ps1',
  version_id: 'pv1',
  assembled_prompt: '당신은 사내 문서를 찾아 답하는 에이전트입니다.',
  suggested_name: '문서 Q&A 봇',
});

// ── 헬퍼 ────────────────────────────────────────────────────────────────────

const renderPage = () =>
  render(<AgentCreateEntryPage />, { wrapper: createWrapper() });

const submitDescription = async (text = '사내 문서를 찾아주는 에이전트') => {
  const user = userEvent.setup();
  await user.type(screen.getByRole('textbox'), text);
  await user.click(screen.getByRole('button', { name: /만들기 시작|전송|생성/ }));
  return user;
};

// ── ① 설명 입력 ────────────────────────────────────────────────────────────

describe('① 설명 입력', () => {
  it('전송 전에는 진행바를 보여주지 않는다', () => {
    // 전부 '대기중'인 5단계는 정보가 아니라 잡음이다.
    renderPage();
    expect(screen.queryByText('의도 파악')).not.toBeInTheDocument();
    expect(screen.queryByText(/스튜디오에서 \[저장\]/)).not.toBeInTheDocument();
  });

  it('전송하면 입력창 바로 아래에 5단계 진행바가 붙는다', async () => {
    stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    await submitDescription();

    for (const label of [
      '의도 파악',
      '도구 추천',
      '프롬프트 생성',
      '에이전트 생성',
      '프롬프트 연결',
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(/스튜디오에서 \[저장\]/)).toBeInTheDocument();
  });

  it('전송한 문장이 요청 버블로 트랜스크립트 맨 위에 남는다 (FR-05)', async () => {
    stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    await submitDescription();

    const bubble = await screen.findByText('사내 문서를 찾아주는 에이전트');
    expect(bubble).toBeInTheDocument();
    // 트랜스크립트(스크롤 영역) 안에 있다 — 하단 입력창이 아니라 버블이다.
    expect(
      bubble.closest('[data-testid="wizard-transcript"]'),
    ).not.toBeNull();
  });

  it('공백만 입력하면 호출하지 않는다', async () => {
    const { requests } = stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByRole('textbox'), '   ');
    const button = screen.getByRole('button', { name: /만들기 시작|전송|생성/ });
    if (!(button as HTMLButtonElement).disabled) await user.click(button);
    expect(requests).toHaveLength(0);
  });

  it('첫 호출은 stop_after=tools 로 보낸다', async () => {
    const { requests } = stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    await submitDescription();
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].stop_after).toBe('tools');
    expect(requests[0].user_request).toBe('사내 문서를 찾아주는 에이전트');
  });
});

// ── 채팅형 레이아웃 (wizard-chat-layout) ───────────────────────────────────

describe('채팅형 레이아웃 (wizard-chat-layout §5.4)', () => {
  it('헤더바가 없다 — 타이틀·[취소] 미노출 (FR-01/FR-11)', () => {
    renderPage();
    expect(
      screen.queryByRole('heading', { name: '에이전트 만들기' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '취소' }),
    ).not.toBeInTheDocument();
  });

  it('첫 화면은 히어로 + 액션 카드를 보여준다 (FR-02)', () => {
    renderPage();
    expect(
      screen.getByText('생성하려는 에이전트에 대해 알려주세요'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /에이전트 직접 만들기/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('에이전트 가져오기')).toBeInTheDocument();
  });

  it('첫 전송 시 chat 모드 전환 — 히어로·액션 카드가 사라지고 하단 입력창이 잠긴다 (FR-03/04/08)', async () => {
    stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    await submitDescription();

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    expect(
      screen.queryByText('생성하려는 에이전트에 대해 알려주세요'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /에이전트 직접 만들기/ }),
    ).not.toBeInTheDocument();
    // 하단 고정 입력창 — 재전송 창구가 아니다
    expect(screen.getByLabelText('에이전트 설명')).toBeDisabled();
  });

  it('질문 라운드가 누적된다 — 이전 라운드 카드가 잠긴 채 남는다 (FR-07)', async () => {
    const ROUND2 = baseResult({
      status: 'need_input',
      round: 2,
      steps: steps({ intent: 'ok' }),
      questions: [
        {
          slot_key: 'audience',
          question: '누가 사용하나요?',
          options: ['사내 직원', '고객'],
          allow_free_text: false,
        },
      ],
      intent: {
        label: null,
        filled_slots: { purpose: '문서 Q&A' },
        missing_slots: ['audience'],
        degraded: false,
      },
    });
    stubStream([sseBody(NEED_INPUT), sseBody(ROUND2)]);
    renderPage();
    const user = await submitDescription();

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    await user.click(screen.getByText('문서 Q&A'));
    await user.click(screen.getByRole('button', { name: '제출' }));

    await screen.findByText('누가 사용하나요?');
    // 라운드 1 카드가 여전히 DOM에 있고 잠김 배지를 단다
    expect(
      screen.getByText('이 에이전트의 핵심 용도는 무엇인가요?'),
    ).toBeInTheDocument();
    expect(screen.getAllByText('✓ 답변 완료').length).toBeGreaterThan(0);
  });

  it('첫 요청 실패 시 chat 모드 유지 — 요청 버블 + 실패 카드, 재시도는 같은 문장을 다시 보낸다', async () => {
    const requests: Record<string, unknown>[] = [];
    let call = 0;
    server.use(
      http.post(
        `*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`,
        async ({ request }) => {
          requests.push((await request.json()) as Record<string, unknown>);
          call += 1;
          if (call === 1) {
            return HttpResponse.json({ detail: 'boom' }, { status: 500 });
          }
          return sseResponse(sseBody(NEED_INPUT));
        },
      ),
    );
    renderPage();
    const user = await submitDescription();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '진행하지 못했습니다',
    );
    // centered 로 튕기지 않는다 — 요청 버블이 함께 보인다
    expect(
      screen.getByText('사내 문서를 찾아주는 에이전트'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('생성하려는 에이전트에 대해 알려주세요'),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '다시 시도' }));

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    expect(requests).toHaveLength(2);
    expect(requests[1].user_request).toBe('사내 문서를 찾아주는 에이전트');
  });
});

// ── ② 의도 수집 ────────────────────────────────────────────────────────────

describe('② 의도 수집', () => {
  it('need_input 이면 질문 카드를 띄운다', async () => {
    stubStream([sseBody(NEED_INPUT)]);
    renderPage();
    await submitDescription();
    expect(
      await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?'),
    ).toBeInTheDocument();
  });

  it('답변을 answers + round 로 에코백한다', async () => {
    const { requests } = stubStream([
      sseBody(NEED_INPUT),
      sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
    ]);
    stubToolCatalog();
    renderPage();
    const user = await submitDescription();

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    await user.click(screen.getByText('문서 Q&A'));
    await user.click(screen.getByRole('button', { name: '제출' }));

    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].stop_after).toBe('tools');
    expect(requests[1].round).toBe(1);
    expect(requests[1].answers).toEqual([
      { slot_key: 'purpose', value: '문서 Q&A' },
    ]);
  });

  it('건너뛰면 빈 answers 로 재호출한다', async () => {
    const { requests } = stubStream([
      sseBody(NEED_INPUT),
      sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
    ]);
    stubToolCatalog();
    renderPage();
    const user = await submitDescription();

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    await user.click(screen.getByRole('button', { name: '건너뛰고 계속하기' }));

    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1].answers).toEqual([]);
  });

  it('다음 응답이 와도 이전 라운드 카드는 잠긴 채 이력으로 남는다 (FR-07)', async () => {
    // F10 스테일 카드 가드는 잠금으로 대체됐다 — 답해도 전송되지 않는 카드가
    // "활성으로" 남으면 오표시지만, 잠긴 이력 카드는 대화 맥락이다.
    stubStream([
      sseBody(NEED_INPUT),
      sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
    ]);
    stubToolCatalog();
    renderPage();
    const user = await submitDescription();

    await screen.findByText('이 에이전트의 핵심 용도는 무엇인가요?');
    await user.click(screen.getByRole('button', { name: '건너뛰고 계속하기' }));

    await screen.findByText('이 도구들을 사용할까요?');
    expect(
      screen.getByText('이 에이전트의 핵심 용도는 무엇인가요?'),
    ).toBeInTheDocument();
    // 잠긴 카드에는 활성 진행 안내가 남지 않는다
    expect(
      screen.queryByRole('button', { name: '건너뛰고 계속하기' }),
    ).not.toBeInTheDocument();
  });
});

// ── ③ 도구 확인 ────────────────────────────────────────────────────────────

describe('③ 도구 확인', () => {
  const goToTools = async () => {
    stubToolCatalog();
    const stub = stubStream([sseBody(TOOLS_PROPOSED, ['intent', 'tools'])]);
    renderPage();
    const user = await submitDescription();
    await screen.findByText('이 도구들을 사용할까요?');
    return { user, stub };
  };

  it('추천 도구를 이름으로 보여주고 기본 선택한다', async () => {
    await goToTools();
    expect(await screen.findByText('문서 검색')).toBeInTheDocument();
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes.every((c) => (c as HTMLInputElement).checked)).toBe(true);
  });

  it('해제한 도구는 다음 요청 tool_ids 에서 빠진다', async () => {
    // D1 회귀 방지의 프론트 절반 — 서버는 tools_confirmed 로 셀렉터를 건너뛴다.
    const { user, stub } = await goToTools();
    await screen.findByText('엑셀 내보내기');

    const excel = screen
      .getByText('엑셀 내보내기')
      .closest('label')!
      .querySelector('input')!;
    await user.click(excel);
    await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));

    await waitFor(() => expect(stub.requests).toHaveLength(2));
    expect(stub.requests[1].tool_ids).toEqual(['internal:a']);
    expect(stub.requests[1].tools_confirmed).toBe(true);
    expect(stub.requests[1].stop_after).toBe('prompt');
  });

  it('확정된 의도를 에코백한다', async () => {
    const { user, stub } = await goToTools();
    await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));

    await waitFor(() => expect(stub.requests).toHaveLength(2));
    expect(stub.requests[1].intent).toEqual({
      label: 'agent_build',
      filled_slots: { purpose: '문서 Q&A' },
      degraded: false,
    });
  });

  it('unknown_tool_ids 가 있으면 안내를 띄운다', async () => {
    stubToolCatalog();
    stubStream([
      sseBody(
        { ...TOOLS_PROPOSED, unknown_tool_ids: ['internal:ghost'] },
        ['intent', 'tools'],
      ),
    ]);
    renderPage();
    await submitDescription();
    expect(
      await screen.findByText(/1개 도구는 카탈로그에 없거나/),
    ).toBeInTheDocument();
  });

  it('[처음부터]는 확인을 받은 뒤에만 초기화한다', async () => {
    // 무상태 위저드라 step②로 되돌아갈 수 없다 — 되돌리기가 아니라 전체
    // 초기화이므로 라벨과 확인 절차가 동작과 일치해야 한다.
    const { user } = await goToTools();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

    await user.click(screen.getByRole('button', { name: '처음부터' }));

    expect(confirm).toHaveBeenCalled();
    expect(screen.getByText('이 도구들을 사용할까요?')).toBeInTheDocument();

    confirm.mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: '처음부터' }));

    await waitFor(() =>
      expect(
        screen.queryByText('이 도구들을 사용할까요?'),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('textbox')).toHaveValue('');
    confirm.mockRestore();
  });

  it('추천이 0건이면 빈 상태를 안내한다', async () => {
    stubToolCatalog();
    stubStream([
      sseBody(
        {
          ...TOOLS_PROPOSED,
          recommended_tool_ids: [],
          final_tool_ids: [],
        },
        ['intent', 'tools'],
      ),
    ]);
    renderPage();
    await submitDescription();
    expect(
      await screen.findByText('추천할 도구를 찾지 못했어요.'),
    ).toBeInTheDocument();
  });
});

// ── ④ 프롬프트 검토 ────────────────────────────────────────────────────────

describe('④ 프롬프트 검토', () => {
  const goToPrompt = async (result = PROMPT_READY) => {
    stubToolCatalog();
    const stub = stubStream([
      sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
      sseBody(result, ['intent', 'tools', 'prompt']),
    ]);
    renderPage();
    const user = await submitDescription();
    await screen.findByText('이 도구들을 사용할까요?');
    await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));
    await screen.findByText('시스템 프롬프트를 확인해주세요');
    return { user, stub };
  };

  it('생성된 프롬프트를 편집 가능한 textarea 에 프리필한다', async () => {
    await goToPrompt();
    const textarea = screen.getByLabelText('시스템 프롬프트');
    expect(textarea).toHaveValue(
      '당신은 사내 문서를 찾아 답하는 에이전트입니다.',
    );
  });

  it('도구 카드가 잠긴 이력으로 함께 남는다 (FR-09)', async () => {
    await goToPrompt();

    expect(screen.getByText('이 도구들을 사용할까요?')).toBeInTheDocument();
    expect(screen.getByText(/선택 완료/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '이 도구로 진행' }),
    ).not.toBeInTheDocument();
    // [이전]으로 돌아가면 잠금이 풀린다
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '이전' }));
    expect(
      screen.getByRole('button', { name: '이 도구로 진행' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText('시스템 프롬프트'),
    ).not.toBeInTheDocument();
  });

  it('글자수 카운터를 보여준다', async () => {
    await goToPrompt();
    expect(
      screen.getByText(new RegExp(`/ ${MAX_ASSEMBLED_CHARS}`)),
    ).toBeInTheDocument();
  });

  it('상한을 넘기면 진행 버튼을 비활성화한다', async () => {
    const { user } = await goToPrompt();
    const textarea = screen.getByLabelText('시스템 프롬프트');
    await user.clear(textarea);
    // fireEvent 수준으로 붙여넣기 — 상한+1자를 타이핑하지 않는다.
    await user.click(textarea);
    await user.paste('가'.repeat(MAX_ASSEMBLED_CHARS + 1));

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '스튜디오로 보내기' }),
      ).toBeDisabled(),
    );
  });

  it('clamp 사유가 오면 절단 안내를 띄운다', async () => {
    await goToPrompt({
      ...PROMPT_READY,
      prompt_clamp_reason: '프롬프트 5000자 → 4000자 절단',
    });
    expect(await screen.findByText(/일부가 잘렸습니다/)).toBeInTheDocument();
  });

  it('degraded 면 규칙기반 안내를 띄운다', async () => {
    await goToPrompt({
      ...PROMPT_READY,
      degraded_stages: ['prompt'],
      steps: steps(
        { intent: 'ok', tools: 'ok', prompt: 'degraded' },
        { prompt: 'LLM 시간 초과' },
      ),
    });
    expect(
      await screen.findByText(/규칙기반 문안으로 만들었습니다/),
    ).toBeInTheDocument();
  });

  it('다시 생성은 같은 session_id 로 재호출한다', async () => {
    const { user, stub } = await goToPrompt();
    await user.click(screen.getByRole('button', { name: '다시 생성' }));
    await waitFor(() => expect(stub.requests).toHaveLength(3));
    expect(stub.requests[2].session_id).toBe('ps1');
  });
});

// ── 핸드오프 ────────────────────────────────────────────────────────────────

describe('스튜디오 핸드오프', () => {
  const goToPrompt = async () => {
    stubToolCatalog();
    stubStream([
      sseBody(TOOLS_PROPOSED, ['intent', 'tools']),
      sseBody(PROMPT_READY, ['intent', 'tools', 'prompt']),
    ]);
    renderPage();
    const user = await submitDescription();
    await screen.findByText('이 도구들을 사용할까요?');
    await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));
    await screen.findByText('시스템 프롬프트를 확인해주세요');
    return user;
  };

  it('위저드 결과를 pendingIntent 로 적재하고 스튜디오로 이동한다', async () => {
    const user = await goToPrompt();
    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));

    const intent = useAgentDraftStore.getState().pendingIntent;
    expect(intent?.kind).toBe('wizard');
    expect(navigateMock).toHaveBeenCalledWith('/agent-builder');
  });

  it('편집하지 않았으면 promptEdited=false 다', async () => {
    const user = await goToPrompt();
    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));

    const intent = useAgentDraftStore.getState().pendingIntent;
    expect(intent).toMatchObject({
      kind: 'wizard',
      result: {
        promptEdited: false,
        toolIds: ['internal:a', 'internal:b'],
        sessionId: 'ps1',
        versionId: 'pv1',
        suggestedName: '문서 Q&A 봇',
      },
    });
  });

  it('편집하면 promptEdited=true 로 넘긴다', async () => {
    // 편집본만 새 버전으로 저장하기 위한 신호다 (module-5 소비).
    const user = await goToPrompt();
    const textarea = screen.getByLabelText('시스템 프롬프트');
    await user.type(textarea, ' 추가 지침');
    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));

    const intent = useAgentDraftStore.getState().pendingIntent;
    expect(intent).toMatchObject({
      kind: 'wizard',
      result: { promptEdited: true },
    });
  });

  it('저장 API 를 호출하지 않는다 (무저장 계약)', async () => {
    const created: unknown[] = [];
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_BUILDER_CREATE}`, async () => {
        created.push(1);
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = await goToPrompt();
    await user.click(screen.getByRole('button', { name: '스튜디오로 보내기' }));
    expect(created).toHaveLength(0);
  });
});

// ── 실패·폴백 ──────────────────────────────────────────────────────────────

describe('실패 처리', () => {
  it('500 이면 실패 카드와 재시도 버튼을 띄운다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderPage();
    await submitDescription();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '진행하지 못했습니다',
    );
    expect(
      screen.getByRole('button', { name: '다시 시도' }),
    ).toBeInTheDocument();
  });

  it('404(킬스위치 off)면 위저드 대신 안내 화면을 보여준다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`, () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    renderPage();
    await submitDescription();
    expect(
      await screen.findByText('자동 생성이 지금은 사용할 수 없어요'),
    ).toBeInTheDocument();
  });

  it('킬스위치 안내에서 직접 만들기를 누르면 빈 스튜디오로 간다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_PIPELINE_STREAM}`, () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    renderPage();
    const user = await submitDescription();
    await screen.findByText('자동 생성이 지금은 사용할 수 없어요');
    await user.click(
      screen.getByRole('button', { name: '에이전트 직접 만들기' }),
    );

    expect(useAgentDraftStore.getState().pendingIntent).toEqual({
      kind: 'blank',
    });
    expect(navigateMock).toHaveBeenCalledWith('/agent-builder');
  });
});

// ── 진행바 반영 ────────────────────────────────────────────────────────────

describe('진행바', () => {
  it('완료된 단계를 완료로 칠한다', async () => {
    stubToolCatalog();
    stubStream([sseBody(TOOLS_PROPOSED, ['intent', 'tools'])]);
    renderPage();
    await submitDescription();
    await screen.findByText('이 도구들을 사용할까요?');

    // 도구 목록(ul)과 진행바(ol)가 함께 있으므로 단계 라벨로 행을 특정한다.
    const row = (label: string) => screen.getByText(label).closest('li')!;
    expect(within(row('의도 파악')).getByText('완료')).toBeInTheDocument();
    expect(within(row('도구 추천')).getByText('완료')).toBeInTheDocument();
    expect(within(row('에이전트 생성')).getByText('대기중')).toBeInTheDocument();
    expect(within(row('프롬프트 연결')).getByText('대기중')).toBeInTheDocument();
  });

  it('degraded 단계는 완료 + 사유 배지로 표시한다', async () => {
    stubToolCatalog();
    stubStream([
      sseBody(
        {
          ...TOOLS_PROPOSED,
          degraded_stages: ['tools'],
          steps: steps(
            { intent: 'ok', tools: 'degraded' },
            { tools: '추천 실패' },
          ),
        },
        ['intent', 'tools'],
      ),
    ]);
    renderPage();
    await submitDescription();
    await screen.findByText('이 도구들을 사용할까요?');
    expect(screen.getByText('추천 실패')).toBeInTheDocument();
  });
});
