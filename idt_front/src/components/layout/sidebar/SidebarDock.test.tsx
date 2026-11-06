import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import SidebarDock from './SidebarDock';
import { useAuthStore } from '@/store/authStore';
import { ADMIN_ENTRY_PATH } from '@/constants/adminNav';
import type { User } from '@/types/auth';

const logoutMutate = vi.fn();
vi.mock('@/hooks/useAuth', () => ({
  useLogout: () => ({ mutate: logoutMutate, isPending: false }),
}));

const normalUser: User = { id: 2, email: 'user@test.com', role: 'user', status: 'approved' };
const adminUser: User = { id: 1, email: 'admin@test.com', role: 'admin', status: 'approved' };

const LocationDisplay = () => <div data-testid="location">{useLocation().pathname}</div>;

const renderDock = (path = '/chatpage', collapsed = false) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarDock collapsed={collapsed} />
      <Routes>
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>,
  );

const MENU = ['즐겨찾기', '역할설정', '리소스', '지식베이스', '환경설정'];

afterEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false });
  logoutMutate.mockReset();
});

describe('SidebarDock', () => {
  it('SD1: 일반 사용자는 메뉴 아이콘 5개를 이름으로 접근하고 관리자는 보이지 않는다', () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderDock();
    const nav = screen.getByRole('navigation', { name: '보조 메뉴' });
    MENU.forEach((label) => {
      const btn = screen.getByRole('button', { name: label });
      expect(nav).toContainElement(btn);
      expect(btn).toHaveAttribute('title', label);
    });
    expect(screen.queryByRole('button', { name: '관리자' })).not.toBeInTheDocument();
  });

  it('SD2: 관리자는 "관리자" 버튼이 추가되고 누르면 관리자 화면으로 이동한다', async () => {
    useAuthStore.setState({ user: adminUser, isAuthenticated: true });
    renderDock();
    await userEvent.click(screen.getByRole('button', { name: '관리자' }));
    expect(screen.getByTestId('location')).toHaveTextContent(ADMIN_ENTRY_PATH);
  });

  it('SD3: 지식베이스는 이동하고, 상세 라우트에서도 활성 표시된다', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    const { unmount } = renderDock();
    await userEvent.click(screen.getByRole('button', { name: '지식베이스' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/knowledge-bases');
    unmount();
    renderDock('/knowledge-bases/kb1');
    expect(screen.getByRole('button', { name: '지식베이스' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '리소스' })).not.toHaveAttribute('aria-current');
  });

  it('SD4: 사용자 이메일을 한 줄로 보여주고 로그아웃 버튼이 logout을 호출한다', async () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderDock();
    expect(screen.getAllByText('user@test.com')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(logoutMutate).toHaveBeenCalledTimes(1);
  });

  it('SD5: 접힌 레일에서도 메뉴 버튼은 이름을 유지하고 이메일은 숨긴다', () => {
    useAuthStore.setState({ user: normalUser, isAuthenticated: true });
    renderDock('/chatpage', true);
    MENU.forEach((label) => expect(screen.getByRole('button', { name: label })).toBeInTheDocument());
    expect(screen.queryByText('user@test.com')).not.toBeInTheDocument();
  });
});
