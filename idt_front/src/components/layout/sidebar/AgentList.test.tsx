import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import AgentList from './AgentList';
import { useLayoutStore } from '@/store/layoutStore';
import type { MyAgent } from '@/types/agent';

const makeAgent = (over: Partial<MyAgent>): MyAgent => ({
  agent_id: 'a',
  name: '에이전트',
  description: '설명',
  source_type: 'owned',
  visibility: 'private',
  temperature: 0.7,
  owner_user_id: 'u1',
  forked_from: null,
  is_pinned: false,
  created_at: '2026-11-01T00:00:00Z',
  ...over,
});

const AGENTS: MyAgent[] = [
  makeAgent({ agent_id: 'p1', name: '여신 심사 보조', description: '심사 의견 초안', is_pinned: true }),
  makeAgent({ agent_id: 'o1', name: '금리 비교 분석가', description: '금리 비교표' }),
  makeAgent({ agent_id: 'o2', name: '회의록 정리', description: '' }),
  makeAgent({ agent_id: 'f1', name: 'FAQ 생성기', description: 'FAQ 추출', source_type: 'forked' }),
];

const LocationDisplay = () => <div data-testid="location">{useLocation().pathname}</div>;

const renderList = (props: Partial<React.ComponentProps<typeof AgentList>> = {}) => {
  const onSelectAgent = vi.fn();
  render(
    <MemoryRouter initialEntries={['/agent-store']}>
      <AgentList agents={AGENTS} selectedAgentId={null} onSelectAgent={onSelectAgent} {...props} />
      <Routes>
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>,
  );
  return { onSelectAgent };
};

afterEach(() => {
  useLayoutStore.setState({ collapsedAgentGroups: [] });
  localStorage.clear();
});

describe('AgentList — 그룹', () => {
  it('AL1: 에이전트가 있는 그룹만 토글 버튼으로 표시하고 개수를 보여준다', () => {
    renderList();
    expect(screen.getByRole('button', { name: /고정됨\s*1/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /내 에이전트\s*2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /포크\s*1/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^구독/ })).not.toBeInTheDocument();
  });

  it('AL2: 그룹 토글을 누르면 항목이 숨겨지고 스토어에 저장된다', async () => {
    renderList();
    const toggle = screen.getByRole('button', { name: /내 에이전트/ });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('금리 비교 분석가')).not.toBeInTheDocument();
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual(['owned']);
    await userEvent.click(toggle);
    expect(screen.getByText('금리 비교 분석가')).toBeInTheDocument();
  });

  it('AL3: 스토어에 접힌 그룹은 처음부터 숨겨진다', () => {
    useLayoutStore.setState({ collapsedAgentGroups: ['pinned'] });
    renderList();
    expect(screen.getByRole('button', { name: /고정됨/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('여신 심사 보조')).not.toBeInTheDocument();
  });
});

describe('AgentList — 항목', () => {
  it('AL4: 항목을 누르면 onSelectAgent 호출 후 /chatpage로 이동한다', async () => {
    const { onSelectAgent } = renderList();
    await userEvent.click(screen.getByText('금리 비교 분석가'));
    expect(onSelectAgent).toHaveBeenCalledWith('o1');
    expect(screen.getByTestId('location')).toHaveTextContent('/chatpage');
  });

  it('AL5: 선택된 항목은 aria-current="true"를 가진다', () => {
    renderList({ selectedAgentId: 'o1' });
    const item = screen.getByText('금리 비교 분석가').closest('button')!;
    expect(item).toHaveAttribute('aria-current', 'true');
    const other = screen.getByText('FAQ 생성기').closest('button')!;
    expect(other).not.toHaveAttribute('aria-current');
  });

  it('AL6: showAvatar에 따라 첫 글자 아바타를 표시하거나 숨긴다', () => {
    const { unmount } = render(
      <MemoryRouter>
        <AgentList agents={AGENTS} selectedAgentId={null} onSelectAgent={vi.fn()} showAvatar />
      </MemoryRouter>,
    );
    const item = screen.getByText('금리 비교 분석가').closest('button')!;
    expect(within(item).getByText('금')).toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter>
        <AgentList agents={AGENTS} selectedAgentId={null} onSelectAgent={vi.fn()} showAvatar={false} />
      </MemoryRouter>,
    );
    const item2 = screen.getByText('금리 비교 분석가').closest('button')!;
    expect(within(item2).queryByText('금')).not.toBeInTheDocument();
  });

  it('AL7: 설명이 있으면 2줄, 비어 있으면 이름만 표시하고 설명은 title로 제공한다', () => {
    renderList();
    expect(screen.getByText('금리 비교표')).toBeInTheDocument();
    const item = screen.getByText('금리 비교 분석가').closest('button')!;
    expect(item).toHaveAttribute('title', '금리 비교표');
    const noDesc = screen.getByText('회의록 정리').closest('button')!;
    expect(noDesc.querySelectorAll('[data-slot="agent-desc"]')).toHaveLength(0);
  });

  it('AL7b: 고정 항목은 별 아이콘을 유지한다', () => {
    renderList();
    const item = screen.getByText('여신 심사 보조').closest('button')!;
    expect(within(item).getByLabelText('고정됨')).toBeInTheDocument();
  });
});

describe('AgentList — 예외 값', () => {
  it('AL10: 이름이 비어 있으면 아바타에 ?를 표시한다', () => {
    render(
      <MemoryRouter>
        <AgentList
          agents={[makeAgent({ agent_id: 'x', name: '  ', description: '이름 없음' })]}
          selectedAgentId={null}
          onSelectAgent={vi.fn()}
          showAvatar
        />
      </MemoryRouter>,
    );
    const item = screen.getByText('이름 없음').closest('button')!;
    expect(within(item).getByText('?')).toBeInTheDocument();
  });

  it('AL11: 비어 있는 그룹의 접힘 키가 저장돼 있어도 다른 그룹은 펼쳐진 채 렌더한다', () => {
    useLayoutStore.setState({ collapsedAgentGroups: ['subscribed'] });
    renderList();
    expect(screen.queryByRole('button', { name: /^구독/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /내 에이전트/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('금리 비교 분석가')).toBeInTheDocument();
  });
});

describe('AgentList — 헤더와 상태', () => {
  it('AL8: onRetry가 있으면 새로고침 버튼이 호출하고, 없으면 버튼이 없다', async () => {
    const onRetry = vi.fn();
    const { unmount } = render(
      <MemoryRouter>
        <AgentList agents={AGENTS} selectedAgentId={null} onSelectAgent={vi.fn()} onRetry={onRetry} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole('button', { name: '에이전트 목록 새로고침' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    unmount();
    renderList();
    expect(screen.queryByRole('button', { name: '에이전트 목록 새로고침' })).not.toBeInTheDocument();
  });

  it('AL9: 로딩·오류·빈 상태를 기존 문구로 표시한다', async () => {
    const { unmount } = render(
      <MemoryRouter>
        <AgentList agents={[]} selectedAgentId={null} onSelectAgent={vi.fn()} isLoading />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status', { name: '불러오는 중' })).toBeInTheDocument();
    unmount();

    const onRetry = vi.fn();
    const r2 = render(
      <MemoryRouter>
        <AgentList agents={[]} selectedAgentId={null} onSelectAgent={vi.fn()} isError onRetry={onRetry} />
      </MemoryRouter>,
    );
    expect(screen.getByText('에이전트 목록을 불러오지 못했습니다')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(onRetry).toHaveBeenCalled();
    r2.unmount();

    renderList({ agents: [] });
    expect(screen.getByText('등록된 에이전트가 없습니다')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '에이전트 만들기' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/agent-builder');
  });
});
