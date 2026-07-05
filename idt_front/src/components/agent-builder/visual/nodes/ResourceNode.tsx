import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { EMPTY_TEXT, RESOURCE_META, EDGE_COLOR } from '../constants';
import type { ResourceNodeData } from '../buildGraph';

type ResourceNodeType = Node<ResourceNodeData, 'resource'>;

/**
 * 리소스 카드 노드 — 스킬/도구/서브에이전트/미들웨어/모델 공통.
 * 스킬·미들웨어는 disabled 플레이스홀더(준비중). agent-builder-visual-canvas Design §2.3.
 */
const ResourceNode = ({ data }: NodeProps<ResourceNodeType>) => {
  const { kind, items, disabled, onAction } = data;
  const meta = RESOURCE_META[kind];
  const accent = EDGE_COLOR[kind];
  const hasItems = items.length > 0;
  const isModel = kind === 'model';

  return (
    <div
      role={isModel ? 'button' : undefined}
      onClick={isModel ? onAction : undefined}
      className={`w-[200px] rounded-2xl border border-zinc-200 bg-white shadow-sm${
        isModel ? ' cursor-pointer transition-colors hover:border-amber-300' : ''
      }`}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />

      {/* 헤더 */}
      <div className="flex items-center gap-1.5 border-b border-zinc-100 px-3.5 py-2.5">
        <span className="text-[13px]">{meta.icon}</span>
        <span
          className="text-[11.5px] font-semibold uppercase tracking-widest"
          style={{ color: accent }}
        >
          {meta.title}
        </span>
      </div>

      {/* 본문 */}
      <div className="px-3.5 py-3">
        {kind === 'model' ? (
          <code className="text-[12.5px] font-medium text-zinc-700">{items[0]}</code>
        ) : hasItems ? (
          <ul className="space-y-1">
            {items.map((label) => (
              <li
                key={label}
                className="truncate rounded-lg bg-zinc-50 px-2.5 py-1.5 text-[12px] text-zinc-600"
              >
                {label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-1 text-center text-[11.5px] text-zinc-400">{EMPTY_TEXT[kind]}</p>
        )}

        {/* 액션 버튼 (모델은 헤더 카드 클릭으로 처리, 버튼 없음) */}
        {kind !== 'model' && (
          <button
            type="button"
            disabled={disabled}
            title={disabled ? '준비중' : undefined}
            onClick={disabled ? undefined : onAction}
            aria-label={meta.actionLabel}
            className={
              disabled
                ? 'mt-2.5 w-full cursor-not-allowed rounded-lg border border-dashed border-zinc-200 py-1.5 text-[12px] font-medium text-zinc-300'
                : 'mt-2.5 w-full rounded-lg py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90 active:scale-[0.98]'
            }
            style={disabled ? undefined : { backgroundColor: accent }}
          >
            {meta.actionLabel}
          </button>
        )}
      </div>
    </div>
  );
};

export default ResourceNode;
