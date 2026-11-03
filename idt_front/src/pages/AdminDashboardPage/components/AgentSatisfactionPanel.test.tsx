// agent-eval-gate: 에이전트별 만족도 위젯.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
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
      <MemoryRouter>
        <AgentSatisfactionPanel />
      </MemoryRouter>
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

  // negative-feedback-drilldown Design §8.4
  describe('드릴다운', () => {
    const negative = {
      message_id: 284,
      agent_id: 'agent-1',
      comment: '답변이 틀림',
      created_at: '2026-10-20T05:03:00Z',
    };
    const mockApi = () => {
      const seen = { drilldown: 0 };
      server.use(
        http.get('*/api/v1/admin/eval/agents', () => HttpResponse.json([])),
        http.get('*/api/v1/admin/eval/recent-negative', () => HttpResponse.json([negative])),
        http.get('*/api/v1/admin/eval/negative/284/drilldown', () => {
          seen.drilldown += 1;
          return HttpResponse.json({
            message_id: 284,
            agent_id: 'agent-1',
            question: '한도가 얼마인가요?',
            answer: '1억원입니다.',
            runs: [],
          });
        }),
      );
      return seen;
    };

    it('항목은 버튼이고 열기 전에는 드릴다운을 조회하지 않는다', async () => {
      const seen = mockApi();
      renderPanel();

      expect(await screen.findByRole('button', { name: /상세 보기/ })).toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(seen.drilldown).toBe(0);
    });

    it('항목을 클릭하면 모달을 열고 1회 조회한다', async () => {
      const seen = mockApi();
      renderPanel();

      await userEvent.click(await screen.findByRole('button', { name: /상세 보기/ }));

      expect(await screen.findByRole('dialog')).toBeInTheDocument();
      expect(await screen.findByText('한도가 얼마인가요?')).toBeInTheDocument();
      expect(seen.drilldown).toBe(1);
    });

    it('키보드로 열 수 있다', async () => {
      mockApi();
      renderPanel();

      (await screen.findByRole('button', { name: /상세 보기/ })).focus();
      await userEvent.keyboard('{Enter}');

      expect(await screen.findByRole('dialog')).toBeInTheDocument();
    });

    it('모달을 닫아도 패널은 유지된다', async () => {
      mockApi();
      renderPanel();

      await userEvent.click(await screen.findByRole('button', { name: /상세 보기/ }));
      await userEvent.click(await screen.findByRole('button', { name: '닫기' }));

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByText('답변이 틀림')).toBeInTheDocument();
    });

    it('같은 메시지에 부정 평가가 2건이어도 각각 표시한다', async () => {
      server.use(
        http.get('*/api/v1/admin/eval/agents', () => HttpResponse.json([])),
        http.get('*/api/v1/admin/eval/recent-negative', () =>
          HttpResponse.json([
            negative,
            { ...negative, comment: '근거가 없음', created_at: '2026-10-21T05:03:00Z' },
          ]),
        ),
      );
      renderPanel();

      expect(await screen.findByText('근거가 없음')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /상세 보기/ })).toHaveLength(2);
    });

    // Check I-1: 코멘트 없는 항목끼리 접근성 이름이 같아지지 않게 에이전트를 포함한다
    it('코멘트가 없어도 에이전트로 버튼 이름이 구분된다', async () => {
      server.use(
        http.get('*/api/v1/admin/eval/agents', () => HttpResponse.json([])),
        http.get('*/api/v1/admin/eval/recent-negative', () =>
          HttpResponse.json([
            { ...negative, agent_id: 'agent-a', comment: null },
            { ...negative, message_id: 285, agent_id: 'agent-b', comment: null },
          ]),
        ),
      );
      renderPanel();

      expect(
        await screen.findByRole('button', { name: 'agent-a 코멘트 없음 상세 보기' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'agent-b 코멘트 없음 상세 보기' }),
      ).toBeInTheDocument();
    });

    // Check M-3: 빈 문자열 코멘트는 모달과 같이 "코멘트 없음"으로 표시한다
    it('빈 문자열 코멘트는 코멘트 없음으로 표시한다', async () => {
      server.use(
        http.get('*/api/v1/admin/eval/agents', () => HttpResponse.json([])),
        http.get('*/api/v1/admin/eval/recent-negative', () =>
          HttpResponse.json([{ ...negative, comment: '' }]),
        ),
      );
      renderPanel();

      expect(await screen.findByText('(코멘트 없음)')).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'agent-1 코멘트 없음 상세 보기' }),
      ).toBeInTheDocument();
    });
  });
});
