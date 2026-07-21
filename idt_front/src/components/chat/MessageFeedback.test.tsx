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

// eval-feedback-loop §3-6: 👎 이유 수집 패널
describe('MessageFeedback 이유 수집', () => {
  const downFeedback = (comment: string | null = null) =>
    http.get('*/api/v1/conversations/messages/:id/feedback', () =>
      HttpResponse.json({ message_id: 5, rating: 'down', comment }),
    );

  it('👎 상태면 이유 패널을 노출한다', async () => {
    server.use(downFeedback());
    renderFb();

    expect(await screen.findByRole('group', { name: '싫어요 이유' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '부정확함' })).toBeInTheDocument();
  });

  it('칩 클릭 시 down + 칩 라벨 comment로 제출한다', async () => {
    let posted: { rating?: string; comment?: string } | null = null;
    server.use(
      downFeedback(),
      http.post('*/api/v1/conversations/messages/:id/feedback', async ({ request }) => {
        posted = (await request.json()) as typeof posted;
        return HttpResponse.json({ message_id: 5, rating: 'down', comment: '근거 부족' });
      }),
    );
    const user = userEvent.setup();
    renderFb();

    await user.click(await screen.findByRole('button', { name: '근거 부족' }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.rating).toBe('down');
    expect(posted!.comment).toBe('근거 부족');
  });

  it('자유 코멘트를 입력해 제출한다', async () => {
    let posted: { rating?: string; comment?: string } | null = null;
    server.use(
      downFeedback(),
      http.post('*/api/v1/conversations/messages/:id/feedback', async ({ request }) => {
        posted = (await request.json()) as typeof posted;
        return HttpResponse.json({ message_id: 5, rating: 'down', comment: '표가 깨져요' });
      }),
    );
    const user = userEvent.setup();
    renderFb();

    await user.type(
      await screen.findByPlaceholderText('무엇이 아쉬웠나요?'), '표가 깨져요',
    );
    await user.click(screen.getByRole('button', { name: '보내기' }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.comment).toBe('표가 깨져요');
  });

  it('이유가 이미 있으면 패널 대신 이유를 표시한다', async () => {
    server.use(downFeedback('근거 부족'));
    renderFb();

    expect(await screen.findByText(/이유: 근거 부족/)).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: '싫어요 이유' })).not.toBeInTheDocument();
  });

  it('👎 재클릭(취소) 시 패널이 닫힌다', async () => {
    server.use(
      downFeedback(),
      http.post('*/api/v1/conversations/messages/:id/feedback', () =>
        HttpResponse.json({ message_id: 5, rating: null, comment: null }),
      ),
    );
    const user = userEvent.setup();
    renderFb();

    await screen.findByRole('group', { name: '싫어요 이유' });
    await user.click(screen.getByRole('button', { name: '싫어요' }));

    await waitFor(() =>
      expect(screen.queryByRole('group', { name: '싫어요 이유' })).not.toBeInTheDocument(),
    );
  });

  it('👍 상태에서는 이유 패널이 없다', async () => {
    server.use(
      http.get('*/api/v1/conversations/messages/:id/feedback', () =>
        HttpResponse.json({ message_id: 5, rating: 'up', comment: null }),
      ),
    );
    renderFb();

    await screen.findByRole('button', { name: '좋아요' });
    expect(screen.queryByRole('group', { name: '싫어요 이유' })).not.toBeInTheDocument();
  });
});
