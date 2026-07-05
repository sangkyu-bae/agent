import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Dropdown, { type DropdownOption } from './Dropdown';

const OPTIONS: DropdownOption[] = [
  { value: 'a', label: 'Apple' },
  { value: 'b', label: 'Banana' },
  { value: 'c', label: 'Cherry', disabled: true },
  { value: 'd', label: 'Durian' },
];

const setup = (props: Partial<React.ComponentProps<typeof Dropdown>> = {}) => {
  const onChange = vi.fn();
  render(
    <Dropdown value="a" onChange={onChange} options={OPTIONS} ariaLabel="과일" {...props} />,
  );
  return { onChange };
};

describe('Dropdown', () => {
  it('트리거 클릭 시 패널이 열리고 옵션이 보인다', async () => {
    setup();
    expect(screen.queryByRole('listbox')).toBeNull();
    await userEvent.click(screen.getByRole('combobox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Banana/ })).toBeInTheDocument();
  });

  it('옵션 클릭 시 onChange가 value로 호출되고 패널이 닫힌다', async () => {
    const { onChange } = setup();
    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(screen.getByRole('option', { name: /Banana/ }));
    expect(onChange).toHaveBeenCalledWith('b');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('선택된 옵션에 aria-selected가 표시된다', async () => {
    setup({ value: 'd' });
    await userEvent.click(screen.getByRole('combobox'));
    const selected = screen.getByRole('option', { name: /Durian/ });
    expect(selected).toHaveAttribute('aria-selected', 'true');
  });

  it('disabled 옵션은 선택되지 않는다', async () => {
    const { onChange } = setup();
    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(screen.getByRole('option', { name: /Cherry/ }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('키보드 ArrowDown + Enter로 선택한다 (disabled 건너뜀)', async () => {
    const { onChange } = setup({ value: 'b' });
    const trigger = screen.getByRole('combobox');
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}'); // open (active=b)
    await userEvent.keyboard('{ArrowDown}'); // c는 disabled → d로
    await userEvent.keyboard('{Enter}');
    expect(onChange).toHaveBeenCalledWith('d');
  });

  it('열렸을 때 활성 옵션을 aria-activedescendant로 가리킨다', async () => {
    setup();
    const trigger = screen.getByRole('combobox');
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}'); // open
    const activeId = trigger.getAttribute('aria-activedescendant');
    expect(activeId).toBeTruthy();
    const activeOption = document.getElementById(activeId!);
    expect(activeOption).toHaveAttribute('role', 'option');
  });

  it('Escape로 닫힌다', async () => {
    setup();
    await userEvent.click(screen.getByRole('combobox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('placeholder는 미선택(빈 값)일 때 표시된다', () => {
    setup({ value: '', placeholder: '전체' });
    expect(screen.getByRole('combobox')).toHaveTextContent('전체');
  });

  it('isLoading일 때 combobox 대신 skeleton을 렌더한다', () => {
    setup({ isLoading: true });
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  describe('model variant', () => {
    const MODELS: DropdownOption[] = [
      { value: 'm1', label: 'anthropic:claude-haiku-4-5' },
      { value: 'm2', label: 'azure:gpt-4.1', badge: 'API 키 미등록' },
      { value: 'm3', label: 'azure:gpt-4.1-mini', badge: 'API 키 미등록' },
    ];

    it('검색어로 옵션을 필터링한다', async () => {
      const onChange = vi.fn();
      render(<Dropdown value="m1" onChange={onChange} options={MODELS} variant="model" ariaLabel="모델" />);
      await userEvent.click(screen.getByRole('combobox'));
      const search = screen.getByLabelText('검색');
      await userEvent.type(search, 'haiku');
      const list = screen.getByRole('listbox');
      expect(within(list).getByRole('option', { name: /haiku/ })).toBeInTheDocument();
      expect(within(list).queryByRole('option', { name: /gpt/ })).toBeNull();
    });

    it('검색 결과가 없으면 emptyText를 표시한다', async () => {
      const onChange = vi.fn();
      render(
        <Dropdown value="m1" onChange={onChange} options={MODELS} variant="model" emptyText="결과 없음" ariaLabel="모델" />,
      );
      await userEvent.click(screen.getByRole('combobox'));
      await userEvent.type(screen.getByLabelText('검색'), 'zzzz');
      expect(screen.getByText('결과 없음')).toBeInTheDocument();
    });

    it('badge가 옵션에 렌더된다', async () => {
      const onChange = vi.fn();
      render(<Dropdown value="m1" onChange={onChange} options={MODELS} variant="model" ariaLabel="모델" />);
      await userEvent.click(screen.getByRole('combobox'));
      expect(screen.getAllByText('[API 키 미등록]').length).toBeGreaterThan(0);
    });
  });
});
