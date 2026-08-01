// mutation-pending-guard: 공통 대기 버튼 — isPending disable·스피너·클릭 가드.
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import LoadingButton from './LoadingButton';

describe('LoadingButton', () => {
  it('L1: idle 상태에서 children을 표시하고 클릭 시 onClick이 호출된다', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <LoadingButton isPending={false} onClick={onClick}>
        저장
      </LoadingButton>,
    );
    const button = screen.getByRole('button', { name: '저장' });
    expect(button).not.toBeDisabled();
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('L2: pending 상태에서 disabled + 스피너 + pendingText가 표시된다', () => {
    render(
      <LoadingButton isPending pendingText="저장 중…">
        저장
      </LoadingButton>,
    );
    const button = screen.getByRole('button', { name: '저장 중…' });
    expect(button).toBeDisabled();
    expect(button.querySelector('svg.animate-spin')).toBeInTheDocument();
    expect(screen.queryByText('저장')).not.toBeInTheDocument();
  });

  it('L3: pending 상태에서 클릭 이벤트를 강제 발화해도 onClick이 호출되지 않는다', () => {
    const onClick = vi.fn();
    render(
      <LoadingButton isPending onClick={onClick} pendingText="저장 중…">
        저장
      </LoadingButton>,
    );
    // disabled 우회 경로(프로그래매틱 click) 이중 방어 검증
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('L4: pendingText 미지정 시 pending 중에도 children이 유지된다', () => {
    render(<LoadingButton isPending>저장</LoadingButton>);
    const button = screen.getByRole('button', { name: '저장' });
    expect(button).toBeDisabled();
    expect(button.querySelector('svg.animate-spin')).toBeInTheDocument();
  });

  it('L5: isPending=false여도 자체 disabled prop이 우선 적용된다', () => {
    render(
      <LoadingButton isPending={false} disabled>
        저장
      </LoadingButton>,
    );
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });
});
