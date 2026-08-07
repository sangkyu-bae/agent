// agent-settings-tab Design §5-1 (+ agent-webhook: Webhook 섹션 실기능 교체)
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import SettingsPanel from './SettingsPanel';

// Webhook 실기능(서버 상태 훅)은 WebhookSection.test.tsx에서 검증 —
// 여기서는 배선(렌더 + agentId 전달)만 단언한다.
vi.mock('./WebhookSection', () => ({
  default: ({ agentId }: { agentId: string | null }) => (
    <section>
      <h3>Webhook</h3>
      <div data-testid="webhook-section" data-agent-id={agentId ?? ''} />
    </section>
  ),
}));

const renderPanel = (maxIterations = 25, agentId: string | null = null) => {
  const onMaxIterationsChange = vi.fn();
  render(
    <SettingsPanel
      agentId={agentId}
      maxIterations={maxIterations}
      onMaxIterationsChange={onMaxIterationsChange}
    />,
  );
  return { onMaxIterationsChange };
};

const getInput = () =>
  screen.getByRole('spinbutton', { name: '최대 반복 횟수' });

describe('SettingsPanel — 렌더', () => {
  it('4개 섹션 제목을 노출하고 자체 저장 버튼은 없다', () => {
    renderPanel();
    expect(screen.getByText('Recursion Limit')).toBeInTheDocument();
    expect(screen.getByText('MCP 서버')).toBeInTheDocument();
    expect(screen.getByText('Webhook')).toBeInTheDocument();
    expect(screen.getByText('Telegram 연동')).toBeInTheDocument();
    // 저장은 StudioHeader 통합 (Design D2) — 탭 내 저장 버튼 부재
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
  });

  it('현재 값과 범위·기본값 안내를 표시한다', () => {
    renderPanel(25);
    expect(getInput()).toHaveValue(25);
    expect(screen.getByText(/10 - 1000/)).toBeInTheDocument();
    expect(screen.getByText(/기본값: 25/)).toBeInTheDocument();
  });
});

describe('SettingsPanel — Recursion Limit 입력 (D2·D3 clamp)', () => {
  it('범위 내 값 입력 후 blur 시 onChange로 확정한다', () => {
    const { onMaxIterationsChange } = renderPanel(25);
    fireEvent.change(getInput(), { target: { value: '500' } });
    fireEvent.blur(getInput());
    expect(onMaxIterationsChange).toHaveBeenCalledTimes(1);
    expect(onMaxIterationsChange).toHaveBeenCalledWith(500);
  });

  it('상한 초과는 1000으로, 하한 미만은 10으로 clamp한다', () => {
    const { onMaxIterationsChange } = renderPanel(25);
    fireEvent.change(getInput(), { target: { value: '1001' } });
    fireEvent.blur(getInput());
    expect(onMaxIterationsChange).toHaveBeenLastCalledWith(1000);

    fireEvent.change(getInput(), { target: { value: '9' } });
    fireEvent.blur(getInput());
    expect(onMaxIterationsChange).toHaveBeenLastCalledWith(10);
  });

  it('빈 값·비숫자는 기존 값으로 복원하고 onChange를 호출하지 않는다', () => {
    const { onMaxIterationsChange } = renderPanel(25);
    fireEvent.change(getInput(), { target: { value: '' } });
    fireEvent.blur(getInput());
    expect(onMaxIterationsChange).not.toHaveBeenCalled();
    expect(getInput()).toHaveValue(25);
  });

  it('Enter로도 값을 확정한다', () => {
    const { onMaxIterationsChange } = renderPanel(25);
    fireEvent.change(getInput(), { target: { value: '300' } });
    fireEvent.keyDown(getInput(), { key: 'Enter' });
    expect(onMaxIterationsChange).toHaveBeenCalledWith(300);
  });

  it('복원 버튼 클릭 시 기본값 25로 되돌린다', async () => {
    const user = userEvent.setup();
    const { onMaxIterationsChange } = renderPanel(500);
    await user.click(screen.getByRole('button', { name: '기본값으로 복원' }));
    expect(onMaxIterationsChange).toHaveBeenCalledWith(25);
  });
});

describe('SettingsPanel — 연동 스텁 (agent-webhook 이후 MCP·Telegram 2종)', () => {
  it('스텁 토글 2개는 모두 disabled + 준비중 + off 상태다', () => {
    renderPanel();
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(2);
    for (const sw of switches) {
      expect(sw).toBeDisabled();
      expect(sw).toHaveAttribute('title', '준비중');
      expect(sw).toHaveAttribute('aria-checked', 'false');
    }
  });

  it('Telegram 섹션은 연결되지 않음·비활성화됨 상태를 표기한다', () => {
    renderPanel();
    expect(screen.getByText('연결되지 않음')).toBeInTheDocument();
    expect(screen.getByText('비활성화됨')).toBeInTheDocument();
  });
});

describe('SettingsPanel — Webhook 섹션 배선 (agent-webhook)', () => {
  it('WebhookSection에 agentId를 전달한다 (edit 모드)', () => {
    renderPanel(25, 'agent-1');
    expect(screen.getByTestId('webhook-section')).toHaveAttribute(
      'data-agent-id',
      'agent-1',
    );
  });

  it('create 모드(agentId null)에서도 섹션 자체는 렌더된다', () => {
    renderPanel(25, null);
    expect(screen.getByTestId('webhook-section')).toHaveAttribute(
      'data-agent-id',
      '',
    );
  });
});
