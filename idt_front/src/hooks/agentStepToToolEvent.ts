/**
 * agentStepsToToolEvents — `AgentRunStep[]` → `ChatToolEvent[]` 변환.
 *
 * Design ws-agent-chat-streaming §3.2 (Q2: tool만 표기).
 * agent-chat-reasoning-display §5.3 — reasoning step도 함께 통과.
 *
 * - node step(supervisor / quality_gate / final_answer)은 폐기.
 * - reasoning step은 kind='reasoning'으로 통과 (text 보존).
 * - tool step: durationMs가 있으면 'completed', 없으면 'started'.
 * - 순서 보존.
 */
import type { AgentRunStep } from '@/hooks/useAgentRunStream';
import type { ChatToolEvent } from '@/hooks/useChatStream';

export function agentStepsToToolEvents(steps: AgentRunStep[]): ChatToolEvent[] {
  return steps
    .filter((s) => s.kind === 'tool' || s.kind === 'reasoning')
    .map<ChatToolEvent>((s) => {
      if (s.kind === 'reasoning') {
        return { kind: 'reasoning', toolName: s.name, text: s.text };
      }
      return {
        kind: s.durationMs !== undefined ? 'completed' : 'started',
        toolName: s.name,
        durationMs: s.durationMs,
      };
    });
}
