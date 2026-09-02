// L2 시나리오 보강 (Design §8.3): 탭에서 모달을 열고 실제로 실행하는 경로.
// L2-1 [+ 모델 스윕] 클릭 → 모달 오픈
// L2-5 [실행] → POST 페이로드 확인
// 스윕 섹션 렌더 및 매트릭스 진입까지 종단으로 확인한다.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import RunsTab from './RunsTab';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const emptyPage = { items: [], total: 0, limit: 20, offset: 0 };

const MODELS = {
  models: [
    { id: 'm-1', display_name: '모델A', is_active: true },
    { id: 'm-2', display_name: '모델B', is_active: true },
  ],
};

const TESTSETS = {
  ...emptyPage,
  items: [
    {
      id: 'ts-1', name: '여신 골든셋', description: '', case_count: 20,
      created_at: '2026-09-01T00:00:00Z', user_id: '1',
    },
  ],
  total: 1,
};

const AGENTS = {
  agents: [{ agent_id: 'ag-1', name: '여신심사봇' }],
  total: 1, page: 1, size: 20,
};

const ESTIMATE = {
  case_count: 20, model_count: 1, total_calls: 20,
  estimated_cost_usd: '1.842000', estimated_minutes: 14,
  basis: { source: 'ai_run_recent_avg', sample_size: 37 },
  per_model: [
    { llm_model_id: 'm-1', display_name: '모델A', estimated_cost_usd: '1.10' },
  ],
};

const SWEEP_SUMMARY = {
  id: 'sw-1', name: '여신심사봇 모델 비교', agent_id: 'ag-1', testset_id: 'ts-1',
  judge_llm_model_id: 'm-1', temperature: 0, status: 'running',
  total_runs: 2, completed_runs: 1, estimated_cost_usd: '1.842000',
  created_at: '2026-09-02T00:00:00Z', completed_at: null,
};

const baseHandlers = (sweeps: unknown[] = []) => [
  http.get('*/api/ragas/runs', () => HttpResponse.json(emptyPage)),
  http.get('*/api/ragas/metrics', () => HttpResponse.json([])),
  http.get('*/api/ragas/testsets', () => HttpResponse.json(TESTSETS)),
  http.get('*/api/v1/agents', () => HttpResponse.json(AGENTS)),
  http.get('*/api/v1/knowledge-bases', () =>
    HttpResponse.json({ knowledge_bases: [] }),
  ),
  http.get('*/api/v1/llm-models', () => HttpResponse.json(MODELS)),
  http.get('*/api/ragas/sweeps', () =>
    HttpResponse.json({ ...emptyPage, items: sweeps, total: sweeps.length }),
  ),
  http.post('*/api/ragas/sweeps/estimate', () => HttpResponse.json(ESTIMATE)),
];

const mount = (sweeps: unknown[] = []) => {
  server.use(...baseHandlers(sweeps));
  return render(<RunsTab />, { wrapper: createWrapper() });
};

describe('L2-1 — 탭에서 스윕 모달 열기', () => {
  it('[+ 모델 스윕] 버튼이 노출된다', async () => {
    mount();

    expect(
      await screen.findByRole('button', { name: '+ 모델 스윕' }),
    ).toBeInTheDocument();
  });

  it('클릭하면 모달이 열리고 temperature 고정 안내가 보인다', async () => {
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: '+ 모델 스윕' }));

    expect(await screen.findByTestId('sweep-model-list')).toBeInTheDocument();
    expect(screen.getByText(/temperature/)).toBeInTheDocument();
  });
});

describe('L2-5 — 실행 페이로드', () => {
  it('실행 시 선택한 조건이 그대로 POST된다', async () => {
    const user = userEvent.setup();
    let payload: Record<string, unknown> | null = null;
    server.use(
      ...baseHandlers(),
      http.post('*/api/ragas/sweeps', async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            sweep_id: 'sw-1', status: 'pending', total_runs: 1,
            estimated_cost_usd: '1.842000', message: '시작됨',
          },
          { status: 202 },
        );
      }),
    );
    render(<RunsTab />, { wrapper: createWrapper() });

    await user.click(await screen.findByRole('button', { name: '+ 모델 스윕' }));
    const list = await screen.findByTestId('sweep-model-list');
    await user.type(screen.getByLabelText('이름'), '비교 실험');
    await user.selectOptions(screen.getByLabelText('에이전트'), 'ag-1');
    await user.selectOptions(screen.getByLabelText('테스트셋'), 'ts-1');
    await user.click(within(list).getAllByRole('checkbox')[0]);
    await user.selectOptions(screen.getByLabelText('채점 모델 (judge)'), 'm-1');
    await user.click(screen.getByRole('button', { name: '예상 비용 확인' }));
    await screen.findByTestId('sweep-estimate');
    await user.click(screen.getByRole('button', { name: '실행' }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({
      name: '비교 실험',
      agent_id: 'ag-1',
      testset_id: 'ts-1',
      model_ids: ['m-1'],
      judge_llm_model_id: 'm-1',
    });
    // 백엔드가 422로 거절하는 메트릭이 섞이면 안 된다
    expect(payload!.metrics).toEqual(['answer_relevancy']);
  });
});

describe('스윕 목록 섹션', () => {
  it('진행 중인 스윕을 상태·진행률과 함께 보여준다', async () => {
    mount([SWEEP_SUMMARY]);

    const section = await screen.findByTestId('sweep-section');
    expect(section).toHaveTextContent('여신심사봇 모델 비교');
    expect(section).toHaveTextContent('실행 중');
    expect(section).toHaveTextContent('1/2');
  });

  it('스윕이 없으면 섹션을 렌더하지 않는다', async () => {
    mount([]);

    await screen.findByRole('button', { name: '+ 모델 스윕' });
    expect(screen.queryByTestId('sweep-section')).not.toBeInTheDocument();
  });
});