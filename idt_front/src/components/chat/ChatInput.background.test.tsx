// background-jobs S9 — ChatInput 백그라운드 전환 버튼 단위
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ChatInput from './ChatInput';

describe('ChatInput — 백그라운드 전환 (S9)', () => {
  it('backgroundEnabled=false 면 버튼을 숨긴다', () => {
    render(<ChatInput onSend={vi.fn()} backgroundEnabled={false} />);
    expect(
      screen.queryByRole('button', { name: '백그라운드로 실행' }),
    ).not.toBeInTheDocument();
  });

  it('입력 내용과 함께 onSendBackground를 호출하고 입력을 비운다', async () => {
    const onSendBackground = vi.fn();
    render(
      <ChatInput
        onSend={vi.fn()}
        backgroundEnabled
        onSendBackground={onSendBackground}
      />,
    );
    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    await userEvent.type(textarea, '시장 조사 보고서 만들어줘');
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드로 실행' }),
    );
    expect(onSendBackground).toHaveBeenCalledWith('시장 조사 보고서 만들어줘');
    expect(textarea).toHaveValue('');
  });

  it('빈 입력이면 버튼이 비활성화된다', () => {
    render(
      <ChatInput onSend={vi.fn()} backgroundEnabled onSendBackground={vi.fn()} />,
    );
    expect(
      screen.getByRole('button', { name: '백그라운드로 실행' }),
    ).toBeDisabled();
  });

  it('isLoading 중에는 백그라운드 전송도 차단된다', async () => {
    const onSendBackground = vi.fn();
    render(
      <ChatInput
        onSend={vi.fn()}
        isLoading
        backgroundEnabled
        onSendBackground={onSendBackground}
      />,
    );
    expect(
      screen.getByRole('button', { name: '백그라운드로 실행' }),
    ).toBeDisabled();
  });
});
