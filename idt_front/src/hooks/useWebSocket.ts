import { useRef, useCallback, useEffect, useState } from 'react';

export type WebSocketStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

export interface WebSocketMessage {
  type: string;
  data?: unknown;
  [key: string]: unknown;
}

interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnect?: boolean;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
  autoConnect?: boolean;
}

interface UseWebSocketReturn {
  status: WebSocketStatus;
  isConnected: boolean;
  connect: (url: string) => void;
  disconnect: () => void;
  send: (message: WebSocketMessage | string) => void;
}

const DEFAULT_RECONNECT_DELAY = 3000;
const DEFAULT_MAX_RECONNECT_ATTEMPTS = 5;

export const useWebSocket = (options: UseWebSocketOptions = {}): UseWebSocketReturn => {
  const {
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnect = false,
    reconnectDelay = DEFAULT_RECONNECT_DELAY,
    maxReconnectAttempts = DEFAULT_MAX_RECONNECT_ATTEMPTS,
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const urlRef = useRef<string>('');
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(false);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    clearReconnectTimer();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, [clearReconnectTimer]);

  const connect = useCallback(
    (url: string) => {
      disconnect();
      urlRef.current = url;
      shouldReconnectRef.current = reconnect;
      reconnectCountRef.current = 0;

      const createWebSocket = () => {
        setStatus('connecting');
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          reconnectCountRef.current = 0;
          setStatus('connected');
          onOpen?.();
        };

        ws.onmessage = (event: MessageEvent) => {
          try {
            const parsed: WebSocketMessage = JSON.parse(event.data as string);
            onMessage?.(parsed);
          } catch {
            onMessage?.({ type: 'raw', data: event.data });
          }
        };

        ws.onclose = () => {
          wsRef.current = null;
          setStatus('disconnected');
          onClose?.();

          if (
            shouldReconnectRef.current &&
            reconnectCountRef.current < maxReconnectAttempts
          ) {
            reconnectCountRef.current += 1;
            const delay = reconnectDelay * reconnectCountRef.current;
            reconnectTimerRef.current = setTimeout(createWebSocket, delay);
          }
        };

        ws.onerror = (event: Event) => {
          setStatus('error');
          onError?.(event);
        };
      };

      createWebSocket();
    },
    [disconnect, reconnect, reconnectDelay, maxReconnectAttempts, onOpen, onMessage, onClose, onError],
  );

  const send = useCallback((message: WebSocketMessage | string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    const payload = typeof message === 'string' ? message : JSON.stringify(message);
    wsRef.current.send(payload);
  }, []);

  useEffect(() => {
    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      wsRef.current?.close();
    };
  }, [clearReconnectTimer]);

  return {
    status,
    isConnected: status === 'connected',
    connect,
    disconnect,
    send,
  };
};
