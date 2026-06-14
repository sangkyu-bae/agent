import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ToolPreviewPanel from './ToolPreviewPanel';
import type { ChatToolEvent } from '@/hooks/useChatStream';

const events: ChatToolEvent[] = [
  { kind: 'started', toolName: 'tavily_search' },
  { kind: 'completed', toolName: 'tavily_search', durationMs: 1234 },
];

describe('ToolPreviewPanel', () => {
  it('returns null when events is empty', () => {
    const { container } = render(
      <ToolPreviewPanel events={[]} visible={true} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders compact button when not visible (counts tools only)', () => {
    render(<ToolPreviewPanel events={events} visible={false} />);
    expect(screen.getByText(/추론 진행 보기 \(2\)/)).toBeInTheDocument();
  });

  it('renders panel with events when visible', () => {
    render(<ToolPreviewPanel events={events} visible={true} />);
    expect(screen.getByText('추론 진행')).toBeInTheDocument();
    expect(screen.getAllByText('tavily_search')).toHaveLength(2);
    expect(screen.getByText('1234ms')).toBeInTheDocument();
  });

  it('calls onToggleVisible(true) when compact button clicked', () => {
    const onToggle = vi.fn();
    render(
      <ToolPreviewPanel
        events={events}
        visible={false}
        onToggleVisible={onToggle}
      />,
    );
    fireEvent.click(screen.getByText(/추론 진행 보기/));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('calls onToggleVisible(false) when 숨기기 clicked', () => {
    const onToggle = vi.fn();
    render(
      <ToolPreviewPanel
        events={events}
        visible={true}
        onToggleVisible={onToggle}
      />,
    );
    fireEvent.click(screen.getByText('숨기기'));
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  // agent-chat-reasoning-display Design §5
  describe('reasoning rendering (T11)', () => {
    const mixed: ChatToolEvent[] = [
      {
        kind: 'reasoning',
        toolName: 'supervisor',
        text: 'X 정보가 필요해서 search_agent를 호출합니다.',
      },
      { kind: 'started', toolName: 'tavily_search' },
      {
        kind: 'completed',
        toolName: 'tavily_search',
        durationMs: 1240,
        preview: '{"query": "예시"}',
      },
      {
        kind: 'reasoning',
        toolName: 'supervisor',
        text: '검색 결과를 정리해 답변합니다.',
      },
    ];

    it('renders reasoning text with 💭 marker', () => {
      render(<ToolPreviewPanel events={mixed} visible={true} />);
      expect(
        screen.getByText('X 정보가 필요해서 search_agent를 호출합니다.'),
      ).toBeInTheDocument();
      expect(
        screen.getByText('검색 결과를 정리해 답변합니다.'),
      ).toBeInTheDocument();
    });

    it('renders tool name + duration, never JSON preview', () => {
      render(<ToolPreviewPanel events={mixed} visible={true} />);
      expect(screen.getAllByText('tavily_search')).toHaveLength(2);
      expect(screen.getByText('1240ms')).toBeInTheDocument();
      // FR-04: JSON preview는 화면에 노출되지 않는다
      expect(screen.queryByText(/{"query":/)).toBeNull();
    });

    it('counts only tools (not reasoning) in compact button', () => {
      render(<ToolPreviewPanel events={mixed} visible={false} />);
      // 4개 중 tool은 2개(started/completed). reasoning 2개는 제외.
      expect(screen.getByText(/추론 진행 보기 \(2\)/)).toBeInTheDocument();
    });
  });
});
