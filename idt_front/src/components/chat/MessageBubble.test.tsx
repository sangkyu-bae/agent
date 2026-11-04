import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MessageBubble from './MessageBubble';
import type { Message } from '@/types/chat';

// useChart는 chart.js canvas에 의존하므로 모킹: ref만 반환
vi.mock('@/hooks/useChart', () => ({
  useChart: () => ({ current: null }),
}));

const baseMessage: Omit<Message, 'role' | 'content'> = {
  id: 'msg-1',
  createdAt: '2026-06-10T00:00:00.000Z',
};

// chat-markdown-rendering Design §6 — MessageBubble 검증 3케이스
describe('MessageBubble', () => {
  it('어시스턴트 메시지는 마크다운으로 렌더한다', () => {
    const message: Message = { ...baseMessage, role: 'assistant', content: '### 분석 결과' };
    render(<MessageBubble message={message} />);
    expect(screen.getByRole('heading', { level: 3, name: '분석 결과' })).toBeInTheDocument();
  });

  it('사용자 메시지는 plain text 그대로 렌더한다', () => {
    const message: Message = { ...baseMessage, role: 'user', content: '### 분석 결과' };
    render(<MessageBubble message={message} />);
    expect(screen.queryByRole('heading')).toBeNull();
    expect(screen.getByText('### 분석 결과')).toBeInTheDocument();
  });

  it('어시스턴트 메시지에 도구 실행 내역이 있으면 접힌 헤더를 그린다 (agent-run-tool-trace)', () => {
    const message: Message = {
      ...baseMessage,
      role: 'assistant',
      content: '답변',
      toolTrace: {
        omitted_count: 0,
        items: [{ seq: 1, kind: 'tool', label: 'list_inquiries', status: 'success' }],
      },
    };
    render(<MessageBubble message={message} />);
    expect(screen.getByRole('button', { name: /도구 실행 내역 \(1\)/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('도구 실행 내역이 없으면 헤더를 그리지 않는다', () => {
    const message: Message = { ...baseMessage, role: 'assistant', content: '답변' };
    render(<MessageBubble message={message} />);
    expect(screen.queryByRole('button', { name: /도구 실행 내역/ })).toBeNull();
  });

  it('스트리밍 중이면 커서 요소를 렌더한다', () => {
    const message: Message = {
      ...baseMessage,
      role: 'assistant',
      content: '답변 생성 중',
      isStreaming: true,
    };
    const { container } = render(<MessageBubble message={message} />);
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });
});
