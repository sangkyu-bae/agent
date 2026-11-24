// firewall-admin-console module-3 — 메뉴 조건부 노출이 실제 레이아웃에 반영되는지 (Plan FR-16, SC-1).
// 사이드바(AdminLayout)와 상단 드롭다운(TopNav) 두 소비처를 함께 본다.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { FIREWALL_STATUS_DRY_RUN } from '@/__tests__/mocks/firewallMocks';
import { useAuthStore } from '@/store/authStore';
import type { User } from '@/types/auth';
import AdminLayout from './AdminLayout';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null, isAuthenticated: false });
});
afterAll(() => server.close());

const STATUS = '*/api/v1/admin/firewall/status';
const adminUser: User = { id: 1, email: 'admin@test.com', role: 'admin', status: 'approved' };

const LocationDisplay = () => <div data-testid="location">{useLocation().pathname}</div>;

const renderLayout = (path: string) => {
  useAuthStore.setState({ user: adminUser, isAuthenticated: true });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="*" element={<LocationDisplay />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

const sidebar = () => screen.getByRole('navigation', { name: '관리 메뉴' });
/** 사이드바 그룹 버튼 라벨 (목록 밖의 "메인으로 돌아가기" 버튼은 제외) */
const groupLabels = () =>
  within(within(sidebar()).getByRole('list'))
    .getAllByRole('button')
    .map((b) => b.textContent?.trim());

describe('관리자 메뉴 — 방화벽 조건부 노출', () => {
  it('백엔드 모듈이 켜져 있으면 사이드바와 드롭다운에 나타나고, 누르면 이동한다', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json(FIREWALL_STATUS_DRY_RUN)));
    const user = userEvent.setup();
    renderLayout('/admin/users');

    const group = await within(sidebar()).findByRole('button', { name: '보안 운영' });
    // 그룹 중 맨 뒤에 붙는다 (진입 경로 그룹 순서 불변)
    expect(groupLabels()).toEqual(['관측', '조직 관리', '문서·품질', '에이전트 리소스', '보안 운영']);

    await user.click(screen.getByRole('button', { name: /^관리$/ }));
    expect(screen.getByText('방화벽')).toBeInTheDocument();

    await user.click(group);
    expect(screen.getByTestId('location')).toHaveTextContent('/admin/firewall');
    // 2차 탭에 항목이 보인다
    expect(screen.getByRole('tab', { name: '방화벽' })).toHaveAttribute('aria-selected', 'true');
  });

  it('꺼져 있으면(404) 사이드바·드롭다운 어디에도 없다', async () => {
    let calls = 0;
    server.use(
      http.get(STATUS, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Not Found' }, { status: 404 });
      }),
    );
    const user = userEvent.setup();
    renderLayout('/admin/users');
    await waitFor(() => expect(calls).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 50));

    expect(within(sidebar()).queryByRole('button', { name: '보안 운영' })).not.toBeInTheDocument();
    expect(groupLabels()).toEqual(['관측', '조직 관리', '문서·품질', '에이전트 리소스']);
    await user.click(screen.getByRole('button', { name: /^관리$/ }));
    expect(screen.queryByText('방화벽')).not.toBeInTheDocument();
    // 사이드바와 상단 메뉴가 같은 쿼리를 공유한다 (요청 1회)
    expect(calls).toBe(1);
  });

  it('꺼져 있어도 직접 진입하면 2차 탭은 보인다 (페이지가 안내를 보여 준다)', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
    renderLayout('/admin/firewall');
    expect(await screen.findByRole('tab', { name: '방화벽' })).toBeInTheDocument();
    expect(within(sidebar()).queryByRole('button', { name: '보안 운영' })).not.toBeInTheDocument();
  });
});
