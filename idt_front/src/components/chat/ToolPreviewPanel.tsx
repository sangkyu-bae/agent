/**
 * ToolPreviewPanel — 추론 진행 + 도구 호출 표시 패널 (토글 가능).
 *
 * agent-chat-reasoning-display Design §5.1 — JSON preview는 렌더하지 않는다 (FR-04).
 * 토글 카운트는 tool 개수만 사용 (FR-06).
 * visible 상태는 외부에서 주입 (Zustand `chatPreferencesStore`에서 관리).
 */
import type { ChatToolEvent } from '@/hooks/useChatStream';

export interface ToolPreviewPanelProps {
  events: ChatToolEvent[];
  visible: boolean;
  onToggleVisible?: (next: boolean) => void;
}

const ToolPreviewPanel = ({
  events,
  visible,
  onToggleVisible,
}: ToolPreviewPanelProps) => {
  if (events.length === 0) return null;

  const toolCount = events.filter((e) => e.kind !== 'reasoning').length;

  if (!visible) {
    return (
      <button
        type="button"
        className="text-xs text-zinc-500 underline"
        onClick={() => onToggleVisible?.(true)}
      >
        추론 진행 보기 ({toolCount})
      </button>
    );
  }

  return (
    <aside className="rounded border border-zinc-200 bg-zinc-50 p-3 text-xs space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-zinc-700">추론 진행</h4>
        <button
          type="button"
          className="text-zinc-500 hover:text-zinc-700"
          onClick={() => onToggleVisible?.(false)}
        >
          숨기기
        </button>
      </div>
      <ul className="space-y-1">
        {events.map((e, i) => {
          if (e.kind === 'reasoning') {
            const text = e.text?.trim();
            if (!text) return null;
            return (
              <li key={i} className="flex items-start gap-2">
                <span aria-hidden="true">💭</span>
                <span className="text-zinc-600">{text}</span>
              </li>
            );
          }
          return (
            <li key={i} className="flex items-center gap-2">
              <span
                className={
                  e.kind === 'started' ? 'text-amber-600' : 'text-emerald-600'
                }
                aria-hidden="true"
              >
                {e.kind === 'started' ? '⏳' : '✓'}
              </span>
              <span className="font-mono">{e.toolName}</span>
              {e.durationMs !== undefined && (
                <span className="text-zinc-400">{e.durationMs}ms</span>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
};

export default ToolPreviewPanel;
