import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { ComposeAgentRequest } from '@/types/agentComposer';
import type { LlmModel } from '@/types/llmModel';
import FixAgentPanel from './FixAgentPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const form: AgentBuilderFormData = {
  name: '재무 리포터',
  description: '재무 데이터 에이전트',
  model: 'gpt-4o',
  systemPrompt: '당신은 재무 에이전트입니다.',
  tools: ['excel_export'],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
  skills: [],
  schedules: [],
};

const models: LlmModel[] = [
  {
    id: 'model-default',
    provider: 'openai',
    model_name: 'gpt-4o',
    display_name: 'GPT-4o',
    description: null,
    max_tokens: null,
    is_active: true,
    is_default: true,
  },
];

const renderPanel = (overrides?: Partial<Parameters<typeof FixAgentPanel>[0]>) => {
  const onApplyDraft = vi.fn();
  render(
    <FixAgentPanel
      mode="create"
      form={form}
      models={models}
      onApplyDraft={onApplyDraft}
      {...overrides}
    />,
    { wrapper: createWrapper() },
  );
  return { onApplyDraft };
};

/** compose 요청 body를 캡처하는 핸들러 등록 */
const captureCompose = () => {
  const captured: ComposeAgentRequest[] = [];
  server.use(
    http.post('*/api/v1/agents/compose', async ({ request }) => {
      captured.push((await request.json()) as ComposeAgentRequest);
      return HttpResponse.json({
        coverage: 'full',
        name_suggestion: '재무 리포터',
        system_prompt: '갱신된 프롬프트',
        tool_ids: ['excel_export', 'tavily_search'],
        workers: [],
        flow_hint: 'excel_export → tavily_search',
        llm_model_id: 'model-default',
        temperature: 0.7,
        missing_capabilities: [],
        notes: '',
      });
    }),
  );
  return captured;
};

describe('FixAgentPanel (fix-agent-composer F3~F6)', () => {
  it('F3: 빈 상태 — 타이틀·예시 프롬프트를 렌더하고, 예시 클릭 시 입력창에 삽입한다', async () => {
    renderPanel();

    expect(screen.getByText('새 에이전트 수정')).toBeInTheDocument();
    expect(screen.getByText('자연어로 에이전트를 수정하세요')).toBeInTheDocument();

    await userEvent.click(screen.getByText(/tavily 검색 도구 추가해줘/));
    expect(screen.getByRole('textbox')).toHaveValue('tavily 검색 도구 추가해줘');
  });

  it('edit 모드 빈 상태 타이틀은 "{이름} 수정"', () => {
    renderPanel({ mode: 'edit' });
    expect(screen.getByText('재무 리포터 수정')).toBeInTheDocument();
  });

  it('F4: 전송 시 user 버블+초안 카드를 렌더하고, current_config에 폼 스냅샷을 담아 보낸다', async () => {
    const captured = captureCompose();
    renderPanel();

    await userEvent.type(screen.getByRole('textbox'), 'tavily 도구 추가해줘{enter}');

    expect(await screen.findByText('tavily 도구 추가해줘')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '적용하기' })).toBeInTheDocument();

    expect(captured).toHaveLength(1);
    expect(captured[0].user_request).toBe('tavily 도구 추가해줘');
    expect(captured[0].current_config).toEqual({
      name: '재무 리포터',
      system_prompt: '당신은 재무 에이전트입니다.',
      tool_ids: ['excel_export'],
      llm_model_id: 'model-default', // model_name → id 매핑
      temperature: 0.7,
    });
    expect(captured[0].history).toBeNull();
  });

  it('F5: 두 번째 전송의 history에 이전 user 턴과 assistant 초안 요약이 포함된다', async () => {
    const captured = captureCompose();
    renderPanel();

    await userEvent.type(screen.getByRole('textbox'), '첫 요청{enter}');
    await screen.findByRole('button', { name: '적용하기' });

    await userEvent.type(screen.getByRole('textbox'), '두번째 요청{enter}');
    await screen.findAllByRole('button', { name: '적용하기' });

    expect(captured).toHaveLength(2);
    const history = captured[1].history!;
    expect(history[0]).toEqual({ role: 'user', content: '첫 요청' });
    expect(history[1].role).toBe('assistant');
    expect(history[1].content).toContain('초안(coverage: full)');
    expect(history[1].content).toContain('excel_export, tavily_search');
  });

  it('적용하기 클릭 시 onApplyDraft 호출 + 적용됨 표시', async () => {
    captureCompose();
    const { onApplyDraft } = renderPanel();

    await userEvent.type(screen.getByRole('textbox'), '요청{enter}');
    await userEvent.click(await screen.findByRole('button', { name: '적용하기' }));

    expect(onApplyDraft).toHaveBeenCalledTimes(1);
    expect(onApplyDraft.mock.calls[0][0].tool_ids).toEqual([
      'excel_export',
      'tavily_search',
    ]);
    expect(screen.getByText('✓ 적용됨')).toBeInTheDocument();
  });

  it('F6: 새 대화 클릭 시 메시지가 초기화되어 빈 상태로 돌아간다', async () => {
    captureCompose();
    renderPanel();

    await userEvent.type(screen.getByRole('textbox'), '요청{enter}');
    await screen.findByRole('button', { name: '적용하기' });

    await userEvent.click(screen.getByRole('button', { name: /새 대화/ }));
    expect(screen.getByText('새 에이전트 수정')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '적용하기' })).not.toBeInTheDocument();
  });

  it('F9(에러 경로): compose 실패 시 에러 버블을 표시하고 대화를 유지한다', async () => {
    server.use(
      http.post('*/api/v1/agents/compose', () =>
        HttpResponse.json({ detail: '실패' }, { status: 500 }),
      ),
    );
    renderPanel();

    await userEvent.type(screen.getByRole('textbox'), '요청{enter}');

    expect(await screen.findByText(/초안 생성에 실패했습니다/)).toBeInTheDocument();
    expect(screen.getByText('요청')).toBeInTheDocument(); // user 버블 유지
    expect(screen.getByRole('textbox')).not.toBeDisabled(); // 재시도 가능
  });
});
