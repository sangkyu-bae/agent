import { describe, expect, it } from 'vitest';

import { agentStepsToToolEvents } from './agentStepToToolEvent';
import type { AgentRunStep } from '@/hooks/useAgentRunStream';

describe('agentStepsToToolEvents', () => {
  it('returns empty array for empty input', () => {
    expect(agentStepsToToolEvents([])).toEqual([]);
  });

  it('filters out node steps (Q2: tool만 표기)', () => {
    const steps: AgentRunStep[] = [
      { kind: 'node', name: 'supervisor' },
      { kind: 'node', name: 'quality_gate' },
      { kind: 'tool', name: 'tavily_search' },
    ];
    const out = agentStepsToToolEvents(steps);
    expect(out).toHaveLength(1);
    expect(out[0].toolName).toBe('tavily_search');
  });

  it('marks tool with no durationMs as started', () => {
    const steps: AgentRunStep[] = [
      { kind: 'tool', name: 'tavily_search' },
    ];
    expect(agentStepsToToolEvents(steps)).toEqual([
      { kind: 'started', toolName: 'tavily_search', durationMs: undefined },
    ]);
  });

  it('marks tool with durationMs as completed and carries durationMs', () => {
    const steps: AgentRunStep[] = [
      { kind: 'tool', name: 'tavily_search', durationMs: 1234 },
    ];
    expect(agentStepsToToolEvents(steps)).toEqual([
      { kind: 'completed', toolName: 'tavily_search', durationMs: 1234 },
    ]);
  });

  it('preserves order across mixed input', () => {
    const steps: AgentRunStep[] = [
      { kind: 'node', name: 'supervisor' },
      { kind: 'tool', name: 'a' },
      { kind: 'node', name: 'quality_gate' },
      { kind: 'tool', name: 'b', durationMs: 50 },
      { kind: 'tool', name: 'c' },
    ];
    const out = agentStepsToToolEvents(steps);
    expect(out.map((e) => e.toolName)).toEqual(['a', 'b', 'c']);
    expect(out.map((e) => e.kind)).toEqual(['started', 'completed', 'started']);
  });

  // agent-chat-reasoning-display Design §5.3
  it('passes reasoning step through with kind=reasoning and text', () => {
    const steps: AgentRunStep[] = [
      { kind: 'node', name: 'supervisor' },
      {
        kind: 'reasoning',
        name: 'supervisor',
        text: '검색이 필요합니다',
        nextWorker: 'search_agent',
      },
      { kind: 'tool', name: 'rag_search' },
    ];
    expect(agentStepsToToolEvents(steps)).toEqual([
      {
        kind: 'reasoning',
        toolName: 'supervisor',
        text: '검색이 필요합니다',
      },
      { kind: 'started', toolName: 'rag_search', durationMs: undefined },
    ]);
  });
});
