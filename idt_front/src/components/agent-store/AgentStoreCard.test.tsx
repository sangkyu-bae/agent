import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import AgentStoreCard from './AgentStoreCard';
import type { StoreAgentSummary } from '@/types/agentStore';

const mockAgent: StoreAgentSummary = {
  agent_id: 'agent-1',
  name: '문서 분석가',
  description: '문서를 분석하는 AI 에이전트',
  visibility: 'public',
  department_name: 'IT부서',
  owner_user_id: 'user-1',
  owner_email: 'owner@test.com',
  temperature: 0.7,
  can_edit: false,
  can_delete: false,
  created_at: '2026-04-20T10:00:00Z',
};

const setup = (overrides?: Partial<StoreAgentSummary>) => {
  const onClick = vi.fn();
  const onSubscribe = vi.fn();
  const onFork = vi.fn();
  const agent = { ...mockAgent, ...overrides };

  render(
    <AgentStoreCard
      agent={agent}
      onClick={onClick}
      onSubscribe={onSubscribe}
      onFork={onFork}
    />,
  );

  return { onClick, onSubscribe, onFork, agent };
};

describe('AgentStoreCard', () => {
  it('AC-1: 에이전트 이름과 설명을 렌더링한다', () => {
    setup();
    expect(screen.getByText('문서 분석가')).toBeInTheDocument();
    expect(screen.getByText('문서를 분석하는 AI 에이전트')).toBeInTheDocument();
  });

  it('AC-2: 소유자 이메일 prefix와 visibility를 표시한다', () => {
    setup();
    expect(screen.getByText(/@owner · 공개/)).toBeInTheDocument();
  });

  it('AC-3: 부서 뱃지와 temperature를 표시한다', () => {
    setup();
    expect(screen.getByText('IT부서')).toBeInTheDocument();
    expect(screen.getByText('temp 0.7')).toBeInTheDocument();
  });

  it('AC-4: 부서가 없으면 뱃지를 표시하지 않는다', () => {
    setup({ department_name: null });
    expect(screen.queryByText('IT부서')).not.toBeInTheDocument();
  });

  it('AC-5: 카드 클릭 시 onClick 호출', async () => {
    const { onClick } = setup();
    await userEvent.click(screen.getByRole('article'));
    expect(onClick).toHaveBeenCalledWith('agent-1');
  });

  it('AC-6: 구독 버튼 클릭 시 onSubscribe 호출 (카드 onClick 미호출)', async () => {
    const { onClick, onSubscribe } = setup();
    await userEvent.click(screen.getByText('구독'));
    expect(onSubscribe).toHaveBeenCalledWith('agent-1');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('AC-7: 포크 버튼 클릭 시 onFork 호출 (카드 onClick 미호출)', async () => {
    const { onClick, onFork } = setup();
    await userEvent.click(screen.getByText('포크'));
    expect(onFork).toHaveBeenCalledWith('agent-1');
    expect(onClick).not.toHaveBeenCalled();
  });

  it('AC-8: role="article" 속성이 존재한다', () => {
    setup();
    expect(screen.getByRole('article')).toBeInTheDocument();
  });

  it('AC-9: owner_email이 없으면 owner_user_id를 표시한다', () => {
    setup({ owner_email: null });
    expect(screen.getByText(/user-1 · 공개/)).toBeInTheDocument();
  });

  it('AC-10: 설명이 없으면 기본 텍스트 표시', () => {
    setup({ description: '' });
    expect(screen.getByText('설명이 없습니다.')).toBeInTheDocument();
  });
});
