import { describe, expect, it } from 'vitest';

import { toAgentSummary } from '@/services/agentSubscriptionService';
import type { AgentSourceType, MyAgent } from '@/types/agent';

const makeAgent = (source_type: AgentSourceType): MyAgent => ({
  agent_id: 'agent-1',
  name: '여신 상담봇',
  description: '설명',
  source_type,
  visibility: 'private',
  temperature: 0.3,
  owner_user_id: 'user-1',
  forked_from: source_type === 'forked' ? 'agent-0' : null,
  is_pinned: false,
  created_at: '2026-11-01T00:00:00',
});

describe('toAgentSummary canEdit (agent-edit-entry FR-08)', () => {
  it.each<[AgentSourceType, boolean]>([
    ['owned', true],
    ['forked', true],
    ['subscribed', false],
  ])('U5: source_type=%s → canEdit=%s', (sourceType, expected) => {
    expect(toAgentSummary(makeAgent(sourceType)).canEdit).toBe(expected);
  });
});
