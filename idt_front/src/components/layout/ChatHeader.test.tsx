// wiki-navigation S3: 채팅 헤더 → 에이전트 워크스페이스 링크
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import ChatHeader from './ChatHeader';

const renderHeader = (props: Parameters<typeof ChatHeader>[0] = {}) =>
  render(
    <MemoryRouter>
      <ChatHeader {...props} />
    </MemoryRouter>,
  );

describe('ChatHeader — 워크스페이스 링크', () => {
  it('T6: agentId가 있으면 워크스페이스 링크가 노출된다', () => {
    renderHeader({ title: '문서 분석가', agentId: 'agent-1' });
    const link = screen.getByTitle('에이전트 워크스페이스');
    expect(link).toHaveAttribute('href', '/agents/agent-1/workspace');
  });

  it('T7: agentId가 없으면 워크스페이스 링크를 노출하지 않는다', () => {
    renderHeader({ title: 'SUPER AI Agent' });
    expect(screen.queryByTitle('에이전트 워크스페이스')).not.toBeInTheDocument();
  });
});
