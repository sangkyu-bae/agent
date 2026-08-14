// agent-create-entry Design §8.3 — 진입 화면 L2 시나리오.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, beforeEach, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import type { JsonBodyType } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useAgentDraftStore } from '@/store/agentDraftStore';
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

const DRAFT_BODY = {
  status: 'draft',
  coverage: 'full',
  name_suggestion: '규정 봇',
  system_prompt: '너는 사내 규정 안내 봇이다.',
  tool_ids: ['tavily_search'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  temperature: 0.5,
  missing_capabilities: [],
  notes: '',
};

const CLARIFY_BODY = {
  status: 'needs_clarification',
  questions: [
    {
      id: 'q1',
      question: '어떤 문서를 참조하나요?',
      options: ['지식베이스 A', '지식베이스 B'],
      allow_free_text: true,
    },
  ],
  plan_summary: '문서 QA 에이전트를 계획했습니다.',
  coverage: 'none',
  name_suggestion: '',
  system_prompt: '',
  tool_ids: [],
  workers: [],
  flow_hint: '',
  llm_model_id: '',
  temperature: 0.7,
  missing_capabilities: [],
  notes: '',
};

const renderPage = () =>
  render(<AgentCreateEntryPage />, { wrapper: createWrapper() });

/** compose 요청 본문을 수집하는 핸들러 */
const captureCompose = (responses: JsonBodyType[]) => {
  const bodies: Record<string, unknown>[] = [];
  let call = 0;
  server.use(
    http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>);
      const body = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return HttpResponse.json(body);
    }),
  );
  return bodies;
};

describe('AgentCreateEntryPage — 화면 구성 (FR-01/FR-09/FR-10)', () => {
  it('히어로·입력창·카드 2종을 렌더한다', () => {
    renderPage();

    expect(
      screen.getByText('생성하려는 에이전트에 대해 알려주세요'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('에이전트 설명')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '에이전트 직접 만들기' }),
    ).toBeInTheDocument();
    expect(screen.getByText('에이전트 가져오기')).toBeInTheDocument();
  });

  it('입력이 비어 있으면 전송 버튼이 비활성이다', () => {
    renderPage();

    expect(screen.getByLabelText('에이전트 설명 전송')).toBeDisabled();
  });

  it('공백만 입력해도 전송 버튼은 비활성이다', async () => {
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '   ');

    expect(screen.getByLabelText('에이전트 설명 전송')).toBeDisabled();
  });

  // FR-10: export가 없어 실사용성이 없으므로 이번 범위에서는 비활성 노출만
  it('가져오기 카드는 비활성이며 클릭해도 아무 일도 없다', async () => {
    renderPage();
    const importCard = screen.getByText('에이전트 가져오기').closest('button')!;

    expect(importCard).toBeDisabled();
    await userEvent.click(importCard);

    expect(navigateMock).not.toHaveBeenCalled();
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  // FR-09
  it('[직접 만들기]는 blank 의도를 적재하고 스튜디오로 보낸다', async () => {
    renderPage();

    await userEvent.click(
      screen.getByRole('button', { name: '에이전트 직접 만들기' }),
    );

    expect(useAgentDraftStore.getState().pendingIntent).toEqual({ kind: 'blank' });
    expect(navigateMock).toHaveBeenCalledWith('/agent-builder');
  });
});

describe('AgentCreateEntryPage — compose 성공 (FR-04/FR-07)', () => {
  it('전송하면 초안을 적재하고 스튜디오로 이동한다', async () => {
    captureCompose([DRAFT_BODY]);
    renderPage();

    await userEvent.type(
      screen.getByLabelText('에이전트 설명'),
      '사내 규정 문서를 찾아 답해주는 봇',
    );
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/agent-builder'),
    );
    expect(useAgentDraftStore.getState().pendingIntent).toEqual({
      kind: 'draft',
      draft: DRAFT_BODY,
    });
  });

  // Design §4.2 — 진입 화면은 편집 대상 폼이 없으므로 current_config를 보내지 않는다
  it('1차 요청은 current_config 없이 round=0으로 나간다', async () => {
    const bodies = captureCompose([DRAFT_BODY]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      user_request: '문서 QA 봇',
      name: null,
      current_config: null,
      history: null,
      clarification_round: 0,
    });
  });
});

describe('AgentCreateEntryPage — HITL (FR-05/FR-06)', () => {
  it('needs_clarification이면 질문 카드를 표시하고 이동하지 않는다', async () => {
    captureCompose([CLARIFY_BODY]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    expect(await screen.findByText('어떤 문서를 참조하나요?')).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  it('답변을 제출하면 원 요청 + 답변으로 round=1 재호출한다', async () => {
    const bodies = captureCompose([CLARIFY_BODY, DRAFT_BODY]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));
    await screen.findByText('어떤 문서를 참조하나요?');

    await userEvent.click(screen.getByRole('button', { name: '지식베이스 A' }));
    await userEvent.click(screen.getByRole('button', { name: '답변 제출' }));

    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      user_request: '문서 QA 봇',
      clarification_round: 1,
      clarification_answers: [
        {
          question_id: 'q1',
          question: '어떤 문서를 참조하나요?',
          answer: '지식베이스 A',
        },
      ],
    });
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/agent-builder'),
    );
  });

  // FR-06: 건너뛰기 = 전부 무응답으로 초안 강제
  it('[건너뛰고 초안 만들기]는 빈 answer로 재호출한다', async () => {
    const bodies = captureCompose([CLARIFY_BODY, DRAFT_BODY]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));
    await screen.findByText('어떤 문서를 참조하나요?');

    await userEvent.click(
      screen.getByRole('button', { name: '건너뛰고 초안 만들기' }),
    );

    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      clarification_round: 1,
      clarification_answers: [
        { question_id: 'q1', question: '어떤 문서를 참조하나요?', answer: '' },
      ],
    });
  });

  // Design §4.3 — 서버가 계속 되물어도 사용자가 빠져나갈 수 있어야 한다
  it('질문 라운드 상한을 넘으면 실패 카드로 강하한다', async () => {
    captureCompose([CLARIFY_BODY]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '뭔가 만들어줘');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    // round 1 → 2 → 3 까지 답변, 4번째 응답에서 상한 초과
    for (let i = 0; i < 3; i += 1) {
      await screen.findByRole('button', { name: '건너뛰고 초안 만들기' });
      await userEvent.click(
        screen.getByRole('button', { name: '건너뛰고 초안 만들기' }),
      );
    }

    expect(
      await screen.findByText(/요청을 더 구체적으로 적어 주세요/),
    ).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});

describe('AgentCreateEntryPage — 실패 처리 (FR-08)', () => {
  it('coverage=none이면 진입 화면에 머물며 미보유 능력을 안내한다', async () => {
    captureCompose([
      {
        ...DRAFT_BODY,
        coverage: 'none',
        system_prompt: '',
        tool_ids: [],
        notes: '요청을 충족할 도구를 찾지 못했습니다.',
        missing_capabilities: [
          {
            capability: '사내 ERP 조회',
            reason: '매칭되는 도구 없음',
            suggestion: 'ERP MCP 서버 등록 필요',
          },
        ],
      },
    ]);
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), 'ERP 조회 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    expect(
      await screen.findByText(/이 요청을 충족할 도구가 없습니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/사내 ERP 조회/)).toBeInTheDocument();
    expect(screen.getByText(/ERP MCP 서버 등록 필요/)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('compose 실패 시 실패 카드를 띄우고 입력은 보존한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));

    expect(
      await screen.findByText(/초안 생성에 실패했습니다/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('에이전트 설명')).toHaveValue('문서 QA 봇');
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('실패 카드의 [그래도 직접 만들기]는 빈 폼으로 보낸다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));
    await screen.findByText(/초안 생성에 실패했습니다/);

    await userEvent.click(
      screen.getByRole('button', { name: '그래도 직접 만들기' }),
    );

    expect(useAgentDraftStore.getState().pendingIntent).toEqual({ kind: 'blank' });
    expect(navigateMock).toHaveBeenCalledWith('/agent-builder');
  });

  it('[다시 설명하기]는 실패 카드만 닫는다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderPage();

    await userEvent.type(screen.getByLabelText('에이전트 설명'), '문서 QA 봇');
    await userEvent.click(screen.getByLabelText('에이전트 설명 전송'));
    await screen.findByText(/초안 생성에 실패했습니다/);

    await userEvent.click(screen.getByRole('button', { name: '다시 설명하기' }));

    await waitFor(() =>
      expect(screen.queryByText(/초안 생성에 실패했습니다/)).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText('에이전트 설명')).toHaveValue('문서 QA 봇');
  });
});

describe('AgentCreateEntryPage — 유령 초안 차단 (Design §2.4 G3)', () => {
  it('마운트 시 이전에 남은 의도를 비운다', () => {
    useAgentDraftStore
      .getState()
      .setPendingIntent({ kind: 'draft', draft: DRAFT_BODY as never });

    renderPage();

    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });
});
