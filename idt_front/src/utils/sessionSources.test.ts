import { describe, expect, it } from 'vitest';

import type { DocumentSource, Message } from '@/types/chat';
import { attachSessionSources, toSessionSourceMap } from './sessionSources';

const doc: DocumentSource = { kind: 'document', source: 'a.pdf', content: '발췌', chunk_id: 'd1' };

const message = (id: string, role: Message['role']): Message => ({
  id, role, content: 'x', createdAt: '2026-11-03T00:00:00Z',
});

describe('toSessionSourceMap', () => {
  it('message_id 를 문자열 키로 바꾼다', () => {
    expect(
      toSessionSourceMap({ session_id: 's1', items: [{ message_id: 2, sources: [doc] }] }),
    ).toEqual({ '2': [doc] });
  });
});

describe('attachSessionSources', () => {
  it('assistant 메시지에만 근거를 붙인다', () => {
    const merged = attachSessionSources(
      [message('1', 'user'), message('2', 'assistant')],
      { '1': [doc], '2': [doc] },
    );
    expect(merged[0].sources).toBeUndefined();
    expect(merged[1].sources).toEqual([doc]);
  });

  it('근거가 없거나 빈 목록이면 메시지를 그대로 둔다', () => {
    const original = [message('2', 'assistant'), message('4', 'assistant')];
    const merged = attachSessionSources(original, { '4': [] });
    expect(merged).toEqual(original);
    expect(merged[0]).toBe(original[0]);
  });
});
