// agent-model-benchmark Design §5.4: 매트릭스 표의 필수 계약 검증.
// 특히 "null은 0이 아니라 —" 규약은 의사결정을 직접 좌우하므로 테스트로 고정한다.
import { render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import SweepMatrixPanel from './SweepMatrixPanel';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const LLM_MODELS = {
  models: [
    { id: 'm-judge', display_name: 'GPT-4o (judge)', is_active: true },
    { id: 'm-1', display_name: 'GPT-4o', is_active: true },
    { id: 'm-2', display_name: 'GPT-4o mini', is_active: true },
  ],
};

const sweep = (rows: unknown[]) => ({
  id: 'sw-1',
  name: '여신심사봇 모델 비교',
  agent_id: 'ag-1',
  testset_id: 'ts-1',
  judge_llm_model_id: 'm-judge',
  temperature: 0,
  status: 'completed',
  total_runs: rows.length,
  completed_runs: rows.length,
  estimated_cost_usd: '1.842000',
  created_at: '2026-09-01T00:00:00Z',
  completed_at: '2026-09-01T00:13:00Z',
  model_ids: ['m-1', 'm-2'],
  metrics: ['answer_relevancy'],
  agent_name: '여신심사봇',
  testset_name: '여신 골든셋 v3',
  case_count: 20,
  actual_cost_usd: '1.611200',
  rows,
});

const row = (over: Record<string, unknown> = {}) => ({
  run_id: 'r-1',
  llm_model_id: 'm-1',
  llm_model_name: 'GPT-4o',
  status: 'completed',
  quality: { answer_relevancy: 0.91 },
  cost_usd: '1.104000',
  latency_p50_ms: 4210,
  latency_p95_ms: 8740,
  tool_f1: 0.92,
  measured_cases: 20,
  failed_cases: 0,
  error_message: null,
  ...over,
});

const mount = (rows: unknown[]) => {
  server.use(
    http.get('*/api/ragas/sweeps/sw-1', () => HttpResponse.json(sweep(rows))),
    http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
  );
  return render(<SweepMatrixPanel sweepId="sw-1" onClose={() => {}} />, {
    wrapper: createWrapper(),
  });
};

describe('SweepMatrixPanel', () => {
  it('모델별 행을 렌더한다', async () => {
    mount([row(), row({ run_id: 'r-2', llm_model_id: 'm-2', llm_model_name: 'GPT-4o mini' })]);

    expect(await screen.findByTestId('sweep-row-r-1')).toBeInTheDocument();
    expect(screen.getByTestId('sweep-row-r-2')).toBeInTheDocument();
  });

  it('judge 모델명을 항상 병기한다', async () => {
    // judge가 다르면 점수를 비교할 수 없으므로 화면에 반드시 드러나야 한다 (Plan R-2)
    mount([row()]);

    expect(await screen.findByTestId('sweep-judge')).toHaveTextContent(
      'GPT-4o (judge)',
    );
  });

  it('측정 불가(null) 지표는 0이 아니라 —로 렌더한다', async () => {
    mount([
      row({
        run_id: 'r-na',
        quality: { answer_relevancy: null },
        cost_usd: null,
        latency_p50_ms: null,
        tool_f1: null,
      }),
    ]);

    await waitFor(() =>
      expect(screen.getByTestId('cell-r-na-answer_relevancy')).toHaveTextContent('—'),
    );
    expect(screen.getByTestId('cell-r-na-cost_usd')).toHaveTextContent('—');
    expect(screen.getByTestId('cell-r-na-tool_f1')).toHaveTextContent('—');
    // 0으로 오해될 표기가 섞이면 안 된다
    expect(screen.getByTestId('cell-r-na-cost_usd')).not.toHaveTextContent('0.0000');
  });

  it('품질 지표는 높은 값을, 비용은 낮은 값을 최고로 표시한다', async () => {
    mount([
      row({ run_id: 'r-hi', quality: { answer_relevancy: 0.91 }, cost_usd: '1.10' }),
      row({
        run_id: 'r-lo',
        llm_model_id: 'm-2',
        quality: { answer_relevancy: 0.86 },
        cost_usd: '0.06',
      }),
    ]);

    await waitFor(() =>
      expect(screen.getByTestId('cell-r-hi-answer_relevancy')).toHaveTextContent('★'),
    );
    expect(screen.getByTestId('cell-r-lo-answer_relevancy')).not.toHaveTextContent('★');
    // 비용은 쌀수록 좋다 — 방향이 뒤집혀야 한다
    expect(screen.getByTestId('cell-r-lo-cost_usd')).toHaveTextContent('★');
    expect(screen.getByTestId('cell-r-hi-cost_usd')).not.toHaveTextContent('★');
  });

  it('실패한 모델 행을 표시하되 나머지 행은 정상 렌더한다', async () => {
    mount([
      row(),
      row({
        run_id: 'r-fail',
        llm_model_id: 'm-2',
        llm_model_name: 'Qwen (NPU)',
        status: 'failed',
        quality: {},
        cost_usd: null,
        latency_p50_ms: null,
        tool_f1: null,
        measured_cases: 0,
        failed_cases: 20,
        error_message: 'connection refused',
      }),
    ]);

    expect(await screen.findByText('실패')).toBeInTheDocument();
    // 부분 실패여도 성공한 행의 값은 그대로 보여야 한다 (Design D12)
    expect(screen.getByTestId('cell-r-1-answer_relevancy')).toHaveTextContent('0.910');
  });
});


describe('SweepMatrixPanel — 실험 조건과 비용 대조', () => {
  it('에이전트명·테스트셋명·케이스 수를 표시한다 (G-2)', async () => {
    mount([row()]);

    const conditions = await screen.findByTestId('sweep-conditions');
    expect(conditions).toHaveTextContent('여신심사봇');
    expect(conditions).toHaveTextContent('여신 골든셋 v3');
    expect(conditions).toHaveTextContent('20건');
  });

  it('예상 대비 실제 비용을 함께 보여준다 (G-1)', async () => {
    mount([row()]);

    const cost = await screen.findByTestId('sweep-cost');
    expect(cost).toHaveTextContent('1.842000');
    expect(cost).toHaveTextContent('1.611200');
  });

  it('추정 오차율을 계산해 표시한다', async () => {
    // 1.8420 → 1.6112 = -12.5% → 반올림 -13%
    mount([row()]);

    expect(await screen.findByTestId('sweep-cost')).toHaveTextContent('-13%');
  });

  it('실제 비용이 없으면 0이 아니라 —로 표시한다', async () => {
    server.use(
      http.get('*/api/ragas/sweeps/sw-1', () =>
        HttpResponse.json({ ...sweep([row()]), actual_cost_usd: null }),
      ),
      http.get('*/api/v1/llm-models', () => HttpResponse.json(LLM_MODELS)),
    );
    render(<SweepMatrixPanel sweepId="sw-1" onClose={() => {}} />, {
      wrapper: createWrapper(),
    });

    const cost = await screen.findByTestId('sweep-cost');
    expect(cost).toHaveTextContent('실제 —');
  });
});
