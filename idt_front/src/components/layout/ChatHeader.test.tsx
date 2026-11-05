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

describe('ChatHeader — 수정 링크 (agent-edit-entry FR-07)', () => {
  it('C1: agentId + canEdit 이면 편집 진입 링크를 노출한다', () => {
    renderHeader({ title: '문서 분석가', agentId: 'agent-1', canEdit: true });
    expect(screen.getByRole('link', { name: '에이전트 수정' })).toHaveAttribute(
      'href',
      '/agent-builder?edit=agent-1&returnTo=%2Fchatpage',
    );
  });

  it.each([
    ['canEdit=false', { agentId: 'agent-1', canEdit: false }],
    ['canEdit 미지정', { agentId: 'agent-1' }],
    ['agentId 없음', { canEdit: true }],
  ])('C2: %s 이면 수정 링크를 노출하지 않는다', (_label, props) => {
    renderHeader({ title: '봇', ...props });
    expect(screen.queryByRole('link', { name: '에이전트 수정' })).not.toBeInTheDocument();
  });

  // agent-edit-entry Check 갭 #3: cn 은 클래스를 병합하지 않아 Badge 기본 inline-flex 가
  // hidden 을 이긴다 → 375px 에서 배지가 보여 헤더가 넘쳤다. 숨김은 감싸는 요소가 맡는다.
  it('C2b: RAG 배지는 좁은 폭에서 숨겨지도록 감싸는 요소에 hidden 을 둔다', () => {
    renderHeader({ title: '봇', agentId: 'agent-1', canEdit: true });
    const badge = screen.getByText('RAG · Agent');
    expect(badge.className).not.toMatch(/\bhidden\b/);
    expect(badge.parentElement).toHaveClass('hidden', 'sm:inline-flex');
  });
});
