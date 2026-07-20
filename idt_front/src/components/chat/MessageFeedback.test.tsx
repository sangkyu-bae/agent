// agent-eval-gate: 답변 평가 버튼 — 👍/👎 토글.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import MessageFeedback from './MessageFeedback';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderFb = (messageId = 5) => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MessageFeedback messageId={messageId} />
    </Wrapper>,
  );
};

describe('MessageFeedback', () => {
  it('👍/👎 버튼을 렌더한다', async () => {
    renderFb();
    expect(await screen.findByRole('button', { name: '좋아요' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '싫어요' })).toBeInTheDocument();
  });

  it('👍 클릭 시 up 평가를 제출한다', async () => {
    let posted: { rating?: string } | null = null;
    server.use(
      http.post('*/api/v1/conversations/messages/:id/feedback', async ({ request }) => {
        posted = (await request.json()) as typeof posted;
        return HttpResponse.json({ message_id: 5, rating: 'up', comment: null });
      }),
    );
    const user = userEvent.setup();
    renderFb();

    await user.click(await screen.findByRole('button', { name: '좋아요' }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.rating).toBe('up');
  });

  it('기존 평가가 있으면 활성 상태로 표시한다', async () => {
    server.use(
      http.get('*/api/v1/conversations/messages/:id/feedback', () =>
        HttpResponse.json({ message_id: 5, rating: 'up', comment: null }),
      ),
    );
    renderFb();

    const up = await screen.findByRole('button', { name: '좋아요' });
    await waitFor(() => expect(up).toHaveAttribute('aria-pressed', 'true'));
  });
});
