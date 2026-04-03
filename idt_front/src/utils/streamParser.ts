import type { StreamEvent } from '@/types/api';

export const parseStreamLine = (line: string): StreamEvent | null => {
  if (!line.startsWith('data: ')) return null;
  try {
    return JSON.parse(line.slice(6)) as StreamEvent;
  } catch {
    return null;
  }
};

export const createFetchStream = async (
  url: string,
  options: RequestInit,
  onChunk: (event: StreamEvent) => void,
  onDone: () => void
) => {
  const response = await fetch(url, { ...options, headers: { Accept: 'text/event-stream', ...options.headers } });
  if (!response.body) throw new Error('ReadableStream not supported');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) { onDone(); break; }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      const event = parseStreamLine(line.trim());
      if (event) onChunk(event);
    }
  }
};
