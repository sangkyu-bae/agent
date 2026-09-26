import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useAuthStore } from '@/store/authStore';
import AdminMcpServersPage from './index';

// mcp-identity-header Design §5.1, §5.4 (AdminMcpServersPage), §8.3 L2-3 ~ L2-6

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, email: 'admin@test.com', role: 'admin' } as never,
    isAuthenticated: true,
  });
});

const SECRET = 's'.repeat(32);

const outlook = (identity: Record<string, unknown> | null) => ({
  id: 'srv-o',
  user_id: '1',
  name: 'Outlook Mail MCP',
  description: '메일',
  endpoint: 'http://localhost:8006/sse',
  transport: 'sse',
  input_schema: null,
  is_active: true,
  default_requires_approval: false,
  tool_id: 'mcp_srv-o',
  created_at: '2026-09-26T00:00:00Z',
  updated_at: '2026-09-26T00:00:00Z',
  auth_config: null,
  server_config: null,
  identity_config: identity,
});

const MASKED = {
  audience: 'mcp-outlook-server',
  issuer: 'agent-builder',
  header_name: 'X-MCP-Identity',
  claim_name: 'preferred_username',
  claim_source: 'mailbox_upn',
  ttl_seconds: 300,
  secret: '****',
};

const listWith = (identity: Record<string, unknown> | null) =>
  server.use(
    http.get('*/api/v1/mcp-registry', () =>
      HttpResponse.json({ items: [outlook(identity)], total: 1 }),
    ),
  );

const capturePut = () => {
  const box: { body: Record<string, unknown> | null } = { body: null };
  server.use(
    http.put('*/api/v1/mcp-registry/:id', async ({ request }) => {
      box.body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(outlook(null));
    }),
  );
  return box;
};

const renderPage = () => render(<AdminMcpServersPage />, { wrapper: createWrapper() });

describe('AdminMcpServersPage — 호출자 신원 헤더', () => {
  it('신원 헤더가 설정된 서버에 배지를 단다', async () => {
    listWith(MASKED);
    renderPage();
    await screen.findByText('Outlook Mail MCP');
    expect(screen.getByText('신원 헤더')).toBeInTheDocument();
  });

  it('L2-3: 신원 헤더를 켜고 audience·비밀을 넣어 생성하면 identity_config 를 보낸다', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/mcp-registry', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(outlook(MASKED), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'Outlook');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '메일');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'http://localhost:8006/sse',
    );
    await user.click(screen.getByLabelText('호출자 신원 헤더 사용'));
    await user.type(screen.getByLabelText(/audience/), 'mcp-outlook-server');
    await user.type(screen.getByLabelText(/서명 비밀/), SECRET);
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      identity_config: {
        audience: 'mcp-outlook-server',
        secret: SECRET,
        claim_source: 'mailbox_upn',
        header_name: 'X-MCP-Identity',
        ttl_seconds: 300,
      },
    });
  });

  it('신원 헤더를 켰는데 비밀이 없으면 전송하지 않고 오류를 보여준다', async () => {
    let posted = false;
    server.use(
      http.post('*/api/v1/mcp-registry', () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'Outlook');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '메일');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'http://localhost:8006/sse',
    );
    await user.click(screen.getByLabelText('호출자 신원 헤더 사용'));
    await user.type(screen.getByLabelText(/audience/), 'mcp-outlook-server');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(await screen.findByText(/서명 비밀/, { selector: 'p' })).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it('L2-4: 수정 모드에서 비밀을 비우면 secret 키 없이 보낸다 (기존 유지)', async () => {
    listWith(MASKED);
    const put = capturePut();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Outlook Mail MCP');

    await user.click(screen.getByRole('button', { name: '수정' }));
    expect(screen.getByLabelText('호출자 신원 헤더 사용')).toBeChecked();
    expect(screen.getByLabelText(/서명 비밀/)).toHaveAttribute(
      'placeholder',
      expect.stringContaining('비우면 기존 유지'),
    );
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body?.identity_config).toMatchObject({ audience: 'mcp-outlook-server' });
    expect(put.body?.identity_config).not.toHaveProperty('secret');
  });

  it('L2-5: 체크를 해제하고 저장하면 identity_config: null', async () => {
    listWith(MASKED);
    const put = capturePut();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Outlook Mail MCP');

    await user.click(screen.getByRole('button', { name: '수정' }));
    await user.click(screen.getByLabelText('호출자 신원 헤더 사용'));
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body).toHaveProperty('identity_config', null);
  });

  it('L2-6: 신원 미사용 서버를 수정하면 identity_config 키가 없다', async () => {
    listWith(null);
    const put = capturePut();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Outlook Mail MCP');

    await user.click(screen.getByRole('button', { name: '수정' }));
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(put.body).not.toBeNull());
    expect(put.body).not.toHaveProperty('identity_config');
  });
});
