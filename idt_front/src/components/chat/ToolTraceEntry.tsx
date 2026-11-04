// Design Ref: agent-run-tool-trace §5.3 — 도구 실행 내역 항목 1개 (추론 행 / 도구 행 + 드릴다운).
// 모든 값은 텍스트 노드로만 그린다 (마크다운·HTML 해석 금지, Design §7).
import { useId, useState } from 'react';
import { Check, ChevronRight, CircleDashed, Lightbulb, XCircle } from 'lucide-react';

import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import {
  TOOL_TRACE_KIND,
  TOOL_TRACE_SOURCE,
  TOOL_TRACE_STATUS,
  type ToolTraceItem,
} from '@/types/toolTrace';
import { cn } from '@/utils/cn';
import { formatDuration, formatInputLines, formatOutput, rawInput } from '@/utils/toolTraceFormat';

interface ToolTraceEntryProps {
  item: ToolTraceItem;
}

const ICON = 'h-4 w-4 shrink-0';
const CODE_BLOCK =
  'max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-2 font-mono text-xs text-fg-secondary';
const SECTION_LABEL = 'mb-1 text-xs font-medium text-fg-subtle';

// 상태는 아이콘과 텍스트를 함께 쓴다 (Plan FR-14). incomplete 는 Check G-01.
const STATUS_VIEW = {
  success: { Icon: Check, label: '성공', icon: 'text-success', text: 'text-fg-subtle' },
  failed: { Icon: XCircle, label: '실패', icon: 'text-danger', text: 'text-danger' },
  incomplete: { Icon: CircleDashed, label: '완료 기록 없음', icon: 'text-fg-subtle', text: 'text-fg-subtle' },
} as const;

const ReasoningRow = ({ item }: ToolTraceEntryProps) => (
  <li className="flex items-start gap-2 px-2 py-1">
    <Lightbulb className={cn(ICON, 'mt-0.5 text-fg-subtle')} strokeWidth={1.75} aria-hidden="true" />
    <div className="min-w-0 text-sm text-fg-muted">
      <span className="mr-1.5 font-medium text-fg-secondary">{item.label}</span>
      {item.worker && <Badge className="mr-1.5">{item.worker}</Badge>}
      <span className="whitespace-pre-wrap break-words">{item.text}</span>
    </div>
  </li>
);

const InputSection = ({ item, showRaw }: { item: ToolTraceItem; showRaw: boolean }) => {
  const lines = formatInputLines(item.input);
  return (
    <div>
      <p className={SECTION_LABEL}>입력</p>
      <div data-testid="tool-trace-input">
        {lines.length === 0 ? (
          <p className="text-xs text-fg-subtle">입력 없음</p>
        ) : showRaw ? (
          <pre className={CODE_BLOCK}>{rawInput(item.input)}</pre>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {lines.map((line) => (
              <div key={line.key} className="contents">
                <dt className="font-medium text-fg-muted">{line.key}</dt>
                <dd className="min-w-0 break-all font-mono text-fg-secondary">{line.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      {item.input_truncated && (
        <p className="mt-1 text-xs text-fg-subtle">저장 한도로 일부만 표시됩니다</p>
      )}
    </div>
  );
};

const OutputSection = ({ item, showRaw }: { item: ToolTraceItem; showRaw: boolean }) => {
  if (item.status === TOOL_TRACE_STATUS.FAILED) {
    return (
      <div>
        <p className={SECTION_LABEL}>오류</p>
        <p className="whitespace-pre-wrap break-words text-xs text-danger">
          {item.error ?? '도구 실행에 실패했습니다.'}
        </p>
      </div>
    );
  }
  if (item.status === TOOL_TRACE_STATUS.INCOMPLETE) {
    return (
      <div>
        <p className={SECTION_LABEL}>결과</p>
        <p className="text-xs text-fg-subtle">실행 완료가 기록되지 않아 결과를 표시할 수 없습니다</p>
      </div>
    );
  }
  const formatted = formatOutput(item.output);
  return (
    <div>
      <p className={SECTION_LABEL}>결과</p>
      <pre data-testid="tool-trace-output" className={CODE_BLOCK}>
        {showRaw ? item.output ?? '' : formatted.text || '결과 없음'}
      </pre>
      {item.output_truncated && (
        <p className="mt-1 text-xs text-fg-subtle">저장 한도로 일부만 표시됩니다</p>
      )}
    </div>
  );
};

const ToolRow = ({ item }: ToolTraceEntryProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const detailId = useId();
  const status = STATUS_VIEW[item.status ?? TOOL_TRACE_STATUS.SUCCESS];
  const duration = formatDuration(item.duration_ms);
  // Check G-04 — 원문과 정리 표시가 다를 때만 토글을 둔다 (입력 키:값, 또는 성공 결과의 JSON).
  const hasRawView =
    formatInputLines(item.input).length > 0 ||
    (item.status === TOOL_TRACE_STATUS.SUCCESS && formatOutput(item.output).isJson);

  return (
    <li>
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={detailId}
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-md px-2 py-1.5 text-left text-sm transition-colors duration-150 hover:bg-surface-sunken"
      >
        <status.Icon className={cn(ICON, status.icon)} strokeWidth={2} aria-hidden="true" />
        <span className="min-w-0 break-all font-medium text-fg">{item.label}</span>
        {item.source === TOOL_TRACE_SOURCE.MCP && <Badge tone="info">MCP</Badge>}
        {item.worker && <Badge>{item.worker}</Badge>}
        {item.requires_approval && <Badge tone="warning">승인 후 실행</Badge>}
        <span className={cn('text-xs', status.text)}>{status.label}</span>
        {duration && <span className="text-xs text-fg-subtle">{duration}</span>}
        <ChevronRight
          className={cn(ICON, 'ml-auto text-fg-subtle transition-transform duration-150', isOpen && 'rotate-90')}
          strokeWidth={1.75}
          aria-hidden="true"
        />
      </button>
      {isOpen && (
        <div id={detailId} className="mt-1 space-y-3 pb-2 pl-8 pr-2">
          <InputSection item={item} showRaw={showRaw} />
          <OutputSection item={item} showRaw={showRaw} />
          {hasRawView && (
            <Button variant="ghost" size="sm" onClick={() => setShowRaw((raw) => !raw)}>
              {showRaw ? '정리해서 보기' : '원문 보기'}
            </Button>
          )}
        </div>
      )}
    </li>
  );
};

const ToolTraceEntry = ({ item }: ToolTraceEntryProps) =>
  item.kind === TOOL_TRACE_KIND.REASONING ? <ReasoningRow item={item} /> : <ToolRow item={item} />;

export default ToolTraceEntry;
