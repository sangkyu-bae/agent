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
