// eval-hub: 평가 실행 탭 — 목록·failed 에러 표면화·실행 폼 검증·202 페이로드
import { render, screen, waitFor } from '@testing-library/react';
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

const failedRun = {
  id: 'run-1',
  eval_type: 'batch',
  target_type: 'rag',
  status: 'failed',
  total_cases: 2,
  created_at: '2026-08-01T00:00:00Z',
  completed_at: '2026-08-01T00:01:00Z',
  summary: {},
  error_message: '컬렉션을 찾을 수 없습니다',
  config: {},
};

const metrics = [
  {
    key: 'faithfulness',
    name: '충실성 (Faithfulness)',
    description: '근거 이탈 측정',
    target_types: ['rag'],
    requires_ground_truth: false,
  },
  {
    key: 'answer_relevancy',
    name: '답변 관련성',
    description: '질문 부합 측정',
    target_types: ['rag', 'agent'],
    requires_ground_truth: false,
  },
];

const stubFormApis = () => {
  server.use(
    http.get('*/api/ragas/metrics', () => HttpResponse.json(metrics)),
    http.get('*/api/ragas/testsets', () =>
      HttpResponse.json({
        ...emptyPage,
        items: [
          {
            id: 'ts-1', name: '여신 QA셋', description: '', case_count: 2,
            created_at: '2026-08-01T00:00:00Z', user_id: '1',
          },
        ],
        total: 1,
      }),
    ),
    http.get('*/api/v1/agents', () =>
      HttpResponse.json({ agents: [], total: 0, page: 1, size: 20 }),
    ),
    http.get('*/api/v1/knowledge-bases', () =>
      HttpResponse.json({
        knowledge_bases: [
          { kb_id: 'kb-1', name: '여신 KB', scope: 'public', collection_name: 'col-loan' },
        ],
      }),
    ),
    http.get('*/api/v1/llm-models', () => HttpResponse.json({ models: [] })),
  );
};

const renderTab = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <RunsTab />
    </Wrapper>,
  );
};

describe('평가 실행 탭', () => {
  it('failed 실행 클릭 시 error_message 표면화', async () => {
    server.use(
      http.get('*/api/ragas/runs', () =>
        HttpResponse.json({ ...emptyPage, items: [failedRun], total: 1 }),
      ),
      http.get('*/api/ragas/runs/run-1', () => HttpResponse.json(failedRun)),
      http.get('*/api/ragas/runs/run-1/results', () =>
        HttpResponse.json(emptyPage),
      ),
    );
    renderTab();
    await userEvent.click(await screen.findByText('실패'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '컬렉션을 찾을 수 없습니다',
    );
  });

  it('실행 폼 — 메트릭 미선택 시 인라인 에러', async () => {
    server.use(
      http.get('*/api/ragas/runs', () => HttpResponse.json(emptyPage)),
    );
    stubFormApis();
    renderTab();
    await userEvent.click(await screen.findByText('+ 평가 실행'));

    // RAG 대상 + KB + 테스트셋 선택, 메트릭은 미선택
    await userEvent.click(screen.getByText('RAG'));
    await userEvent.selectOptions(
      await screen.findByLabelText('지식 베이스'), 'col-loan',
    );
    await userEvent.selectOptions(screen.getByLabelText('테스트셋'), 'ts-1');
    await userEvent.click(screen.getByRole('button', { name: '평가 시작' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '메트릭을 1개 이상 선택하세요.',
    );
  });

  it('실행 폼 제출 — testset_id 기반 202 페이로드', async () => {
    let payload: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/ragas/runs', () => HttpResponse.json(emptyPage)),
      http.post('*/api/ragas/batch', async ({ request }) => {
        payload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { run_id: 'run-new', status: 'pending', total_cases: 2, message: 'ok' },
          { status: 202 },
        );
      }),
    );
    stubFormApis();
    renderTab();
    await userEvent.click(await screen.findByText('+ 평가 실행'));

    await userEvent.click(screen.getByText('RAG'));
    await userEvent.selectOptions(
      await screen.findByLabelText('지식 베이스'), 'col-loan',
    );
    await userEvent.selectOptions(screen.getByLabelText('테스트셋'), 'ts-1');
    await userEvent.click(
      await screen.findByRole('checkbox', { name: /충실성/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '평가 시작' }));

    await waitFor(() => expect(payload).not.toBeNull());
    expect(payload).toMatchObject({
      target_type: 'rag',
      testset_id: 'ts-1',
      metrics: ['faithfulness'],
      collection_name: 'col-loan',
    });
    expect(payload).not.toHaveProperty('agent_id');
  });
});
