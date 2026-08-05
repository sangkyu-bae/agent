import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import AdminSectionTabs from './AdminSectionTabs';
import { ADMIN_NAV_GROUPS } from '@/constants/adminNav';

const orgGroup = ADMIN_NAV_GROUPS.find((g) => g.key === 'org')!;
const observabilityGroup = ADMIN_NAV_GROUPS.find((g) => g.key === 'observability')!;

const LocationDisplay = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

const renderTabs = (group: typeof orgGroup, initialPath: string) =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AdminSectionTabs group={group} />
      <Routes>
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>,
  );

describe('AdminSectionTabs', () => {
  it('TB1: 그룹 items가 순서대로 탭으로 렌더링된다', () => {
    renderTabs(orgGroup, '/admin/users');
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['사용자 관리', '부서 관리']);
  });

  it('TB2: 현재 경로에 해당하는 탭이 aria-selected=true다', () => {
    renderTabs(orgGroup, '/admin/departments');
    expect(screen.getByRole('tab', { name: '부서 관리' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: '사용자 관리' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });

  it('TB3: 탭 클릭 시 해당 경로로 이동한다', async () => {
    const user = userEvent.setup();
    renderTabs(orgGroup, '/admin/users');

    await user.click(screen.getByRole('tab', { name: '부서 관리' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/admin/departments');
  });

  it('TB4: 하위 상세 경로에서도 소속 탭이 활성이다', () => {
    renderTabs(observabilityGroup, '/admin/agent-runs/run-1');
    expect(screen.getByRole('tab', { name: 'Agent Run 관측' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});
