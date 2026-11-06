import { describe, expect, it } from 'vitest';

import type { Message } from '@/types/chat';
import type { ToolTrace } from '@/types/toolTrace';
import { attachSessionToolTraces, toSessionToolTraceMap } from './sessionToolTraces';

const trace: ToolTrace = {
  omitted_count: 0,
  items: [{ seq: 1, kind: 'tool', label: 'list_inquiries', status: 'success' }],
};
const reasoningOnly: ToolTrace = {
  omitted_count: 0,
  items: [{ seq: 1, kind: 'reasoning', label: '판단', text: 'A' }],
};

const message = (id: string, role: Message['role']): Message => ({
  id, role, content: 'x', createdAt: '2026-11-03T00:00:00Z',
});

describe('toSessionToolTraceMap', () => {
  it('message_id 를 문자열 키로 바꾼다', () => {
    expect(
      toSessionToolTraceMap({ session_id: 's1', items: [{ message_id: 2, tool_trace: trace }] }),
    ).toEqual({ '2': trace });
  });
});

describe('attachSessionToolTraces', () => {
  it('assistant 메시지에만 붙인다', () => {
    const merged = attachSessionToolTraces(
      [message('1', 'user'), message('2', 'assistant')],
      { '1': trace, '2': trace },
    );
    expect(merged[0].toolTrace).toBeUndefined();
    expect(merged[1].toolTrace).toEqual(trace);
  });

  it('도구가 없는 내역이나 없는 키는 메시지를 그대로 둔다', () => {
    const original = [message('2', 'assistant'), message('4', 'assistant')];
    const merged = attachSessionToolTraces(original, { '2': reasoningOnly });
    expect(merged).toEqual(original);
    expect(merged[0]).toBe(original[0]);
  });

  it('근거 병합과 함께 써도 서로 덮지 않는다', () => {
    const withSources: Message = {
      ...message('2', 'assistant'),
      sources: [{ kind: 'mcp', source: '도구', content: '발췌', chunk_id: 'c1' }],
    };
    const [merged] = attachSessionToolTraces([withSources], { '2': trace });
    expect(merged.sources).toEqual(withSources.sources);
    expect(merged.toolTrace).toEqual(trace);
  });
});
