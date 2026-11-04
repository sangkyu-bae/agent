// Design Ref: agent-run-tool-trace §3.1, §4.2 — 백엔드 ToolTrace wire 형태.
// wire 값은 백엔드 StrEnum(tool_trace_policy.py)과 같다. 변경은 계약 변경이다.

export const TOOL_TRACE_KIND = {
  REASONING: 'reasoning',
  TOOL: 'tool',
} as const;
export type ToolTraceKind = (typeof TOOL_TRACE_KIND)[keyof typeof TOOL_TRACE_KIND];

export const TOOL_TRACE_STATUS = {
  SUCCESS: 'success',
  FAILED: 'failed',
  /** Check G-01 — 시작만 기록되고 종료 기록이 없는 호출. 실패로 단정하지 않는다. */
  INCOMPLETE: 'incomplete',
} as const;
export type ToolTraceStatus = (typeof TOOL_TRACE_STATUS)[keyof typeof TOOL_TRACE_STATUS];

export const TOOL_TRACE_SOURCE = {
  INTERNAL: 'internal',
  MCP: 'mcp',
} as const;
export type ToolTraceSource = (typeof TOOL_TRACE_SOURCE)[keyof typeof TOOL_TRACE_SOURCE];

/** 항목마다 있는 필드가 다르다. 서버는 None·false 키를 싣지 않는다. */
export interface ToolTraceItem {
  seq: number;
  kind: ToolTraceKind;
  label: string;
  /** 서브에이전트 소속 워커 라벨 */
  worker?: string;
  /** kind=reasoning 전용 */
  text?: string;
  source?: ToolTraceSource;
  status?: ToolTraceStatus;
  requires_approval?: boolean;
  duration_ms?: number;
  input?: Record<string, unknown>;
  input_truncated?: boolean;
  output?: string;
  output_truncated?: boolean;
  error?: string;
}

export interface ToolTrace {
  omitted_count: number;
  items: ToolTraceItem[];
}

/** GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/tool-traces 응답 */
export interface SessionToolTracesResponse {
  session_id: string;
  items: { message_id: number; tool_trace: ToolTrace }[];
}
