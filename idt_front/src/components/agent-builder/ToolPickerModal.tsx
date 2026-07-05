import type { CatalogTool } from '@/types/toolCatalog';
import Modal from '@/components/common/Modal';

interface ToolPickerModalProps {
  isOpen: boolean;
  catalogTools?: CatalogTool[];
  selectedIds: string[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onToggle: (toolId: string) => void;
  onClose: () => void;
}

/**
 * 도구 추가 팝업.
 * useToolCatalog 결과를 표시하고 항목 토글을 부모로 위임한다.
 * 선택은 즉시 form에 반영되므로 별도 확정 단계가 없다.
 */
const ToolPickerModal = ({
  isOpen,
  catalogTools,
  selectedIds,
  isLoading = false,
  isError = false,
  onRetry,
  onToggle,
  onClose,
}: ToolPickerModalProps) => {
  if (!isOpen) return null;

  return (
    <Modal
      title="도구 추가"
      size="lg"
      scroll="body"
      onClose={onClose}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
        >
          완료
        </button>
      }
    >
      <>
          {isLoading ? (
            <div className="grid grid-cols-1 gap-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[52px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
              ))}
            </div>
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-8">
              <p className="text-[13px] text-zinc-500">도구 목록을 불러올 수 없습니다</p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
                >
                  다시 시도
                </button>
              )}
            </div>
          ) : catalogTools && catalogTools.length > 0 ? (
            <div className="grid grid-cols-1 gap-2">
              {catalogTools.map((tool) => {
                const isSelected = selectedIds.includes(tool.tool_id);
                return (
                  <button
                    key={tool.tool_id}
                    type="button"
                    onClick={() => onToggle(tool.tool_id)}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all ${
                      isSelected
                        ? 'border-violet-300 bg-violet-50'
                        : 'border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[13px] font-medium ${isSelected ? 'text-violet-700' : 'text-zinc-700'}`}>
                          {tool.name}
                        </span>
                        {tool.source === 'mcp' && (
                          <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600">MCP</span>
                        )}
                      </div>
                      {tool.description && (
                        <p className="mt-0.5 line-clamp-1 text-[11.5px] text-zinc-400">{tool.description}</p>
                      )}
                    </div>
                    {isSelected && (
                      <svg className="h-4 w-4 shrink-0 text-violet-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 py-8 text-center">
              <p className="text-[13px] text-zinc-400">등록된 도구가 없습니다</p>
            </div>
          )}
      </>
    </Modal>
  );
};

export default ToolPickerModal;
