import type { ReactNode } from 'react';

interface PlaceholderSectionProps {
  /** 비어있음 안내 문구 (예: "서브에이전트가 없습니다") */
  emptyText: string;
  /** 헤더 우측 비활성 액션 라벨 (예: "+미들웨어") */
  actionLabel?: string;
  /** 헤더 좌측 아이콘 */
  icon?: ReactNode;
}

/**
 * 백엔드 미지원 기능의 비활성 자리 표시 블록.
 * 동작하는 것처럼 보이지 않도록 disabled + opacity + "준비중" 툴팁 적용.
 * agent-builder-studio-ui Design §3.2 / FR-09.
 */
const PlaceholderSection = ({
  emptyText,
  actionLabel,
  icon,
}: PlaceholderSectionProps) => {
  return (
    <div className="opacity-60" aria-disabled="true">
      {actionLabel && (
        <div className="mb-2 flex justify-end">
          <button
            type="button"
            disabled
            title="준비중"
            className="cursor-not-allowed rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-400"
          >
            {actionLabel}
          </button>
        </div>
      )}
      <div
        title="준비중"
        className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-200 bg-zinc-50 py-4 text-center"
      >
        {icon}
        <span className="text-[12.5px] text-zinc-400">{emptyText}</span>
        <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-[10px] font-semibold text-zinc-500">
          준비중
        </span>
      </div>
    </div>
  );
};

export default PlaceholderSection;
