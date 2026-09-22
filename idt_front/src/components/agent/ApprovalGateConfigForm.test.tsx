// approval-gate Design §5.4 — 에이전트 설정 승인 게이트 섹션
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ApprovalGateConfigForm from './ApprovalGateConfigForm';
import { DEFAULT_APPROVAL_GATE_CONFIG } from '@/types/approval';

const setup = (over = {}, enforced = false) => {
  const onChange = vi.fn();
  render(
    <ApprovalGateConfigForm
      value={{ ...DEFAULT_APPROVAL_GATE_CONFIG, ...over }}
      enforced={enforced}
      onChange={onChange}
    />,
  );
  return onChange;
};

describe('ApprovalGateConfigForm — 토글', () => {
  it('mode=always 면 켜짐', () => {
    setup({ mode: 'always' });
    expect(screen.getByLabelText('승인 게이트 사용')).toBeChecked();
  });

  it('mode=off 면 꺼짐', () => {
    setup({ mode: 'off' });
    expect(screen.getByLabelText('승인 게이트 사용')).not.toBeChecked();
  });

  it('끄면 mode=off 로 전달한다', async () => {
    const onChange = setup({ mode: 'always' });
    await userEvent.click(screen.getByLabelText('승인 게이트 사용'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'off' }),
    );
  });
});

describe('ApprovalGateConfigForm — 관리자 강제', () => {
  it('enforced 면 강제 뱃지를 보여준다', () => {
    setup({}, true);
    expect(screen.getByText('관리자 강제')).toBeInTheDocument();
  });

  it('enforced 면 토글이 비활성이다', () => {
    setup({}, true);
    expect(screen.getByLabelText('승인 게이트 사용')).toBeDisabled();
  });

  it('enforced 면 mode=off 여도 켜진 것으로 보인다', () => {
    // 백엔드 FR-20 — 강제는 mode=off 를 이긴다. 화면이 실제 동작과 달라
    // 보이면 사용자가 꺼진 줄 안다.
    setup({ mode: 'off' }, true);
    expect(screen.getByLabelText('승인 게이트 사용')).toBeChecked();
  });
});

describe('ApprovalGateConfigForm — 집행 시각', () => {
  it('cron 을 입력하면 그대로 전달한다', async () => {
    const onChange = setup();
    await userEvent.type(screen.getByLabelText('집행 시각 cron'), '0');
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ execute_after: '0' }),
    );
  });

  it('비우면 null 로 전달한다 (즉시 집행)', async () => {
    const onChange = setup({ execute_after: '0 0 * * *' });
    await userEvent.clear(screen.getByLabelText('집행 시각 cron'));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ execute_after: null }),
    );
  });

  it('게이트가 꺼져 있으면 비활성이다', () => {
    setup({ mode: 'off' });
    expect(screen.getByLabelText('집행 시각 cron')).toBeDisabled();
  });
});

describe('ApprovalGateConfigForm — 만료 시간', () => {
  it('현재 값을 보여준다', () => {
    setup({ expires_hours: 24 });
    expect(screen.getByLabelText('만료 시간')).toHaveValue(24);
  });

  it('상하한이 입력 속성에 걸려 있다', () => {
    setup();
    const input = screen.getByLabelText('만료 시간');
    expect(input).toHaveAttribute('min', '1');
    expect(input).toHaveAttribute('max', '720');
  });
});

describe('ApprovalGateConfigForm — cron 공백 입력 (Check 에서 발견된 회귀)', () => {
  it('공백이 들어간 cron 을 그대로 입력할 수 있다', async () => {
    // 이전 구현은 키 입력마다 trim 해서 '30 23 * * *' 가 '3023***' 가 됐다.
    // 제어 컴포넌트라 부모가 value 를 다시 내려줘야 누적되므로 상태를 둔다.
    const { useState } = await import('react');
    const Harness = () => {
      const [v, setV] = useState({ ...DEFAULT_APPROVAL_GATE_CONFIG });
      return <ApprovalGateConfigForm value={v} onChange={setV} />;
    };
    render(<Harness />);
    const input = screen.getByLabelText('집행 시각 cron');
    await userEvent.type(input, '30 23 * * *');
    expect(input).toHaveValue('30 23 * * *');
  });
});
