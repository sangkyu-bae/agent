import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppSidebar from './AppSidebar';
import { useAuthStore } from '@/store/authStore';
import { useLayoutStore } from '@/store/layoutStore';
import type { User } from '@/types/auth';

const adminUser: User = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  status: 'approved',
};

const normalUser: User = {
  id: 2,
  email: 'user@test.com',
  role: 'user',
  status: 'approved',
};

const LocationDisplay = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

const renderSidebar = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/chatpage']}>
        <AppSidebar agents={[]} selectedAgentId={null} onSelectAgent={vi.fn()} />
        <Routes>
          <Route path="*" element={<LocationDisplay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false });
  useLayoutStore.setState({ isSidebarCollapsed: false });
});

// ui-redesign-chat §5.5: 접기 레일 — 접혀도 모든 항목은 aria-label로 접근 가능한 이름을 유지한다
describe('AppSidebar — 접기 레일', () => {
  it('C1: 토글 버튼이 "사이드바 접기"→"사이드바 펼치기"로 바뀌고 스토어가 갱신된다', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderSidebar();

    const toggle = screen.getByRole('button', { name: '사이드바 접기' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);

    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(true);
    expect(screen.getByRole('button', { name: '사이드바 펼치기' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('C2: 접힌 상태에서도 내비 버튼이 이름으로 접근 가능하고 클릭 시 이동한다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    useLayoutStore.setState({ isSidebarCollapsed: true });
    const user = userEvent.setup();
    renderSidebar();

    expect(screen.getByRole('complementary', { name: '주 메뉴' })).toHaveAttribute('data-collapsed', 'true');
    expect(screen.queryByText('에이전트 스토어')).not.toBeInTheDocument();
    const store = screen.getByRole('button', { name: '에이전트 스토어' });
    expect(store).toHaveAttribute('title', '에이전트 스토어');
    await user.click(store);
    expect(screen.getByTestId('location')).toHaveTextContent('/agent-store');
    expect(screen.getByRole('button', { name: '관리자' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '로그아웃' })).toBeInTheDocument();
  });

  it('C3: 접힌 상태의 "에이전트 목록" 버튼은 사이드바를 펼친다', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    useLayoutStore.setState({ isSidebarCollapsed: true });
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: '에이전트 목록' }));
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(false);
    expect(screen.getByText('에이전트 스토어')).toBeInTheDocument();
  });
});

describe('AppSidebar — 관리자 진입 메뉴', () => {
  it('A1: 관리자일 때 "관리자" 메뉴를 노출한다', () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    renderSidebar();
    expect(screen.getByRole('button', { name: '관리자' })).toBeInTheDocument();
  });

  it('A2: 일반 사용자일 때 "관리자" 메뉴를 노출하지 않는다', () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderSidebar();
    expect(screen.queryByRole('button', { name: '관리자' })).not.toBeInTheDocument();
  });

  it('A3: user가 없으면 "관리자" 메뉴를 노출하지 않는다', () => {
    useAuthStore.setState({ user: null, isAuthenticated: false });
    renderSidebar();
    expect(screen.queryByRole('button', { name: '관리자' })).not.toBeInTheDocument();
  });

  it('A4: "관리자" 클릭 시 /admin/dashboard로 이동한다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: '관리자' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/admin/dashboard');
  });
});

describe('AppSidebar — 에이전트 스토어 진입 메뉴', () => {
  it('S1: "에이전트 스토어" 메뉴를 노출한다', () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderSidebar();
    expect(screen.getByRole('button', { name: '에이전트 스토어' })).toBeInTheDocument();
  });

  it('S2: "에이전트 스토어" 클릭 시 /agent-store로 이동한다', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: '에이전트 스토어' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/agent-store');
  });
});
