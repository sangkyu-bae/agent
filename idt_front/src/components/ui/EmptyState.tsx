// Design Ref: ui-redesign-chat §5.3 — 빈 상태 1종. 스토어·만들기·작업·설정의 서로 다른 빈 상태 양식을 대체한다.
import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';

interface EmptyStateProps {
  /** 아이콘 또는 이미지. 기본 48px 원형 배경으로 감싼다 */
  icon?: ReactNode;
  /** icon을 감싸지 않고 그대로 배치 (아바타 등) */
  iconUnstyled?: boolean;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  /** 제안 카드 등 추가 콘텐츠 */
  children?: ReactNode;
  className?: string;
}

const EmptyState = ({
  icon,
  iconUnstyled = false,
  title,
  description,
  action,
  children,
  className,
}: EmptyStateProps) => (
  <div className={cn('flex flex-col items-center justify-center px-6 py-16 text-center', className)}>
    {icon &&
      (iconUnstyled ? (
        <div className="mb-5">{icon}</div>
      ) : (
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-surface-sunken text-fg-subtle">
          {icon}
        </div>
      ))}
    <h2 className="text-xl font-semibold text-fg">{title}</h2>
    {description && <p className="mt-2 max-w-md text-base text-fg-muted">{description}</p>}
    {action && <div className="mt-6">{action}</div>}
    {children && <div className="mt-8 w-full">{children}</div>}
  </div>
);

export default EmptyState;
