// subagent-step-observability Design §5.3 / §8.3 F4~F6
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StepTree from './StepTree';
import type { LlmCallDto, StepDto, ToolCallDto } from '@/types/agentRunAdmin';

const step = (
  id: string,
  step_index: number,
  node_name: string,
  parent_step_id: string | null = null,
  depth = 0,
): StepDto => ({
  id,
  step_index,
  node_name,
  node_type: 'WORKER',
  status: 'SUCCESS',
  input_summary: null,
  output_summary: null,
  started_at: '2026-10-06T07:32:16Z',
  ended_at: null,
  latency_ms: 120,
  error_text: null,
  llm_calls: [],
  tool_calls: [],
  parent_step_id,
  depth,
});

const nested = [
  step('s1', 1, 'supervisor'),
  step('w1', 2, 'sub_agent_분석가_0'),
  step('c1', 3, 'child_supervisor', 'w1', 1),
  step('c2', 4, 'list_inquiries_worker', 'w1', 1),
  step('s2', 5, 'final_answer'),
];

describe('StepTree', () => {
  it('F4: 자식이 있는 step 에 토글과 "하위 N" 배지를 보이고 기본은 펼침', () => {
    render(<StepTree steps={nested} orphanLlmCalls={[]} />);

    const toggle = screen.getByRole('button', { name: /sub_agent_분석가_0 하위 step/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('하위 2')).toBeInTheDocument();
    expect(screen.getByText('child_supervisor')).toBeInTheDocument();
    expect(screen.getByText('list_inquiries_worker')).toBeInTheDocument();
  });

  it('F4: 자식은 부모 step 블록 안에 그려진다', () => {
    render(<StepTree steps={nested} orphanLlmCalls={[]} />);
    const group = screen.getByRole('group', { name: 'sub_agent_분석가_0 하위 step' });
    expect(within(group).getByText('child_supervisor')).toBeInTheDocument();
    expect(within(group).queryByText('final_answer')).not.toBeInTheDocument();
  });

  it('F5: 토글을 누르면 자식이 숨겨지고 aria-expanded=false', async () => {
    const user = userEvent.setup();
    render(<StepTree steps={nested} orphanLlmCalls={[]} />);

    const toggle = screen.getByRole('button', { name: /sub_agent_분석가_0 하위 step/ });
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('child_supervisor')).not.toBeInTheDocument();
    expect(screen.getByText('final_answer')).toBeInTheDocument();
  });

  it('G-4: 자식 step 의 tool·LLM 호출과 orphan LLM 블록이 유지된다', () => {
    const llm: LlmCallDto = {
      id: 'l1',
      purpose: 'supervisor',
      provider: 'openai',
      model_name: 'gpt-5.1',
      llm_model_id: null,
      token_usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
      cost_usd: { input_usd: 0, output_usd: 0, total_usd: 0.001 },
      latency_ms: 300,
      status: 'SUCCESS',
      created_at: '2026-10-06T07:32:16Z',
    };
    const tool: ToolCallDto = {
      id: 't1',
      tool_name: 'list_inquiries',
      arguments: { board: 'loan' },
      result_summary: '미답변 1696건',
      latency_ms: 900,
      status: 'SUCCESS',
      retrievals: [],
      llm_calls: [],
    };
    const child = { ...step('c2', 4, 'list_inquiries_worker', 'w1', 1), tool_calls: [tool] };
    const childSup = { ...step('c1', 3, 'child_supervisor', 'w1', 1), llm_calls: [llm] };
    render(
      <StepTree
        steps={[nested[0], nested[1], childSup, child, nested[4]]}
        orphanLlmCalls={[{ ...llm, id: 'l-orphan', model_name: 'orphan-model' }]}
      />,
    );

    const group = screen.getByRole('group', { name: 'sub_agent_분석가_0 하위 step' });
    expect(within(group).getByText(/list_inquiries$/)).toBeInTheDocument();
    expect(within(group).getByText('gpt-5.1')).toBeInTheDocument();
    expect(screen.getByText('orphan LLM calls (step 외)')).toBeInTheDocument();
    expect(screen.getByText('orphan-model')).toBeInTheDocument();
  });

  it('F6: 과거 런(계층 없음)은 토글 없이 평면으로 그린다', () => {
    render(
      <StepTree
        steps={[step('a', 1, 'supervisor'), step('b', 2, 'quality_gate')]}
        orphanLlmCalls={[]}
      />,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('supervisor')).toBeInTheDocument();
    expect(screen.getByText('quality_gate')).toBeInTheDocument();
  });
});
