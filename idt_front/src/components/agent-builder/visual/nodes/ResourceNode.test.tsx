import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ReactFlowProvider } from '@xyflow/react';
import ResourceNode from './ResourceNode';
import type { ResourceNodeData } from '../buildGraph';

/** RF 커스텀 노드는 Provider 컨텍스트(Handle)가 필요. */
const renderNode = (data: ResourceNodeData) =>
  render(
    <ReactFlowProvider>
      {/* @ts-expect-error 테스트에서는 data만 주입 */}
      <ResourceNode data={data} />
    </ReactFlowProvider>,
  );

describe('ResourceNode', () => {
  it('도구 노드 — 빈 상태 텍스트 표시', () => {
    renderNode({ kind: 'tool', items: [], disabled: false });
    expect(screen.getByText('도구가 설정되지 않았습니다')).toBeInTheDocument();
  });

  it('도구 노드 — 도구명 목록 표시', () => {
    renderNode({ kind: 'tool', items: ['웹 검색'], disabled: false });
    expect(screen.getByText('웹 검색')).toBeInTheDocument();
  });

  it('도구 노드 — "도구 추가" 클릭 시 onAction 호출', async () => {
    const onAction = vi.fn();
    renderNode({ kind: 'tool', items: [], disabled: false, onAction });
    await userEvent.click(screen.getByRole('button', { name: '+ 도구 추가' }));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it('스킬 노드 — 액션 버튼 disabled (준비중)', async () => {
    const onAction = vi.fn();
    renderNode({ kind: 'skill', items: [], disabled: true, onAction });
    const btn = screen.getByRole('button', { name: '+ 스킬 추가' });
    expect(btn).toBeDisabled();
    await userEvent.click(btn);
    expect(onAction).not.toHaveBeenCalled();
  });

  it('미들웨어 노드 — 빈 상태 + disabled', () => {
    renderNode({ kind: 'middleware', items: [], disabled: true });
    expect(screen.getByText('미들웨어 없음')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ 미들웨어 추가' })).toBeDisabled();
  });

  it('모델 노드 — 라벨 표시 + 카드 클릭 시 onAction 호출', async () => {
    const onAction = vi.fn();
    renderNode({ kind: 'model', items: ['anthropic:claude-haiku-4-5'], disabled: false, onAction });
    expect(screen.getByText('anthropic:claude-haiku-4-5')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button'));
    expect(onAction).toHaveBeenCalledOnce();
  });
});
