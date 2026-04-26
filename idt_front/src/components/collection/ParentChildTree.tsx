import { useState } from 'react';
import type { ParentChunkGroup } from '@/types/collection';
import { CHUNK_TYPE_BADGE } from '@/types/collection';

interface ParentChildTreeProps {
  parents: ParentChunkGroup[];
}

const ParentChildTree = ({ parents }: ParentChildTreeProps) => {
  const [expandedParents, setExpandedParents] = useState<Set<string>>(new Set());

  const toggleParent = (chunkId: string) => {
    setExpandedParents((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  };

  if (parents.length === 0) {
    return (
      <p className="py-8 text-center text-[15px] text-zinc-400">
        계층 구조 데이터가 없습니다
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {parents.map((parent) => {
        const isExpanded = expandedParents.has(parent.chunk_id);
        const parentBadge = CHUNK_TYPE_BADGE.parent;
        const preview = parent.content.slice(0, 80);

        return (
          <div
            key={parent.chunk_id}
            className="rounded-xl border border-violet-100 bg-violet-50/30"
          >
            <button
              onClick={() => toggleParent(parent.chunk_id)}
              className="flex w-full items-center gap-2 px-4 py-3 text-left"
            >
              <span className="text-[12px] text-zinc-400">
                {isExpanded ? '▼' : '▶'}
              </span>
              <span className="text-[13px] font-medium text-zinc-700">
                Parent #{parent.chunk_index}
              </span>
              <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${parentBadge.bg} ${parentBadge.color}`}>
                {parentBadge.label}
              </span>
              {!isExpanded && (
                <span className="truncate text-[13px] text-zinc-400">
                  {preview}{parent.content.length > 80 ? '...' : ''}
                </span>
              )}
            </button>

            {isExpanded && (
              <div className="border-t border-violet-100 px-4 py-3">
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-600">
                  {parent.content}
                </p>

                {parent.children.length > 0 && (
                  <div className="mt-3 ml-4 space-y-1.5 border-l-2 border-sky-200 pl-3">
                    {parent.children.map((child) => {
                      const childBadge = CHUNK_TYPE_BADGE[child.chunk_type];
                      return (
                        <div
                          key={child.chunk_id}
                          className="rounded-lg bg-white px-3 py-2"
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-[12px] text-zinc-400">
                              #{child.chunk_index}
                            </span>
                            <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${childBadge.bg} ${childBadge.color}`}>
                              {childBadge.label}
                            </span>
                          </div>
                          <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-zinc-500">
                            {child.content}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default ParentChildTree;
