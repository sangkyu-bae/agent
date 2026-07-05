import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { UseAgentRunStreamOptions } from '@/hooks/useAgentRunStream';
import TestChatView from './TestChatView';

// useAgentRunStream을 모킹하여 WS 없이 스트림 완료 상태를 구동한다.
// enabled + streamId가 있으면 즉시 완료(answer 확정) 상태를 반환한다.
vi.mock('@/hooks/useAgentRunStream', () => ({
  useAgentRunStream: (opts: UseAgentRunStreamOptions) => ({
    status: opts.enabled ? 'open' : 'idle',
    steps: [],
    tokens: opts.enabled ? '테스트 ' : '',
    answer: opts.enabled && opts.streamId ? '테스트 응답입니다' : null,
    charts: [],
    error: null,
    isDone: !!(opts.enabled && opts.streamId),
    streamId: opts.streamId ?? '',
  }),
}));

describe('TestChatView', () => {
  it('생성 모드에서는 입력이 비활성이고 안내를 표시한다', () => {
    render(<TestChatView mode="create" agentId={null} agentName="새 에이전트" />);
    expect(screen.getByText('저장 후 테스트할 수 있습니다')).toBeInTheDocument();
    expect(screen.getByLabelText('테스트 입력')).toBeDisabled();
  });

  it('수정 모드에서 질의 전송 시 사용자 메시지와 스트림 응답을 렌더한다', async () => {
    render(<TestChatView mode="edit" agentId="agent-1" agentName="문서 분석가" />);

    const input = screen.getByLabelText('테스트 입력');
    expect(input).not.toBeDisabled();

    await userEvent.type(input, '안녕하세요{Enter}');

    // 사용자 메시지 + 스트림 완료 후 확정된 어시스턴트 응답
    expect(await screen.findByText('안녕하세요')).toBeInTheDocument();
    expect(await screen.findByText('테스트 응답입니다')).toBeInTheDocument();
  });

  it('"새 대화" 클릭 시 메시지를 초기화한다', async () => {
    render(<TestChatView mode="edit" agentId="agent-1" agentName="문서 분석가" />);

    await userEvent.type(screen.getByLabelText('테스트 입력'), '첫 질문{Enter}');
    expect(await screen.findByText('첫 질문')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /새 대화/ }));
    expect(screen.queryByText('첫 질문')).toBeNull();
    expect(screen.getByText('에이전트와 대화를 시작하세요')).toBeInTheDocument();
  });
});
