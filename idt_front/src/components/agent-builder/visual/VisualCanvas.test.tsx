import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeAll } from 'vitest';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import VisualCanvas from './VisualCanvas';

// React Flow는 jsdom에서 ResizeObserver를 요구한다.
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const FORM: AgentBuilderFormData = {
  name: '테스트 에이전트',
  description: '설명',
  model: 'claude-haiku-4-5',
  systemPrompt: '지침',
  tools: [],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
};

const noop = () => {};

const renderCanvas = () =>
  render(
    <VisualCanvas
      form={FORM}
      onAddTool={noop}
      onConfigModel={noop}
      onManageSubAgents={noop}
      onEditInForm={noop}
    />,
  );

// 노드 클릭은 jsdom에서 d3-drag 충돌을 유발하므로, 노드별 콜백 검증은
// AgentNode/ResourceNode 단위 테스트에서 수행한다. 여기서는 통합 렌더만 확인.
describe('VisualCanvas', () => {
  it('폼 데이터로 에이전트/모델 노드를 렌더한다', async () => {
    renderCanvas();
    expect(await screen.findByText('테스트 에이전트')).toBeInTheDocument();
    expect(screen.getByText('claude-haiku-4-5')).toBeInTheDocument();
  });

  it('빈 상태 노드 텍스트를 표시한다 (도구/서브에이전트/미들웨어/스킬)', async () => {
    renderCanvas();
    expect(await screen.findByText('도구가 설정되지 않았습니다')).toBeInTheDocument();
    expect(screen.getByText('No sub-agents')).toBeInTheDocument();
    expect(screen.getByText('미들웨어 없음')).toBeInTheDocument();
    expect(screen.getByText('스킬이 설정되지 않았습니다')).toBeInTheDocument();
  });

  it('"기본 레이아웃" 버튼 클릭이 동작한다 (크래시 없음)', async () => {
    renderCanvas();
    const resetBtn = await screen.findByRole('button', { name: '↻ 기본 레이아웃' });
    await userEvent.click(resetBtn);
    expect(resetBtn).toBeInTheDocument();
  });
});
