import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminLayout from './AdminLayout';
import { useAuthStore } from '@/store/authStore';
import type { User } from '@/types/auth';

const adminUser: User = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  status: 'approved',
};

const LocationDisplay = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

const renderLayout = (initialPath: string) => {
  useAuthStore.setState({ user: adminUser, isAuthenticated: true });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="*" element={<LocationDisplay />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false });
});

describe('AdminLayout — 그룹 사이드바 + 2차 탭', () => {
  it('AL1: 사이드바에 그룹 4개만 노출되고 개별 항목은 노출되지 않는다', () => {
    renderLayout('/admin/users');
    const sidebar = screen.getByRole('navigation', { name: '관리 메뉴' });
    expect(within(sidebar).getByRole('button', { name: '관측' })).toBeInTheDocument();
    expect(within(sidebar).getByRole('button', { name: '조직 관리' })).toBeInTheDocument();
    expect(within(sidebar).getByRole('button', { name: '문서·품질' })).toBeInTheDocument();
    expect(
      within(sidebar).getByRole('button', { name: '에이전트 리소스' }),
    ).toBeInTheDocument();
    // 개별 항목은 사이드바가 아닌 탭 바에만 존재
    expect(within(sidebar).queryByText('부서 관리')).not.toBeInTheDocument();
    expect(within(sidebar).queryByText('운영 대시보드')).not.toBeInTheDocument();
  });

  it('AL2: 현재 경로 소속 그룹의 탭 바가 렌더링된다', () => {
    renderLayout('/admin/users');
    const tablist = screen.getByRole('tablist', { name: '조직 관리 하위 메뉴' });
    expect(within(tablist).getByRole('tab', { name: '사용자 관리' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(within(tablist).getByRole('tab', { name: '부서 관리' })).toBeInTheDocument();
  });

  it('AL3: 그룹 버튼 클릭 시 그룹 첫 탭 경로로 이동한다', async () => {
    const user = userEvent.setup();
    renderLayout('/admin/users');

    await user.click(screen.getByRole('button', { name: '문서·품질' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/admin/chunking-profiles');
    expect(
      screen.getByRole('tablist', { name: '문서·품질 하위 메뉴' }),
    ).toBeInTheDocument();
  });

  it('AL4: 하위 상세 경로에서도 소속 그룹·탭이 활성이다', () => {
    renderLayout('/admin/agent-runs/run-1');
    expect(screen.getByRole('tablist', { name: '관측 하위 메뉴' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Agent Run 관측' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
