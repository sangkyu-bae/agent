import { useState, type ReactNode } from 'react';

interface CollapsibleSectionProps {
  title: string;
  /** 헤더 우측에 배치되는 액션 (버튼/아이콘 등) */
  action?: ReactNode;
  /** 헤더 좌측 타이틀 앞 아이콘 */
  icon?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * 좌측 구성 패널의 접기/펼치기 공통 래퍼.
 * agent-builder-studio-ui Design §5.6.
 */
const CollapsibleSection = ({
  title,
  action,
  icon,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-zinc-100 py-3">
      <div className="flex items-center justify-between px-1">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-[13px] font-semibold text-zinc-700 transition-colors hover:text-zinc-900"
        >
          <svg
            className={`h-3.5 w-3.5 text-zinc-400 transition-transform ${open ? '' : '-rotate-90'}`}
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2.5}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
          {icon}
          {title}
        </button>
        {action}
      </div>

      {open && <div className="mt-3 px-1">{children}</div>}
    </div>
  );
};

export default CollapsibleSection;
