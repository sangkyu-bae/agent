/**
 * useChatStream — General Chat 실시간 토큰 스트리밍 hook.
 *
 * Wraps the generic `useWebSocket` and:
 *   - Builds the WS URL via `wsUrl()` with access token
 *   - Sends the initial `subscribe` payload on open
 *   - Maps incoming `ChatMessage`s into a small UI-friendly state machine
 *   - Detects replay (`metadata.cached === true`) for Q3 "이어보기" UX
 *
 * ws-chat-streaming Design §5.2.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { WS_ENDPOINTS } from '@/constants/api';
import { useAuthStore } from '@/store/authStore';
import { useWebSocket, type WebSocketStatus } from '@/hooks/useWebSocket';
import type { ChatMessage, ChatSource, WSEnvelope } from '@/types/websocket';
import { wsUrl } from '@/utils/wsUrl';

// ChatPage 등에서 동일 심볼을 소비하므로 re-export.
export type { ChatSource };

export interface ChatToolEvent {
  kind: 'started' | 'completed' | 'reasoning';
  toolName: string;
  preview?: string;
  durationMs?: number;
  // agent-chat-reasoning-display Design §3.3 — reasoning kind 전용
  text?: string;
}

export interface ChatStreamState {
  status: WebSocketStatus;
  tokens: string;
  toolEvents: ChatToolEvent[];
  answer: string | null;
  sources: ChatSource[];
  wasSummarized: boolean;
  // agent-eval-gate — 저장된 assistant 메시지 id (평가 대상). 부재 시 평가 미노출.
  assistantMessageId: number | null;
  error: { code: string; message: string } | null;
  isDone: boolean;
  isReplayed: boolean;
  // chatpage-rerequest-stale-state-fix Design §3.2 — 현재 state 가 어떤 stream 의 것인지
  streamId: string;
}

export interface UseChatStreamOptions {
  // chatpage-rerequest-stale-state-fix Design §3.2 — 매 send 마다 신규 발급되는 stream lifecycle id
  streamId?: string;
  sessionId: string;
  message: string;
  topK?: number;
  enabled?: boolean;
}

const INITIAL_STATE: Omit<ChatStreamState, 'streamId'> = {
  status: 'idle',
  tokens: '',
  toolEvents: [],
  answer: null,
  sources: [],
  wasSummarized: false,
  assistantMessageId: null,
  error: null,
  isDone: false,
  isReplayed: false,
};

export function useChatStream(opts: UseChatStreamOptions): ChatStreamState {
  const { streamId = '', sessionId, message, topK, enabled = true } = opts;
  const accessToken = useAuthStore((s) => s.accessToken);

  const [state, setState] = useState<ChatStreamState>({ ...INITIAL_STATE, streamId: '' });

  // chatpage-rerequest-stale-state-fix Design §3.2 — Adjusting state while rendering.
  // 새 streamId 가 부여되면 같은 render 안에서 INITIAL 로 동기 리셋한다.
  // React: render body 의 setState 는 같은 컴포넌트에 한해 안전한 패턴이며,
  // 다음 render 의 view 계산이 즉시 새 INITIAL 값을 보게 된다.
  if (enabled && streamId && streamId !== state.streamId) {
    setState({ ...INITIAL_STATE, streamId });
  }

  // Latest subscribe payload — ref so onOpen always uses current values.
  const subscribeRef = useRef({ message, topK });
  subscribeRef.current = { message, topK };

  const handleMessage = useCallback((raw: { type: string; data?: unknown; metadata?: WSEnvelope['metadata'] }) => {
    const cached = Boolean((raw as WSEnvelope).metadata?.cached);
    const msg = raw as unknown as ChatMessage;
    switch (msg.type) {
      case 'chat_started':
        // Cached marker — replay 시 표시 가능
        if (cached) {
          setState((s) => ({ ...s, isReplayed: true }));
        }
        break;
      case 'chat_token': {
        // fix-chat-reasoning-object-render: chunk가 비정상(객체/배열)으로 와도
        // 문자열 결합으로 "[object Object]"가 새지 않도록 string 가드(2차 안전망).
        const chunk = typeof msg.data.chunk === 'string' ? msg.data.chunk : '';
        setState((s) => ({ ...s, tokens: s.tokens + chunk }));
        break;
      }
      case 'chat_step_reasoning':
        // agent-chat-reasoning-display Design §5.3
        setState((s) => ({
          ...s,
          toolEvents: [
            ...s.toolEvents,
            {
              kind: 'reasoning',
              toolName: msg.data.step_name,
              text: msg.data.reasoning,
            },
          ],
        }));
        break;
      case 'chat_tool_started':
        setState((s) => ({
          ...s,
          toolEvents: [
            ...s.toolEvents,
            { kind: 'started', toolName: msg.data.tool_name, preview: msg.data.input_preview },
          ],
        }));
        break;
      case 'chat_tool_completed':
        setState((s) => ({
          ...s,
          toolEvents: [
            ...s.toolEvents,
            {
              kind: 'completed',
              toolName: msg.data.tool_name,
              preview: msg.data.output_preview,
              durationMs: msg.data.duration_ms,
            },
          ],
        }));
        break;
      case 'chat_answer_completed':
        setState((s) => ({
          ...s,
          answer: msg.data.answer,
          sources: msg.data.sources ?? [],
          wasSummarized: Boolean(msg.data.was_summarized),
          assistantMessageId: msg.data.assistant_message_id ?? null,
        }));
        break;
      case 'chat_done':
        setState((s) => ({ ...s, isDone: true }));
        break;
      case 'chat_failed':
        setState((s) => ({ ...s, error: msg.data, isDone: true }));
        break;
      default:
        break;
    }
  }, []);

  const { connect, disconnect, send, status } = useWebSocket({
    reconnect: false,
    onMessage: handleMessage,
    onOpen: () => {
      const { message: m, topK: t } = subscribeRef.current;
      send({ type: 'subscribe', message: m, top_k: t });
    },
  });

  useEffect(() => {
    setState((s) => (s.status === status ? s : { ...s, status }));
  }, [status]);

  useEffect(() => {
    // chatpage-rerequest-stale-state-fix Design §3.2 — streamId deps 로 매 send 재연결 보장.
    // 상태 리셋은 render 단계에서 이미 처리되었으므로 여기서는 connect 만 담당.
    if (!enabled || !accessToken || !sessionId || !streamId) return;
    const url = wsUrl(WS_ENDPOINTS.WS_CHAT(sessionId), { token: accessToken });
    connect(url);
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, accessToken, sessionId, streamId]);

  return state;
}
