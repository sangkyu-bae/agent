/**
 * ToolPreviewPanel — 추론 진행 + 도구 호출 표시 패널 (토글 가능).
 *
 * agent-chat-reasoning-display Design §5.1 — JSON preview는 렌더하지 않는다 (FR-04).
 * 토글 카운트는 tool 개수만 사용 (FR-06).
 * visible 상태는 외부에서 주입 (Zustand `chatPreferencesStore`에서 관리).
 * Design Ref: ui-redesign-chat §5.4 — 토큰·lucide 아이콘. 로직 변경 없음.
 */
import { Check, Lightbulb, Loader2 } from 'lucide-react';
import Button from '@/components/ui/Button';
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
      <Button variant="ghost" size="sm" onClick={() => onToggleVisible?.(true)}>
        추론 진행 보기 ({toolCount})
      </Button>
    );
  }

  return (
    <aside className="space-y-2 rounded-xl border border-border bg-surface-muted p-3 text-sm">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-fg">추론 진행</h4>
        <Button variant="ghost" size="sm" onClick={() => onToggleVisible?.(false)}>
          숨기기
        </Button>
      </div>
      <ul className="space-y-1">
        {events.map((e, i) => {
          if (e.kind === 'reasoning') {
            const text = e.text?.trim();
            if (!text) return null;
            return (
              <li key={i} className="flex items-start gap-2">
                <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden="true" />
                <span className="text-fg-muted">{text}</span>
              </li>
            );
          }
          const started = e.kind === 'started';
          return (
            <li key={i} className="flex items-center gap-2">
              {started ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-warning" strokeWidth={2} aria-hidden="true" />
              ) : (
                <Check className="h-4 w-4 shrink-0 text-success" strokeWidth={2} aria-hidden="true" />
              )}
              <span className="font-mono text-xs text-fg">{e.toolName}</span>
              {e.durationMs !== undefined && (
                <span className="text-xs text-fg-subtle">{e.durationMs}ms</span>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
};

export default ToolPreviewPanel;
