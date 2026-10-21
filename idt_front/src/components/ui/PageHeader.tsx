// Design Ref: ui-redesign-chat §5.3 — 고정 헤더 바. CLAUDE.md 패턴 A(고정 헤더 + 스크롤 바디)의 헤더 영역을 표준화한다.
import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** 제목 왼쪽 슬롯 (아이콘, 토글 버튼) */
  leading?: ReactNode;
  /** 오른쪽 액션 슬롯 */
  actions?: ReactNode;
  /** 헤더 아래 탭 슬롯 */
  tabs?: ReactNode;
  /** 52px 고정 높이 한 줄 헤더 (채팅용) */
  compact?: boolean;
  className?: string;
}

const PageHeader = ({ title, subtitle, leading, actions, tabs, compact = false, className }: PageHeaderProps) => (
  <header className={cn('shrink-0 border-b border-border bg-surface', className)}>
    <div
      className={cn(
        'flex items-center gap-3 px-4 sm:px-6',
        compact ? 'h-13' : 'py-4',
      )}
    >
      {leading && <div className="flex shrink-0 items-center gap-2">{leading}</div>}
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold text-fg">{title}</h1>
        {subtitle && <p className="mt-0.5 hidden truncate text-sm text-fg-muted md:block">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
    {tabs && <div className="px-4 sm:px-6 [&>[role=tablist]]:border-b-0">{tabs}</div>}
  </header>
);

export default PageHeader;
