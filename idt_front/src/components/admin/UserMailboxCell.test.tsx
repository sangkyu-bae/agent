import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import UserMailboxCell from './UserMailboxCell';

// mcp-identity-header Design §5.1, §5.4 (AdminUsersPage), §8.3 L2-1·L2-2

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const PATCH_URL = '*/api/v1/admin/users/:id/mailbox';

const renderCell = (mailbox: string | null) =>
  render(<UserMailboxCell userId={7} mailboxUpn={mailbox} />, { wrapper: createWrapper() });

describe('UserMailboxCell', () => {
  it('미등록이면 대시와 등록 버튼을 보여준다', () => {
    renderCell(null);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '등록' })).toBeInTheDocument();
  });

  it('등록된 메일함과 편집 버튼을 보여준다', () => {
    renderCell('kim@corp.com');
    expect(screen.getByText('kim@corp.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '편집' })).toBeInTheDocument();
  });

  it('L2-1: 입력 후 저장하면 PATCH 로 보내고 편집을 닫는다', async () => {
    let captured: { id: string; body: unknown } | null = null;
    server.use(
      http.patch(PATCH_URL, async ({ request, params }) => {
        captured = { id: String(params.id), body: await request.json() };
        return HttpResponse.json({ id: 7, email: 'a@b.c', mailbox_upn: 'kim@corp.com' });
      }),
    );
    const user = userEvent.setup();
    renderCell(null);

    await user.click(screen.getByRole('button', { name: '등록' }));
    await user.type(screen.getByLabelText('메일함 주소'), 'Kim@Corp.com');
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({ id: '7', body: { mailbox_upn: 'Kim@Corp.com' } });
    await waitFor(() => expect(screen.queryByLabelText('메일함 주소')).not.toBeInTheDocument());
  });

  it('빈 값으로 저장하면 null — 해제', async () => {
    let body: unknown = undefined;
    server.use(
      http.patch(PATCH_URL, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 7, email: 'a@b.c', mailbox_upn: null });
      }),
    );
    const user = userEvent.setup();
    renderCell('kim@corp.com');

    await user.click(screen.getByRole('button', { name: '편집' }));
    await user.clear(screen.getByLabelText('메일함 주소'));
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(body).toEqual({ mailbox_upn: null }));
  });

  it('L2-2: 저장 중에는 저장 버튼이 비활성화된다', async () => {
    server.use(
      http.patch(PATCH_URL, async () => {
        await delay(200);
        return HttpResponse.json({ id: 7, email: 'a@b.c', mailbox_upn: 'x@y.co' });
      }),
    );
    const user = userEvent.setup();
    renderCell(null);

    await user.click(screen.getByRole('button', { name: '등록' }));
    await user.type(screen.getByLabelText('메일함 주소'), 'x@y.co');
    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(screen.getByRole('button', { name: /저장/ })).toBeDisabled();
  });

  it('400 이면 서버 메시지를 입력창 아래에 보여주고 편집을 유지한다', async () => {
    server.use(
      http.patch(PATCH_URL, () =>
        HttpResponse.json({ detail: 'Mailbox must be an email address' }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderCell(null);

    await user.click(screen.getByRole('button', { name: '등록' }));
    await user.type(screen.getByLabelText('메일함 주소'), 'bad');
    await user.click(screen.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('Mailbox must be an email address')).toBeInTheDocument();
    expect(screen.getByLabelText('메일함 주소')).toBeInTheDocument();
  });

  it('취소하면 요청 없이 편집을 닫는다', async () => {
    let called = false;
    server.use(
      http.patch(PATCH_URL, () => {
        called = true;
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    renderCell('kim@corp.com');

    await user.click(screen.getByRole('button', { name: '편집' }));
    await user.click(screen.getByRole('button', { name: '취소' }));

    expect(screen.getByText('kim@corp.com')).toBeInTheDocument();
    expect(called).toBe(false);
  });
});
