// agent-eval-gate: 에이전트별 만족도 위젯.
import { render, screen } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AgentSatisfactionPanel from './AgentSatisfactionPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPanel = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <AgentSatisfactionPanel />
    </Wrapper>,
  );
};

describe('AgentSatisfactionPanel', () => {
  it('에이전트별 만족도를 렌더한다', async () => {
    server.use(
      http.get('*/api/v1/admin/eval/agents', () =>
        HttpResponse.json([
          { agent_id: 'general-chat', up: 8, down: 2, satisfaction: 0.8 },
        ]),
      ),
      http.get('*/api/v1/admin/eval/recent-negative', () => HttpResponse.json([])),
    );
    renderPanel();

    expect(await screen.findByText('general-chat')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText(/👍 8/)).toBeInTheDocument();
  });

  it('평가 0건이면 "평가 없음" 표시', async () => {
    server.use(
      http.get('*/api/v1/admin/eval/agents', () =>
        HttpResponse.json([
          { agent_id: 'a2', up: 0, down: 0, satisfaction: null },
        ]),
      ),
      http.get('*/api/v1/admin/eval/recent-negative', () => HttpResponse.json([])),
    );
    renderPanel();

    expect(await screen.findByText('a2')).toBeInTheDocument();
    expect(screen.getByText('평가 없음')).toBeInTheDocument();
  });

  it('최근 부정 피드백을 표시한다', async () => {
    server.use(
      http.get('*/api/v1/admin/eval/agents', () => HttpResponse.json([])),
      http.get('*/api/v1/admin/eval/recent-negative', () =>
        HttpResponse.json([
          { message_id: 1, agent_id: 'general-chat', comment: '답변이 틀림', created_at: '2026-07-20T00:00:00Z' },
        ]),
      ),
    );
    renderPanel();

    expect(await screen.findByText('답변이 틀림')).toBeInTheDocument();
  });
});
