import { useState } from 'react';
import { useComposeAgent } from '@/hooks/useAgentComposer';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { LlmModel } from '@/types/llmModel';
import type {
  ComposeAgentDraftResponse,
  ComposeHistoryTurn,
  FixChatMessage,
} from '@/types/agentComposer';
import ComposeDraftCard from './ComposeDraftCard';

interface FixAgentPanelProps {
  mode: 'create' | 'edit';
  form: AgentBuilderFormData;
  models?: LlmModel[];
  onApplyDraft: (draft: ComposeAgentDraftResponse) => void;
}

/** 시안(docs/img/fix_agent.png)의 빈 상태 예시 프롬프트 */
const EXAMPLE_PROMPTS = [
  'tavily 검색 도구 추가해줘',
  'todo로 작업 관리할 수 있는 기능 추가해줘',
  '시스템 프롬프트를 구조화된 프롬프트로 압축해 개선해줘',
];

const MAX_HISTORY_TURNS = 6;
const MAX_USER_REQUEST_CHARS = 1000;

/** assistant 초안 턴을 history용 요약 텍스트로 변환 (카드 JSON 미전송 — Design §4.4). */
const summarizeDraft = (m: FixChatMessage): string => {
  const d = m.draft!;
  const tools = d.tool_ids.length > 0 ? d.tool_ids.join(', ') : '없음';
  return `초안(coverage: ${d.coverage}) — 이름: ${d.name_suggestion} / 도구: ${tools}${
    m.applied ? ' (적용됨)' : ''
  }`;
};

/**
 * Fix 에이전트 탭 — 채팅으로 compose를 호출하고 초안 카드를 표시한다.
 * 대화는 로컬 state (compose 무저장 원칙, TestChatView와 동일 정책).
 */
const FixAgentPanel = ({ mode, form, models, onApplyDraft }: FixAgentPanelProps) => {
  const [messages, setMessages] = useState<FixChatMessage[]>([]);
  const [input, setInput] = useState('');
  const composeMutation = useComposeAgent();
  const isPending = composeMutation.isPending;

  const buildHistory = (): ComposeHistoryTurn[] =>
    messages
      .filter((m) => !m.isError)
      .map<ComposeHistoryTurn>((m) => ({
        role: m.role,
        content: m.draft ? summarizeDraft(m) : m.content,
      }))
      .slice(-MAX_HISTORY_TURNS);

  const handleSend = () => {
    const text = input.trim().slice(0, MAX_USER_REQUEST_CHARS);
    if (!text || isPending) return;

    const history = buildHistory();
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: text },
    ]);
    setInput('');

    composeMutation.mutate(
      {
        user_request: text,
        name: form.name || null,
        current_config: {
          name: form.name || null,
          system_prompt: form.systemPrompt || null,
          tool_ids: form.tools,
          llm_model_id:
            models?.find((m) => m.model_name === form.model)?.id ?? null,
          temperature: form.temperature,
        },
        history: history.length > 0 ? history : null,
      },
      {
        onSuccess: (draft) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: draft.notes || '초안을 생성했습니다.',
              draft,
            },
          ]);
        },
        onError: (error) => {
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: `⚠ 초안 생성에 실패했습니다: ${error.message}`,
              isError: true,
            },
          ]);
        },
      },
    );
  };

  const handleNewChat = () => {
    setMessages([]);
    setInput('');
  };

  const handleApply = (messageId: string, draft: ComposeAgentDraftResponse) => {
    onApplyDraft(draft);
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, applied: true } : m)),
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 새 대화 */}
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
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-full border-2 border-dashed border-violet-300">
              <svg className="h-9 w-9 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
              </svg>
            </div>
            <p className="text-[17px] font-bold text-zinc-900">
              {mode === 'edit' && form.name ? `${form.name} 수정` : '새 에이전트 수정'}
            </p>
            <p className="mt-1.5 text-[13px] text-zinc-400">자연어로 에이전트를 수정하세요</p>
            <div className="mt-5 space-y-1.5">
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setInput(p)}
                  className="block w-full text-[12.5px] text-zinc-500 transition-colors hover:text-violet-600"
                >
                  &ldquo;{p}&rdquo;
                </button>
              ))}
            </div>
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
              ) : m.draft ? (
                <ComposeDraftCard
                  key={m.id}
                  draft={m.draft}
                  mode={mode}
                  currentToolIds={form.tools}
                  applied={!!m.applied}
                  modelUnresolved={
                    !!models && !models.some((mm) => mm.id === m.draft!.llm_model_id)
                  }
                  onApply={() => handleApply(m.id, m.draft!)}
                />
              ) : (
                <div
                  key={m.id}
                  className={`text-[14px] leading-[1.8] ${m.isError ? 'text-red-500' : 'text-zinc-800'}`}
                >
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              ),
            )}
            {isPending && (
              <div className="flex items-center gap-1.5 py-1" aria-label="초안 생성 중">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400" />
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
            disabled={isPending}
            placeholder="에이전트를 어떻게 수정할지 설명하세요..."
            rows={2}
            aria-label="Fix 에이전트 입력"
            className="block w-full resize-none bg-transparent px-4 py-3 text-[14px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none disabled:cursor-not-allowed disabled:bg-zinc-50"
          />
        </div>
        <p className="mt-1.5 text-center text-[11px] text-zinc-400">
          Enter로 전송, Shift + Enter로 줄바꿈
        </p>
      </div>
    </div>
  );
};

export default FixAgentPanel;
