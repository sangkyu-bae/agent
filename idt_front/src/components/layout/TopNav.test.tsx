import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TopNav from './TopNav';
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

const renderTopNav = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/chatpage']}>
        <TopNav />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false });
});

describe('TopNav — 관리 메뉴', () => {
  it('T1: 관리자일 때 "관리" 메뉴를 노출한다', () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    renderTopNav();
    expect(screen.getByRole('button', { name: /관리/ })).toBeInTheDocument();
  });

  it('T2: "관리" 드롭다운에 관리자 페이지가 모두 노출된다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByRole('button', { name: /^관리$/ }));

    expect(screen.getByText('사용자 관리')).toBeInTheDocument();
    expect(screen.getByText('부서 관리')).toBeInTheDocument();
    expect(screen.getByText('RAGAS 평가')).toBeInTheDocument();
    expect(screen.getByText('Agent Run 관측')).toBeInTheDocument();
    expect(screen.getByText('위키 관리')).toBeInTheDocument();
  });

  it('T4: "관리" 드롭다운에 그룹 헤더 4개가 노출된다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByRole('button', { name: /^관리$/ }));

    expect(screen.getByText('관측')).toBeInTheDocument();
    expect(screen.getByText('조직 관리')).toBeInTheDocument();
    expect(screen.getByText('문서·품질')).toBeInTheDocument();
    expect(screen.getByText('에이전트 리소스')).toBeInTheDocument();
  });

  it('T3: 일반 사용자일 때 "관리" 메뉴를 노출하지 않는다', () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderTopNav();
    expect(screen.queryByRole('button', { name: /^관리$/ })).not.toBeInTheDocument();
  });
});

describe('TopNav — 에이전트 메뉴', () => {
  it('에이전트 드롭다운에 "유틸리티" 항목을 노출한다 (utility-page)', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByRole('button', { name: /^에이전트$/ }));

    expect(screen.getByText('유틸리티')).toBeInTheDocument();
    expect(screen.queryByText('도구 연결')).not.toBeInTheDocument();
  });
});
