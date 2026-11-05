// agent-token-limit Design D12 — 반복·토큰 한도가 공유하는 숫자 입력 (clamp·복원)
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import LimitNumberField from './LimitNumberField';

const renderField = (value = 50000) => {
  const onChange = vi.fn();
  render(
    <LimitNumberField
      id="token-limit-input"
      label="토큰 예산"
      value={value}
      min={8000}
      max={500000}
      defaultValue={50000}
      onChange={onChange}
    />,
  );
  return { onChange };
};

const getInput = () => screen.getByRole('spinbutton', { name: '토큰 예산' });

describe('LimitNumberField', () => {
  it('현재 값·범위·기본값 안내를 표시한다', () => {
    renderField(50000);
    expect(getInput()).toHaveValue(50000);
    expect(screen.getByText(/8000 - 500000/)).toBeInTheDocument();
    expect(screen.getByText(/기본값: 50000/)).toBeInTheDocument();
  });

  it('범위 내 값은 blur 시 그대로 확정한다', () => {
    const { onChange } = renderField();
    fireEvent.change(getInput(), { target: { value: '120000' } });
    fireEvent.blur(getInput());
    expect(onChange).toHaveBeenCalledWith(120000);
  });

  it('하한 미만은 min, 상한 초과는 max로 clamp한다', () => {
    const { onChange } = renderField();
    fireEvent.change(getInput(), { target: { value: '999' } });
    fireEvent.blur(getInput());
    expect(onChange).toHaveBeenLastCalledWith(8000);
    expect(getInput()).toHaveValue(8000);

    fireEvent.change(getInput(), { target: { value: '500001' } });
    fireEvent.blur(getInput());
    expect(onChange).toHaveBeenLastCalledWith(500000);
  });

  it('비숫자는 Enter 시 이전 값으로 복원하고 onChange를 호출하지 않는다', () => {
    const { onChange } = renderField(77000);
    fireEvent.change(getInput(), { target: { value: 'abc' } });
    fireEvent.keyDown(getInput(), { key: 'Enter' });
    expect(onChange).not.toHaveBeenCalled();
    expect(getInput()).toHaveValue(77000);
  });

  it('상위 값이 바뀌면 입력도 동기화된다', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <LimitNumberField
        id="x" label="토큰 예산" value={50000} min={8000} max={500000}
        defaultValue={50000} onChange={onChange}
      />,
    );
    rerender(
      <LimitNumberField
        id="x" label="토큰 예산" value={90000} min={8000} max={500000}
        defaultValue={50000} onChange={onChange}
      />,
    );
    expect(getInput()).toHaveValue(90000);
  });

  it('복원 버튼은 defaultValue로 onChange를 호출한다', async () => {
    const user = userEvent.setup();
    const { onChange } = renderField(90000);
    await user.click(screen.getByRole('button', { name: '기본값으로 복원' }));
    expect(onChange).toHaveBeenCalledWith(50000);
  });
});
