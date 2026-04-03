import { useRef, useCallback } from 'react';
import type { StreamEvent } from '@/types/api';

interface UseStreamOptions {
  onDelta?: (delta: string) => void;
  onDone?: () => void;
  onError?: (error: string) => void;
  onToolCall?: (data: string) => void;
}

export const useStream = (options: UseStreamOptions) => {
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback((url: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: StreamEvent = JSON.parse(e.data);
        switch (event.event) {
          case 'delta':
            options.onDelta?.(event.data);
            break;
          case 'done':
            options.onDone?.();
            es.close();
            break;
          case 'error':
            options.onError?.(event.data);
            es.close();
            break;
          case 'tool_call':
            options.onToolCall?.(event.data);
            break;
        }
      } catch {
        // parse error 무시
      }
    };

    es.onerror = () => {
      options.onError?.('스트림 연결 오류');
      es.close();
    };
  }, [options]);

  const disconnect = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  return { connect, disconnect };
};
