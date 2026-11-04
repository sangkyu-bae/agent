// Design Ref: agent-run-tool-trace §5.1 — 답변 아래 접이식 "도구 실행 내역 (N)".
// 기본 접힘: 2026-05 agent-chat-reasoning-display 의 가독성 판단을 지키며 필요할 때만 펼친다.
import { useId, useState } from 'react';
import { ChevronRight } from 'lucide-react';

import type { ToolTrace } from '@/types/toolTrace';
import { cn } from '@/utils/cn';
import { countTools } from '@/utils/toolTraceFormat';
import ToolTraceEntry from './ToolTraceEntry';

interface ToolTraceListProps {
  trace: ToolTrace;
}

const ToolTraceList = ({ trace }: ToolTraceListProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const panelId = useId();
  const toolCount = countTools(trace);
  // Plan FR-12 — 도구 호출이 없으면 영역을 그리지 않는다.
  if (toolCount === 0) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={panelId}
        onClick={() => setIsOpen((open) => !open)}
        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-fg-muted transition-colors duration-150 hover:bg-surface-sunken hover:text-fg"
      >
        <ChevronRight
          className={cn('h-4 w-4 transition-transform duration-150', isOpen && 'rotate-90')}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        도구 실행 내역 ({toolCount})
      </button>
      {isOpen && (
        <div id={panelId} className="mt-1.5 rounded-xl border border-border bg-surface-muted p-2">
          <ul className="space-y-0.5">
            {trace.items.map((item) => (
              <ToolTraceEntry key={item.seq} item={item} />
            ))}
          </ul>
          {trace.omitted_count > 0 && (
            <p className="px-2 pt-1 text-xs text-fg-subtle">
              외 {trace.omitted_count}건은 표시하지 않았습니다
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default ToolTraceList;
