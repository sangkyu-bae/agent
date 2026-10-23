import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import ChatHistoryPanel from './ChatHistoryPanel';
import type { ChatSession } from '@/types/chat';

const sessions: ChatSession[] = [
  { id: 's1', title: '여신 한도 문의', messages: [], createdAt: '2026-10-01T00:00:00Z', updatedAt: '2026-10-01T00:00:00Z' },
  { id: 's2', title: '정책 요약', messages: [], createdAt: '2026-10-02T00:00:00Z', updatedAt: '2026-10-02T00:00:00Z' },
];

const baseProps = {
  sessions,
  activeSessionId: 's1',
  onSelectSession: vi.fn(),
  onNewChat: vi.fn(),
};

describe('ChatHistoryPanel', () => {
  it('닫힘 상태는 레일만 렌더링하고 열기·새 대화 버튼을 제공한다', async () => {
    const onToggle = vi.fn();
    const onNewChat = vi.fn();
    render(<ChatHistoryPanel {...baseProps} isOpen={false} onToggle={onToggle} onNewChat={onNewChat} />);
    expect(screen.queryByRole('region', { name: '대화 목록' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '대화 목록 열기' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: '새 대화' }));
    expect(onNewChat).toHaveBeenCalledTimes(1);
  });

  it('열림 상태에서 세션 목록·활성 표시·검색이 동작한다', async () => {
    const onSelectSession = vi.fn();
    render(<ChatHistoryPanel {...baseProps} isOpen onToggle={vi.fn()} onSelectSession={onSelectSession} />);
    expect(screen.getByRole('region', { name: '대화 목록' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /여신 한도 문의/ })).toHaveAttribute('aria-current', 'true');

    await userEvent.click(screen.getByRole('button', { name: /정책 요약/ }));
    expect(onSelectSession).toHaveBeenCalledWith('s2');

    await userEvent.type(screen.getByRole('textbox', { name: '대화 검색' }), '정책');
    expect(screen.queryByText('여신 한도 문의')).not.toBeInTheDocument();
    expect(screen.getByText('정책 요약')).toBeInTheDocument();
    expect(screen.queryByTestId('history-backdrop')).not.toBeInTheDocument();
  });

  it('overlay 모드에서는 백드롭 클릭과 ESC로 닫힌다', () => {
    const onToggle = vi.fn();
    render(<ChatHistoryPanel {...baseProps} isOpen overlay onToggle={onToggle} />);
    expect(screen.getByRole('region', { name: '대화 목록' }).className).toContain('absolute');
    fireEvent.click(screen.getByTestId('history-backdrop'));
    expect(onToggle).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('에러 상태에서 재시도 버튼을 노출한다', async () => {
    const onRetry = vi.fn();
    render(<ChatHistoryPanel {...baseProps} isOpen onToggle={vi.fn()} isError onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
