// builtin-middleware D10: 관리자 미들웨어 관리 페이지 테스트.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeAll, afterEach, afterAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import AdminMiddlewarePage from '@/pages/AdminMiddlewarePage';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CATALOG = {
  middlewares: [
    {
      middleware_type: 'model_retry',
      name: 'LLM 재시도',
      description: 'LLM 호출 실패 시 지수 백오프로 자동 재시도합니다.',
      is_builtin: true,
      is_enforced: false,
      default_config: { max_retries: 3, backoff_factor: 2.0, initial_delay: 1.0 },
      is_active: true,
      sort_order: 10,
    },
    {
      middleware_type: 'model_call_limit',
      name: '모델 호출 상한',
      description: 'run당 LLM 호출 횟수를 제한합니다.',
      is_builtin: false,
      is_enforced: false,
      default_config: { run_limit: 10, exit_behavior: 'end' },
      is_active: true,
      sort_order: 40,
    },
  ],
};

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminMiddlewarePage />
    </QueryClientProvider>,
  );
};

const mockCatalog = () =>
  server.use(
    http.get(`*${API_ENDPOINTS.MIDDLEWARE_CATALOG}`, () =>
      HttpResponse.json(CATALOG),
    ),
  );

describe('AdminMiddlewarePage', () => {
  it('카탈로그 목록을 렌더링한다', async () => {
    mockCatalog();
    renderPage();
    expect(await screen.findByText('LLM 재시도')).toBeInTheDocument();
    expect(screen.getByText('모델 호출 상한')).toBeInTheDocument();
    expect(
      screen.getByRole('switch', { name: 'LLM 재시도 빌트인' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(
      screen.getByRole('switch', { name: 'LLM 재시도 강제' }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  it('강제 토글 시 PATCH 본문에 is_enforced만 전송한다', async () => {
    mockCatalog();
    let captured: unknown = null;
    server.use(
      http.patch(
        `*${API_ENDPOINTS.MIDDLEWARE_CATALOG_DETAIL('model_call_limit')}`,
        async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json({
            ...CATALOG.middlewares[1],
            is_enforced: true,
          });
        },
      ),
    );
    renderPage();
    fireEvent.click(
      await screen.findByRole('switch', { name: '모델 호출 상한 강제' }),
    );
    await waitFor(() => expect(captured).toEqual({ is_enforced: true }));
  });

  it('설정 편집 저장 시 default_config를 전송한다', async () => {
    mockCatalog();
    let captured: unknown = null;
    server.use(
      http.patch(
        `*${API_ENDPOINTS.MIDDLEWARE_CATALOG_DETAIL('model_retry')}`,
        async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json(CATALOG.middlewares[0]);
        },
      ),
    );
    renderPage();
    await screen.findByText('LLM 재시도');
    fireEvent.click(screen.getAllByRole('button', { name: '편집' })[0]);

    const input = screen.getByRole('spinbutton', {
      name: 'LLM 재시도 최대 재시도',
    });
    fireEvent.change(input, { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '설정 저장' }));

    await waitFor(() =>
      expect(captured).toEqual({
        default_config: { max_retries: 5, backoff_factor: 2.0, initial_delay: 1.0 },
      }),
    );
  });

  it('토글 실패 시 에러 메시지를 표시한다', async () => {
    mockCatalog();
    server.use(
      http.patch(
        `*${API_ENDPOINTS.MIDDLEWARE_CATALOG_DETAIL('model_retry')}`,
        () => HttpResponse.json({ detail: '권한 없음' }, { status: 403 }),
      ),
    );
    renderPage();
    fireEvent.click(
      await screen.findByRole('switch', { name: 'LLM 재시도 빌트인' }),
    );
    expect(await screen.findByText(/권한 없음|실패/)).toBeInTheDocument();
  });
});
