import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { EMPTY_TEXT } from '../constants';
import type { AgentNodeData } from '../buildGraph';

type AgentNodeType = Node<AgentNodeData, 'agent'>;

/**
 * 중앙 에이전트(허브) 노드 — 이름/설명/INSTRUCTIONS + Edit in Form.
 * agent-builder-visual-canvas Design §2.3.
 */
const AgentNode = ({ data }: NodeProps<AgentNodeType>) => {
  const { name, description, systemPrompt, onEditInForm } = data;

  return (
    <div className="w-[240px] rounded-2xl border border-zinc-300 bg-white shadow-md">
      {/* 사방 핸들 (엣지 출발점, 시각적으로 숨김) */}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Top} id="top" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} id="bottom" style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Left} id="left" style={{ opacity: 0 }} />

      <div className="border-b border-zinc-100 px-4 py-2.5">
        <span className="text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
          에이전트
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="truncate text-[15px] font-bold text-zinc-900">{name || '새 에이전트'}</p>
        <p className="mt-0.5 truncate text-[12.5px] text-zinc-400">
          {description || '에이전트 설명을 입력하세요'}
        </p>

        <div className="mt-3 border-t border-zinc-100 pt-3">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">
            Instructions
          </span>
          <p className="mt-1 line-clamp-2 text-[12.5px] leading-relaxed text-zinc-600">
            {systemPrompt || EMPTY_TEXT.instructions}
          </p>
        </div>

        <button
          type="button"
          onClick={onEditInForm}
          className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg border border-zinc-200 bg-zinc-50 py-1.5 text-[12px] font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-100"
        >
          ✏ Edit in Form
        </button>
      </div>
    </div>
  );
};

export default AgentNode;
