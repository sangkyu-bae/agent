// agent-model-benchmark Design §5.4: 생성 폼의 게이트 2가지를 고정한다.
//   1) 모델 5개 상한 — 초과 선택 자체가 막혀야 한다
//   2) 예상 비용을 확인하기 전에는 실행 불가 — 금액을 모른 채 과금되면 안 된다
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import CreateSweepModal from './CreateSweepModal';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const MODELS = {
  models: Array.from({ length: 7 }, (_, i) => ({
    id: `m-${i}`,
    display_name: `모델${i}`,
    is_active: true,
  })),
};

const AGENTS = { agents: [{ agent_id: 'ag-1', name: '여신심사봇' }], total: 1 };

const TESTSETS = {
  items: [{ id: 'ts-1', name: '여신 골든셋', case_count: 20, description: '', created_at: '', user_id: null }],
  total: 1,
  limit: 20,
  offset: 0,
};

const ESTIMATE = {
  case_count: 20,
  model_count: 2,
  total_calls: 40,
  estimated_cost_usd: '1.842000',
  estimated_minutes: 14,
  basis: { source: 'ai_run_recent_avg', sample_size: 37 },
  per_model: [
    { llm_model_id: 'm-0', display_name: '모델0', estimated_cost_usd: '1.10' },
    { llm_model_id: 'm-1', display_name: '모델1', estimated_cost_usd: '0.74' },
  ],
};

const mount = () => {
  server.use(
    http.get('*/api/v1/llm-models', () => HttpResponse.json(MODELS)),
    http.get('*/api/v1/agents', () => HttpResponse.json(AGENTS)),
    http.get('*/api/ragas/testsets', () => HttpResponse.json(TESTSETS)),
    http.post('*/api/ragas/sweeps/estimate', () => HttpResponse.json(ESTIMATE)),
  );
  return render(<CreateSweepModal onClose={() => {}} onCreated={() => {}} />, {
    wrapper: createWrapper(),
  });
};

// '모델0'은 체크박스 라벨과 judge <option> 양쪽에 나타나므로
// 모델 목록 컨테이너 안으로 범위를 좁혀 조회한다.
const modelBoxes = async () => {
  const list = await screen.findByTestId('sweep-model-list');
  await waitFor(() =>
    expect(within(list).getAllByRole('checkbox')).toHaveLength(7),
  );
  return within(list).getAllByRole('checkbox');
};

describe('CreateSweepModal — 모델 상한 게이트', () => {
  it('5개를 고르면 나머지 체크박스가 비활성화된다', async () => {
    const user = userEvent.setup();
    mount();
    const boxes = await modelBoxes();

    for (let i = 0; i < 5; i += 1) await user.click(boxes[i]);

    expect(boxes[5]).toBeDisabled();
    expect(boxes[6]).toBeDisabled();
    // 이미 고른 건 해제할 수 있어야 한다
    expect(boxes[0]).not.toBeDisabled();
  });

  it('상한 도달 시 안내 문구를 보여준다', async () => {
    const user = userEvent.setup();
    mount();
    const boxes = await modelBoxes();

    for (let i = 0; i < 5; i += 1) await user.click(boxes[i]);

    expect(screen.getByText(/최대 5개/)).toBeInTheDocument();
  });

  it('하나 해제하면 다시 선택할 수 있다', async () => {
    const user = userEvent.setup();
    mount();
    const boxes = await modelBoxes();

    for (let i = 0; i < 5; i += 1) await user.click(boxes[i]);
    await user.click(boxes[0]);

    expect(boxes[5]).not.toBeDisabled();
  });
});

describe('CreateSweepModal — 비용 확인 게이트', () => {
  it('예상 비용을 확인하기 전에는 실행 버튼이 비활성화된다', async () => {
    mount();
    await modelBoxes();

    expect(screen.getByRole('button', { name: '실행' })).toBeDisabled();
  });

  it('비용 확인 후 실행이 활성화되고 추정치 라벨이 보인다', async () => {
    const user = userEvent.setup();
    mount();
    const boxes = await modelBoxes();

    await user.type(screen.getByLabelText('이름'), '비교 실험');
    await user.selectOptions(screen.getByLabelText('에이전트'), 'ag-1');
    await user.selectOptions(screen.getByLabelText('테스트셋'), 'ts-1');
    await user.click(boxes[0]);
    await user.selectOptions(screen.getByLabelText('채점 모델 (judge)'), 'm-0');
    await user.click(screen.getByRole('button', { name: '예상 비용 확인' }));

    const panel = await screen.findByTestId('sweep-estimate');
    expect(panel).toHaveTextContent('1.842000');
    // "추정치"임을 반드시 명시해야 한다 (Plan R-3)
    expect(panel).toHaveTextContent('추정치');
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '실행' })).not.toBeDisabled(),
    );
  });

  it('조건을 바꾸면 이전 추정치가 무효화되어 실행이 다시 막힌다', async () => {
    const user = userEvent.setup();
    mount();
    const boxes = await modelBoxes();

    await user.type(screen.getByLabelText('이름'), '비교 실험');
    await user.selectOptions(screen.getByLabelText('에이전트'), 'ag-1');
    await user.selectOptions(screen.getByLabelText('테스트셋'), 'ts-1');
    await user.click(boxes[0]);
    await user.selectOptions(screen.getByLabelText('채점 모델 (judge)'), 'm-0');
    await user.click(screen.getByRole('button', { name: '예상 비용 확인' }));
    await screen.findByTestId('sweep-estimate');

    // 모델을 하나 더 추가하면 금액이 달라진다 — 옛 추정치로 실행하면 안 된다
    await user.click(boxes[1]);

    expect(screen.queryByTestId('sweep-estimate')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '실행' })).toBeDisabled();
  });
});

describe('CreateSweepModal — 메트릭 노출', () => {
  it('agent 대상이 지원하는 3개 지표만 제시한다', async () => {
    // faithfulness·context_* 를 노출하면 사용자가 고른 뒤 422를 맞는다
    mount();
    await modelBoxes();

    expect(screen.getByText('답변 관련성')).toBeInTheDocument();
    expect(screen.getByText('답변 정확성')).toBeInTheDocument();
    expect(screen.getByText('답변 유사도')).toBeInTheDocument();
    expect(screen.queryByText(/충실성|Faithfulness/i)).not.toBeInTheDocument();
  });

  it('temperature 0 고정을 안내한다', async () => {
    mount();
    await modelBoxes();

    expect(screen.getByText(/temperature/)).toBeInTheDocument();
  });
});
