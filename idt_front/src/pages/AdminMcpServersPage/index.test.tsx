import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, beforeEach, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useAuthStore } from '@/store/authStore';
import AdminMcpServersPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  // 페이지는 등록 시 authStore.user.id를 user_id로 주입한다
  useAuthStore.setState({
    user: { id: 1, email: 'admin@test.com', role: 'admin' } as never,
    isAuthenticated: true,
  });
});

const renderPage = () =>
  render(<AdminMcpServersPage />, { wrapper: createWrapper() });

describe('AdminMcpServersPage', () => {
  it('P-1: MCP 서버 목록을 렌더한다', async () => {
    renderPage();
    expect(await screen.findByText('Naver Search')).toBeInTheDocument();
    expect(screen.getByText('Streamable HTTP')).toBeInTheDocument();
    expect(screen.getByText('활성')).toBeInTheDocument();
  });

  it('P-2: 등록 모달에서 SSE 서버를 생성한다 (user_id 주입)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/mcp-registry', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 'srv-new' }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'My SSE');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '설명');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'https://e.example.com/sse',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      name: 'My SSE',
      transport: 'sse',
      user_id: '1',
    });
  });

  it('P-3: 수정 시 시크릿 미입력이면 auth_config를 전송하지 않는다 (기존 유지)', async () => {
    let putBody: Record<string, unknown> | null = null;
    server.use(
      http.put('*/api/v1/mcp-registry/:id', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 'srv-1', name: 'Naver Search' });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '수정' }));
    // 시크릿 필드는 비운 채로 저장
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody).not.toHaveProperty('auth_config');
    expect(putBody).not.toHaveProperty('server_config');
    expect(putBody).toMatchObject({ transport: 'streamable_http' });
  });

  it('P-4: 행 연결 테스트 — 성공 시 도구 목록 표시', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '테스트' }));

    expect(await screen.findByText(/연결 성공/)).toBeInTheDocument();
    expect(screen.getByText('search')).toBeInTheDocument();
  });

  it('P-5: 삭제 확인 다이얼로그 후 DELETE 호출', async () => {
    let deleted = false;
    server.use(
      http.delete('*/api/v1/mcp-registry/:id', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: 'Naver Search 삭제' }));
    // ConfirmDialog의 확인 버튼
    await user.click(screen.getByRole('button', { name: '삭제' }));

    await waitFor(() => expect(deleted).toBe(true));
  });
});

describe('AdminMcpServersPage — 도구 동기화 (mcp-tool-auto-sync)', () => {
  it('S-1: 모든 서버 행에 "동기화" 버튼이 있다 (FR-12 상시 노출)', async () => {
    renderPage();
    await screen.findByText('Naver Search');

    expect(screen.getByRole('button', { name: 'Naver Search 도구 동기화' })).toBeInTheDocument();
  });

  it('S-2: 동기화 클릭 시 mcp_server_id 로 sync 를 호출한다 (FR-11)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/tool-catalog/sync', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ synced_count: 3 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: 'Naver Search 도구 동기화' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toEqual({ mcp_server_id: 'srv-1' });
  });

  it('S-3: 동기화 성공 시 동기화된 도구 수를 안내한다', async () => {
    server.use(
      http.post('*/api/v1/tool-catalog/sync', () =>
        HttpResponse.json({ synced_count: 3 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: 'Naver Search 도구 동기화' }));

    expect(await screen.findByText(/도구 3개를 동기화했습니다/)).toBeInTheDocument();
  });

  it('S-4: 동기화 실패(500) 시 사용자 문구로 안내한다 (§6.3)', async () => {
    server.use(
      http.post('*/api/v1/tool-catalog/sync', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: 'Naver Search 도구 동기화' }));

    expect(
      await screen.findByText(/도구 목록을 가져오지 못했습니다/),
    ).toBeInTheDocument();
  });

  it('S-5: 동기화 403 시 관리자 권한 안내를 표시한다', async () => {
    server.use(
      http.post('*/api/v1/tool-catalog/sync', () =>
        HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: 'Naver Search 도구 동기화' }));

    expect(await screen.findByText(/관리자 권한이 필요합니다/)).toBeInTheDocument();
  });

  it('S-6: 등록 응답 tool_sync.ok=false 면 실패 배너를 띄운다 (FR-10)', async () => {
    // 등록 성공 후 목록이 재조회되면 새 서버가 포함된다(실제 동작 반영)
    server.use(
      http.get('*/api/v1/mcp-registry', () =>
        HttpResponse.json({
          items: [
            {
              id: 'srv-new',
              user_id: '1',
              name: 'My SSE',
              description: '설명',
              endpoint: 'https://e.example.com/sse',
              transport: 'sse',
              input_schema: null,
              is_active: true,
              tool_id: 'mcp_srv-new',
              created_at: '2026-08-31T00:00:00Z',
              updated_at: '2026-08-31T00:00:00Z',
              auth_config: null,
              server_config: null,
              tool_sync: null,
            },
          ],
          total: 1,
        }),
      ),
      http.post('*/api/v1/mcp-registry', () =>
        HttpResponse.json(
          {
            id: 'srv-new',
            user_id: '1',
            name: 'My SSE',
            description: '설명',
            endpoint: 'https://e.example.com/sse',
            transport: 'sse',
            input_schema: null,
            is_active: true,
            tool_id: 'mcp_srv-new',
            created_at: '2026-08-31T00:00:00Z',
            updated_at: '2026-08-31T00:00:00Z',
            auth_config: null,
            server_config: null,
            tool_sync: {
              ok: false,
              synced_count: 0,
              error_hint: 'api_key 누락으로 인한 404 가능성이 높습니다',
            },
          },
          { status: 201 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('My SSE');

    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'My SSE');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '설명');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'https://e.example.com/sse',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(await screen.findByText(/도구 동기화 실패/)).toBeInTheDocument();
    expect(
      screen.getByText(/api_key 누락으로 인한 404 가능성이 높습니다/),
    ).toBeInTheDocument();
  });

  it('S-7: 등록 응답 tool_sync.ok=true 면 실패 배너를 띄우지 않는다', async () => {
    server.use(
      http.post('*/api/v1/mcp-registry', () =>
        HttpResponse.json(
          {
            id: 'srv-new',
            user_id: '1',
            name: 'My SSE',
            description: '설명',
            endpoint: 'https://e.example.com/sse',
            transport: 'sse',
            input_schema: null,
            is_active: true,
            tool_id: 'mcp_srv-new',
            created_at: '2026-08-31T00:00:00Z',
            updated_at: '2026-08-31T00:00:00Z',
            auth_config: null,
            server_config: null,
            tool_sync: { ok: true, synced_count: 2, error_hint: null },
          },
          { status: 201 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');

    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'My SSE');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '설명');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'https://e.example.com/sse',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() =>
      expect(screen.queryByPlaceholderText('예: Naver Search')).not.toBeInTheDocument(),
    );
    expect(screen.queryByText(/도구 동기화 실패/)).not.toBeInTheDocument();
  });
});

describe('AdminMcpServersPage — 기본 승인 필요 플래그 (approval-gate-phase2 D-07)', () => {
  const CHECKBOX = '이 서버의 도구는 기본으로 승인 필요';

  it('U-1: 등록 모달의 체크박스는 기본 꺼짐이다', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');
    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    expect(screen.getByRole('checkbox', { name: CHECKBOX })).not.toBeChecked();
    expect(screen.getByText(/새로 동기화되는 도구에만 적용/)).toBeInTheDocument();
  });

  it('U-2: 체크 후 등록하면 default_requires_approval=true 를 보낸다', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/mcp-registry', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 'srv-new' }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Naver Search');
    await user.click(screen.getByRole('button', { name: '서버 등록' }));
    await user.type(screen.getByPlaceholderText('예: Naver Search'), 'My Mail');
    await user.type(screen.getByPlaceholderText('서버에 대한 설명'), '메일');
    await user.type(
      screen.getByPlaceholderText('https://server.example.com/mcp'),
      'https://mail.example.com/sse',
    );
    await user.click(screen.getByRole('checkbox', { name: CHECKBOX }));
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({ default_requires_approval: true });
  });

  it('U-3: 플래그가 켜진 서버의 수정 모달은 체크된 채 열린다', async () => {
    server.use(
      http.get('*/api/v1/mcp-registry', () =>
        HttpResponse.json({
          items: [
            {
              id: 'srv-mail', user_id: '1', name: 'Mail MCP', description: '메일',
              endpoint: 'https://mail/sse', transport: 'sse', input_schema: null,
              is_active: true, default_requires_approval: true, tool_id: 'mcp_srv-mail',
              created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z',
              auth_config: null, server_config: null,
            },
          ],
          total: 1,
        }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Mail MCP');
    await user.click(screen.getByRole('button', { name: '수정' }));
    expect(screen.getByRole('checkbox', { name: CHECKBOX })).toBeChecked();
  });

  it('U-4: 수정에서 체크를 해제하고 저장하면 false 를 보낸다', async () => {
    let putBody: Record<string, unknown> | null = null;
    server.use(
      http.get('*/api/v1/mcp-registry', () =>
        HttpResponse.json({
          items: [
            {
              id: 'srv-mail', user_id: '1', name: 'Mail MCP', description: '메일',
              endpoint: 'https://mail/sse', transport: 'sse', input_schema: null,
              is_active: true, default_requires_approval: true, tool_id: 'mcp_srv-mail',
              created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z',
              auth_config: null, server_config: null,
            },
          ],
          total: 1,
        }),
      ),
      http.put('*/api/v1/mcp-registry/:id', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 'srv-mail', name: 'Mail MCP' });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Mail MCP');
    await user.click(screen.getByRole('button', { name: '수정' }));
    await user.click(screen.getByRole('checkbox', { name: CHECKBOX }));
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(putBody).not.toBeNull());
    expect(putBody).toMatchObject({ default_requires_approval: false });
  });

  it('U-5: 목록에서 플래그가 켜진 서버에만 "승인 기본" 뱃지가 보인다', async () => {
    server.use(
      http.get('*/api/v1/mcp-registry', () =>
        HttpResponse.json({
          items: [
            {
              id: 'a', user_id: '1', name: 'Mail MCP', description: '메일',
              endpoint: 'https://mail/sse', transport: 'sse', input_schema: null,
              is_active: true, default_requires_approval: true, tool_id: 'mcp_a',
              created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z',
              auth_config: null, server_config: null,
            },
            {
              id: 'b', user_id: '1', name: 'Search MCP', description: '검색',
              endpoint: 'https://s/sse', transport: 'sse', input_schema: null,
              is_active: true, default_requires_approval: false, tool_id: 'mcp_b',
              created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z',
              auth_config: null, server_config: null,
            },
          ],
          total: 2,
        }),
      ),
    );
    renderPage();
    await screen.findByText('Search MCP');
    expect(screen.getAllByText('승인 기본')).toHaveLength(1);
  });
});
