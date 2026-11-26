// stock-analysis-agents §9.1 · Plan SC-6 — '시장 분석' 메뉴는 GET /access 의 can_view 일 때만 보인다.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import {
  MA_ACCESS_NONE,
  MA_ACCESS_VIEWER,
} from '@/__tests__/mocks/marketAnalysisMocks';
import AppSidebar from './AppSidebar';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const LocationDisplay = () => <div data-testid="location">{useLocation().pathname}</div>;

const renderSidebar = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/chatpage']}>
        <AppSidebar agents={[]} selectedAgentId={null} onSelectAgent={vi.fn()} />
        <Routes>
          <Route path="*" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe('AppSidebar — 시장 분석 메뉴', () => {
  it('보기 권한이 있으면 메뉴가 보이고 누르면 이동한다', async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () => HttpResponse.json(MA_ACCESS_VIEWER)),
    );
    renderSidebar();
    await user.click(await screen.findByRole('button', { name: '시장 분석' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/market-analysis');
  });

  it('권한이 없거나 모듈이 꺼져 있으면(404) 메뉴가 없다', async () => {
    let calls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () => {
        calls += 1;
        return HttpResponse.json(MA_ACCESS_NONE);
      }),
    );
    const { unmount } = renderSidebar();
    await waitFor(() => expect(calls).toBe(1));
    expect(screen.queryByRole('button', { name: '시장 분석' })).not.toBeInTheDocument();
    unmount();

    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Not Found' }, { status: 404 });
      }),
    );
    renderSidebar();
    await waitFor(() => expect(calls).toBe(2));
    expect(screen.queryByRole('button', { name: '시장 분석' })).not.toBeInTheDocument();
  });
});
