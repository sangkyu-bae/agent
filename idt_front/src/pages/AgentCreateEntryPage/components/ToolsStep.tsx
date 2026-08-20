import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import ToolPickerModal from '@/components/agent-builder/ToolPickerModal';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import type { CatalogTool } from '@/types/toolCatalog';

interface ToolsStepProps {
  /** 서버가 추천한 도구 (셀렉터 결과). */
  recommendedIds: string[];
  /** 현재 선택된 도구 — 추천 토글 + 직접 추가의 합. */
  selectedIds: string[];
  /** 카탈로그에 없거나 비활성이라 반영되지 않은 id (조용히 사라지지 않게 안내). */
  unknownIds: string[];
  isPending: boolean;
  onToggle: (toolId: string) => void;
  onConfirm: () => void;
  onBack: () => void;
}

const describe = (tool: CatalogTool | undefined, toolId: string) => ({
  name: tool?.name ?? toolId,
  description: tool?.description ?? '',
});

/**
 * ③ 도구 확인 (Design §5.4 step③ / FR-F06).
 *
 * 추천 도구는 기본 전부 선택된 상태로 오고 개별 해제할 수 있으며,
 * `[도구 더 추가]` 로 기존 `ToolPickerModal` 을 열어 카탈로그 전체에서 고른다.
 *
 * 여기서 확정한 목록은 다음 호출에 `tools_confirmed=true` 와 함께 실려
 * 서버가 셀렉터를 다시 돌리지 않는다 — 그래야 해제한 도구가 되살아나지 않는다
 * (Design D1).
 */
const ToolsStep = ({
  recommendedIds,
  selectedIds,
  unknownIds,
  isPending,
  onToggle,
  onConfirm,
  onBack,
}: ToolsStepProps) => {
  const [pickerOpen, setPickerOpen] = useState(false);
  const { data: catalogTools, isLoading, isError, refetch } = useToolCatalog();

  const byId = new Map((catalogTools ?? []).map((t) => [t.tool_id, t]));
  // 추천 + 사용자가 직접 추가한 것을 한 목록으로 보여준다. 추천 순서를 앞에 둔다.
  const visibleIds = [
    ...recommendedIds,
    ...selectedIds.filter((id) => !recommendedIds.includes(id)),
  ];

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[15px] font-semibold text-zinc-900">
          이 도구들을 사용할까요?
        </h2>
        <p className="mt-1 text-[12.5px] text-zinc-500">
          요청 내용에 맞춰 골라봤어요. 필요 없는 건 해제하고, 빠진 건 추가하세요.
        </p>
      </div>

      {unknownIds.length > 0 && (
        <div
          role="status"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800"
        >
          {unknownIds.length}개 도구는 카탈로그에 없거나 비활성이라 제외됐습니다.
        </div>
      )}

      {visibleIds.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-4 py-8 text-center">
          <p className="text-[13.5px] text-zinc-500">
            추천할 도구를 찾지 못했어요.
          </p>
          <p className="mt-1 text-[12px] text-zinc-400">
            도구 없이 진행하거나 직접 추가할 수 있습니다.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {visibleIds.map((toolId) => {
            const { name, description } = describe(byId.get(toolId), toolId);
            const checked = selectedIds.includes(toolId);
            const addedByUser = !recommendedIds.includes(toolId);
            return (
              <li key={toolId}>
                <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-zinc-200 bg-white p-4 transition-all hover:border-zinc-300">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={isPending}
                    onChange={() => onToggle(toolId)}
                    className="mt-1 h-4 w-4 accent-violet-600"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-[13.5px] font-medium text-zinc-900">
                        {name}
                      </span>
                      {addedByUser && (
                        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-600">
                          직접 추가
                        </span>
                      )}
                    </span>
                    {description && (
                      <span className="mt-0.5 block text-[12px] leading-relaxed text-zinc-500">
                        {description}
                      </span>
                    )}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            disabled={isPending}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed"
          >
            이전
          </button>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            disabled={isPending}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-[13.5px] font-medium text-violet-600 transition-all hover:border-violet-300 disabled:cursor-not-allowed"
          >
            도구 더 추가
          </button>
        </div>
        <LoadingButton
          isPending={isPending}
          pendingText="프롬프트 만드는 중…"
          onClick={onConfirm}
          className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-60"
        >
          이 도구로 진행
        </LoadingButton>
      </div>

      <ToolPickerModal
        isOpen={pickerOpen}
        catalogTools={catalogTools}
        selectedIds={selectedIds}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => void refetch()}
        onToggle={onToggle}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
};

export default ToolsStep;
