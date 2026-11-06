// agent-run-source-citations §2.2 — 재진입 시 메시지 이력에 세션 근거를 붙인다.
import type { DocumentSource, Message, SessionSourcesResponse } from '@/types/chat';

export type SessionSourceMap = Record<string, DocumentSource[]>;

export const toSessionSourceMap = (res: SessionSourcesResponse): SessionSourceMap =>
  Object.fromEntries(res.items.map((item) => [String(item.message_id), item.sources]));

export const attachSessionSources = (
  messages: Message[],
  sources: SessionSourceMap,
): Message[] =>
  messages.map((message) => {
    const found = message.role === 'assistant' ? sources[message.id] : undefined;
    return found && found.length > 0 ? { ...message, sources: found } : message;
  });
