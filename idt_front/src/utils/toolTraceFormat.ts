// Design Ref: agent-run-tool-trace §5.3 — 도구 입력·결과 표시 정리 (순수 함수).
// 2026-05 agent-chat-reasoning-display 가 raw JSON 을 뺀 이유(가독성)를 정리된 표시로 해결한다.
import { TOOL_TRACE_KIND, type ToolTrace } from '@/types/toolTrace';

export interface InputLine {
  key: string;
  value: string;
}

export interface FormattedOutput {
  text: string;
  /** 객체·배열 JSON 으로 해석되어 들여쓰기로 정리됐는지 */
  isJson: boolean;
}

const stringifyValue = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value) ?? String(value);

export const formatInputLines = (input: Record<string, unknown> | undefined): InputLine[] =>
  Object.entries(input ?? {}).map(([key, value]) => ({ key, value: stringifyValue(value) }));

export const rawInput = (input: Record<string, unknown> | undefined): string =>
  input ? JSON.stringify(input) : '';

export const formatOutput = (output: string | undefined): FormattedOutput => {
  const text = output ?? '';
  const trimmed = text.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return { text: JSON.stringify(JSON.parse(trimmed), null, 2), isJson: true };
    } catch {
      // 저장 한도(1KB) 절단으로 JSON 이 깨진 결과 — 텍스트로 둔다.
    }
  }
  return { text, isJson: false };
};

export const formatDuration = (ms: number | undefined): string | null => {
  if (typeof ms !== 'number') return null;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
};

export const countTools = (trace: ToolTrace): number =>
  trace.items.filter((item) => item.kind === TOOL_TRACE_KIND.TOOL).length;
