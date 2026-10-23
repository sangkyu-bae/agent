import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Tabs from './Tabs';

const items = [
  { key: 'all', label: '전체', count: 12 },
  { key: 'mine', label: '내 것' },
  { key: 'off', label: '비활성', disabled: true },
  { key: 'dept', label: '부서' },
];

describe('Tabs', () => {
  it('tablist/tab 역할과 aria-selected를 렌더링한다', () => {
    render(<Tabs items={items} value="all" onChange={() => {}} aria-label="필터" />);
    expect(screen.getByRole('tablist', { name: '필터' })).toBeInTheDocument();
    const all = screen.getByRole('tab', { name: /전체/ });
    expect(all).toHaveAttribute('aria-selected', 'true');
    expect(all).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: '내 것' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '비활성' })).toBeDisabled();
  });

  it('클릭 시 onChange가 key로 호출된다', async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} value="all" onChange={onChange} aria-label="필터" />);
    await userEvent.click(screen.getByRole('tab', { name: '내 것' }));
    expect(onChange).toHaveBeenCalledWith('mine');
  });

  it('화살표 키로 이동하면 disabled 탭을 건너뛰고 포커스와 선택이 이동한다', async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} value="mine" onChange={onChange} aria-label="필터" />);
    const mine = screen.getByRole('tab', { name: '내 것' });
    mine.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('dept');
    expect(screen.getByRole('tab', { name: '부서' })).toHaveFocus();

    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('all');

    await userEvent.keyboard('{End}');
    expect(onChange).toHaveBeenLastCalledWith('dept');
    await userEvent.keyboard('{Home}');
    expect(onChange).toHaveBeenLastCalledWith('all');
  });
});
