import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ReactFlowProvider } from '@xyflow/react';
import AgentNode from './AgentNode';
import type { AgentNodeData } from '../buildGraph';

const renderNode = (data: AgentNodeData) =>
  render(
    <ReactFlowProvider>
      {/* @ts-expect-error 테스트에서는 data만 주입 */}
      <AgentNode data={data} />
    </ReactFlowProvider>,
  );

describe('AgentNode', () => {
  it('이름/설명/지침을 렌더한다', () => {
    renderNode({ name: '내 에이전트', description: '설명', systemPrompt: '너는 도우미' });
    expect(screen.getByText('내 에이전트')).toBeInTheDocument();
    expect(screen.getByText('설명')).toBeInTheDocument();
    expect(screen.getByText('너는 도우미')).toBeInTheDocument();
  });

  it('빈 값은 플레이스홀더로 대체', () => {
    renderNode({ name: '', description: '', systemPrompt: '' });
    expect(screen.getByText('새 에이전트')).toBeInTheDocument();
    expect(screen.getByText('에이전트 설명을 입력하세요')).toBeInTheDocument();
    expect(screen.getByText('No instructions set')).toBeInTheDocument();
  });

  it('"Edit in Form" 클릭 시 onEditInForm 호출', async () => {
    const onEditInForm = vi.fn();
    renderNode({ name: 'A', description: '', systemPrompt: '', onEditInForm });
    await userEvent.click(screen.getByRole('button', { name: /Edit in Form/ }));
    expect(onEditInForm).toHaveBeenCalledOnce();
  });
});
