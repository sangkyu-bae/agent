import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppSidebar from './AppSidebar';
import { useAuthStore } from '@/store/authStore';
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

  it('A4: "관리자" 클릭 시 /admin/users로 이동한다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByRole('button', { name: '관리자' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/admin/users');
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
