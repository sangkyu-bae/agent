// Design Ref: agent-run-tool-trace §2.2 — 재진입 시 메시지 이력에 세션 도구 실행 내역을 붙인다.
// sessionSources.ts 와 같은 규칙: assistant 메시지 id 로만 병합, 없으면 메시지를 그대로 둔다.
import type { Message } from '@/types/chat';
import type { SessionToolTracesResponse, ToolTrace } from '@/types/toolTrace';
import { countTools } from './toolTraceFormat';

export type SessionToolTraceMap = Record<string, ToolTrace>;

export const toSessionToolTraceMap = (res: SessionToolTracesResponse): SessionToolTraceMap =>
  Object.fromEntries(res.items.map((item) => [String(item.message_id), item.tool_trace]));

export const attachSessionToolTraces = (
  messages: Message[],
  traces: SessionToolTraceMap,
): Message[] =>
  messages.map((message) => {
    const found = message.role === 'assistant' ? traces[message.id] : undefined;
    return found && countTools(found) > 0 ? { ...message, toolTrace: found } : message;
  });
