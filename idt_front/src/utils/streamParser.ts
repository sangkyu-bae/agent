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

/* ────────────────────────────────────────────────────────────────────────
 * 이벤트 이름을 보존하는 SSE (agent-create-wizard Design §3.5)
 *
 * 위의 `createFetchStream` 은 `data:` 줄만 읽고 `event:` 이름을 버린다 —
 * 델타 텍스트 스트림에는 충분하지만, 파이프라인 SSE 는
 * stage_started / stage_completed / stage_failed / pipeline_result 로
 * **분기**해야 하므로 이름이 필요하다. 페이로드 모양으로 추측하는 방식은
 * stage_started 와 stage_completed 를 구분하지 못해 채택하지 않았다.
 * ──────────────────────────────────────────────────────────────────────── */

/** 이름이 붙은 SSE 이벤트 1건. */
export interface NamedStreamEvent<T = unknown> {
  event: string;
  id: number | null;
  data: T;
}

/**
 * SSE 블록(빈 줄로 구분되는 `event:`/`id:`/`data:` 묶음) 1개를 파싱한다.
 *
 * `: heartbeat` 같은 주석 라인만 있는 블록과 `data:` 가 없는 블록은 null 이다
 * (서버가 15초마다 heartbeat 를 흘린다).
 */
export const parseSseBlock = <T = unknown>(
  block: string,
): NamedStreamEvent<T> | null => {
  let event = '';
  let id: number | null = null;
  let raw: string | null = null;

  for (const line of block.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(':')) continue;
    if (trimmed.startsWith('event:')) event = trimmed.slice(6).trim();
    else if (trimmed.startsWith('id:')) {
      const parsed = Number(trimmed.slice(3).trim());
      id = Number.isNaN(parsed) ? null : parsed;
    } else if (trimmed.startsWith('data:')) raw = trimmed.slice(5).trim();
  }

  if (raw === null || !event) return null;
  try {
    return { event, id, data: JSON.parse(raw) as T };
  } catch {
    return null;
  }
};

/**
 * POST + 본문으로 SSE 를 소비한다 — 이름이 붙은 이벤트를 콜백으로 밀어준다.
 *
 * EventSource 를 쓰지 않는 이유: 입력이 본문이라 query 로 못 싣고, 헤더 인증도
 * 불가능하다. 인증 헤더는 호출자가 `options.headers` 로 넣는다.
 *
 * @throws 스트림이 열리기 전의 실패(4xx/5xx)는 여기서 Error 로 던진다 —
 *   호출자가 404(킬스위치 off)와 401 을 구분해야 하므로 status 를 메시지에
 *   싣고 `status` 프로퍼티로도 노출한다.
 */
export const createEventFetchStream = async (
  url: string,
  options: RequestInit,
  onEvent: (event: NamedStreamEvent) => void,
  onDone: () => void,
): Promise<void> => {
  const response = await fetch(url, {
    ...options,
    headers: { Accept: 'text/event-stream', ...options.headers },
  });

  if (!response.ok) {
    const error = new Error(`SSE request failed with status ${response.status}`);
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }
  if (!response.body) throw new Error('ReadableStream not supported');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      // 마지막 블록에 종결 빈 줄이 없을 수 있다 — 남은 버퍼를 흘려보낸다.
      const tail = parseSseBlock(buffer);
      if (tail) onEvent(tail);
      onDone();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (parsed) onEvent(parsed);
    }
  }
};
