import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import SubAgentManagerModal from './SubAgentManagerModal';
import type { SubAgentConfig } from '@/types/agentBuilder';
import type { LlmModel } from '@/types/llmModel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CANDIDATES = [
  { agent_id: 'a1', name: '검색봇', description: '웹 검색', source_type: 'owned', tool_ids: [], has_sub_agents: false, llm_model_id: 'm1', visibility: 'private' },
  { agent_id: 'a2', name: '분석봇', description: '데이터 분석', source_type: 'public', tool_ids: [], has_sub_agents: false, llm_model_id: 'm1', visibility: 'public' },
  { agent_id: 'self', name: '나자신', description: '편집중', source_type: 'owned', tool_ids: [], has_sub_agents: false, llm_model_id: 'm1', visibility: 'private' },
];

const MODELS: LlmModel[] = [
  { id: 'm1', provider: 'anthropic', model_name: 'claude-haiku-4-5' } as LlmModel,
];

function mockList(agents = CANDIDATES) {
  server.use(
    http.get('*/api/v1/agents/available-sub-agents', () =>
      HttpResponse.json({ agents }),
    ),
  );
}

function renderModal(props: Partial<React.ComponentProps<typeof SubAgentManagerModal>> = {}) {
  const onAdd = vi.fn();
  const onRemove = vi.fn();
  const onClose = vi.fn();
  render(
    <SubAgentManagerModal
      isOpen
      currentAgentId="self"
      selected={[]}
      models={MODELS}
      onAdd={onAdd}
      onRemove={onRemove}
      onClose={onClose}
      {...props}
    />,
    { wrapper: createWrapper() },
  );
  return { onAdd, onRemove, onClose };
}

describe('SubAgentManagerModal', () => {
  it('후보를 표시하고 현재 편집 에이전트는 제외한다', async () => {
    mockList();
    renderModal();
    await waitFor(() => expect(screen.getByText('검색봇')).toBeInTheDocument());
    expect(screen.getByText('분석봇')).toBeInTheDocument();
    expect(screen.queryByText('나자신')).not.toBeInTheDocument();
    // 모델 배지
    expect(screen.getAllByText('anthropic:claude-haiku-4-5').length).toBeGreaterThan(0);
  });

  it('이미 추가된 서브에이전트는 후보에서 제외한다', async () => {
    mockList();
    const selected: SubAgentConfig[] = [
      { ref_agent_id: 'a1', name: '검색봇', description: '' },
    ];
    renderModal({ selected });
    await waitFor(() => expect(screen.getByText('분석봇')).toBeInTheDocument());
    // 좌측 현재 목록에는 검색봇이 있지만 우측 후보에는 없음 → "추가" 버튼은 분석봇 1개만
    expect(screen.getAllByRole('button', { name: '추가' })).toHaveLength(1);
  });

  it('검색어로 후보를 필터링한다', async () => {
    mockList();
    renderModal();
    await waitFor(() => expect(screen.getByText('검색봇')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('에이전트 검색'), {
      target: { value: '분석' },
    });
    expect(screen.queryByText('검색봇')).not.toBeInTheDocument();
    expect(screen.getByText('분석봇')).toBeInTheDocument();
  });

  it('추가 클릭 시 onAdd를 호출한다', async () => {
    mockList();
    const { onAdd } = renderModal();
    await waitFor(() => expect(screen.getByText('검색봇')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: '추가' })[0]);
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ agent_id: 'a1' }));
  });

  it('최대 3개 도달 시 추가 버튼이 비활성화된다', async () => {
    mockList();
    const selected: SubAgentConfig[] = [
      { ref_agent_id: 'x1', name: 'X1', description: '' },
      { ref_agent_id: 'x2', name: 'X2', description: '' },
      { ref_agent_id: 'x3', name: 'X3', description: '' },
    ];
    renderModal({ selected });
    await waitFor(() => expect(screen.getByText('검색봇')).toBeInTheDocument());
    screen.getAllByRole('button', { name: '추가' }).forEach((btn) => {
      expect(btn).toBeDisabled();
    });
  });

  it('현재 서브에이전트 제거 시 onRemove를 호출한다', async () => {
    mockList();
    const selected: SubAgentConfig[] = [
      { ref_agent_id: 'a1', name: '검색봇', description: '' },
    ];
    const { onRemove } = renderModal({ selected });
    fireEvent.click(screen.getByRole('button', { name: '검색봇 제거' }));
    expect(onRemove).toHaveBeenCalledWith('a1');
  });
});
