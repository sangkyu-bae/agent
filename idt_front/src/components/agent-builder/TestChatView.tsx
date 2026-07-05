import { useEffect, useState } from 'react';
import { useAgentRunStream } from '@/hooks/useAgentRunStream';
import type { TestChatMessage } from '@/types/agentBuilder';

interface TestChatViewProps {
  mode: 'create' | 'edit';
  agentId: string | null;
  agentName: string;
}

interface ActiveRun {
  streamId: string;
  runId: string;
  query: string;
}

/**
 * 우측 테스트 패널의 대화 뷰.
 * - edit 모드(저장된 agent_id)에서만 useAgentRunStream으로 실시간 테스트.
 * - create 모드에서는 입력을 비활성화하고 안내를 표시한다 (Design §5.5).
 */
const TestChatView = ({ mode, agentId, agentName }: TestChatViewProps) => {
  const [messages, setMessages] = useState<TestChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [active, setActive] = useState<ActiveRun | null>(null);
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());

  const canTest = mode === 'edit' && !!agentId;

  const stream = useAgentRunStream({
    streamId: active?.streamId ?? '',
    runId: active?.runId ?? '',
    agentId: agentId ?? '',
    query: active?.query ?? '',
    sessionId,
    enabled: canTest && !!active,
  });

  // 스트림 완료 시 최종 답변을 메시지로 확정하고 active 해제.
  useEffect(() => {
    if (!active || stream.streamId !== active.streamId) return;
    if (!stream.isDone) return;
    const content = stream.error
      ? `⚠ 실행 실패: ${stream.error.message}`
      : stream.answer ?? stream.tokens;
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'assistant', content },
    ]);
    setActive(null);
  }, [active, stream.streamId, stream.isDone, stream.answer, stream.tokens, stream.error]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !canTest || active) return;
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: text },
    ]);
    setActive({ streamId: crypto.randomUUID(), runId: crypto.randomUUID(), query: text });
    setInput('');
  };

  const handleNewChat = () => {
    setSessionId(crypto.randomUUID());
    setMessages([]);
    setActive(null);
    setInput('');
  };

  const isStreaming = !!active && !stream.isDone;
  const liveText = isStreaming ? stream.tokens : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div className="flex shrink-0 justify-end px-4 py-2">
        <button
          type="button"
          onClick={handleNewChat}
          className="flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-[12.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" />
          </svg>
          새 대화
        </button>
      </div>

      {/* 대화 본문 */}
      <div style={{ flex: 1, overflowY: 'auto' }} className="px-4">
        {messages.length === 0 && !isStreaming ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border-2 border-dashed border-zinc-200">
              <svg className="h-8 w-8 text-zinc-300" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" />
              </svg>
            </div>
            <p className="text-[15px] font-semibold text-zinc-900">
              {agentName || '새 에이전트'} 테스트
            </p>
            <p className="mt-1 text-[13px] text-zinc-400">
              {canTest ? '에이전트와 대화를 시작하세요' : '저장 후 테스트할 수 있습니다'}
            </p>
          </div>
        ) : (
          <div className="space-y-4 py-4">
            {messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div
                    className="max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 text-[14px] leading-relaxed text-white"
                    style={{ background: 'linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%)' }}
                  >
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  </div>
                </div>
              ) : (
                <div key={m.id} className="text-[14px] leading-[1.8] text-zinc-800">
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              ),
            )}
            {isStreaming && (
              <div className="text-[14px] leading-[1.8] text-zinc-800">
                <p className="whitespace-pre-wrap">
                  {liveText}
                  <span className="ml-0.5 animate-pulse">▍</span>
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 입력창 */}
      <div className="shrink-0 px-4 pb-4 pt-2">
        <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-sm transition-all focus-within:border-violet-400">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={!canTest || isStreaming}
            placeholder={canTest ? '에이전트를 테스트해 보세요...' : '저장 후 테스트할 수 있습니다'}
            rows={2}
            aria-label="테스트 입력"
            className="block w-full resize-none bg-transparent px-4 py-3 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none disabled:cursor-not-allowed disabled:bg-zinc-50"
          />
        </div>
        <p className="mt-1.5 text-center text-[11px] text-zinc-400">Enter로 전송, Shift + Enter로 줄바꿈</p>
      </div>
    </div>
  );
};

export default TestChatView;
