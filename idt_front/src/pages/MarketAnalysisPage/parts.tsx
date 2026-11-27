// stock-analysis-agents §9 — 탭들이 같이 쓰는 작은 표시 조각 (표·상태·페이지 이동).
import type { ReactNode } from 'react';
import Button from '@/components/ui/Button';
import { cn } from '@/utils/cn';
import { marketAnalysisErrorMessage } from '@/utils/marketAnalysis';

export const Loading = () => (
  <p className="py-10 text-center text-sm text-fg-muted">불러오는 중…</p>
);

export const ErrorBox = ({ error, fallback }: { error: unknown; fallback: string }) => (
  <p
    role="alert"
    className="rounded-xl border border-danger-border bg-danger-bg px-4 py-3 text-sm text-danger"
  >
    {marketAnalysisErrorMessage(error, fallback)}
  </p>
);

export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="rounded-xl border border-border bg-surface-muted px-4 py-8 text-center text-sm text-fg-muted">
    {children}
  </p>
);

export const Card = ({
  title,
  children,
  className,
  actions,
  label,
}: {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
  /** 있으면 영역 이름(region)으로 읽힌다 */
  label?: string;
}) => (
  <section
    aria-label={label}
    className={cn('rounded-xl border border-border bg-surface p-4 shadow-sm', className)}
  >
    {(title || actions) && (
      <div className="mb-3 flex items-center justify-between gap-3">
        {title && <h2 className="text-base font-semibold text-fg">{title}</h2>}
        {actions}
      </div>
    )}
    {children}
  </section>
);

export const Table = ({ children, label }: { children: ReactNode; label: string }) => (
  <div className="overflow-x-auto rounded-xl border border-border">
    <table aria-label={label} className="w-full min-w-max text-left text-sm">
      {children}
    </table>
  </div>
);

export const Th = ({ children, right = false }: { children: ReactNode; right?: boolean }) => (
  <th
    scope="col"
    className={cn(
      'border-b border-border bg-surface-muted px-3 py-2 text-xs font-medium text-fg-muted',
      right && 'text-right',
    )}
  >
    {children}
  </th>
);

export const Td = ({
  children,
  right = false,
  className,
}: {
  children: ReactNode;
  right?: boolean;
  className?: string;
}) => (
  <td className={cn('border-b border-border px-3 py-2 text-fg', right && 'text-right tabular-nums', className)}>
    {children}
  </td>
);

export const Pager = ({
  page,
  total,
  size,
  onChange,
}: {
  page: number;
  total: number;
  size: number;
  onChange: (page: number) => void;
}) => {
  const last = Math.max(1, Math.ceil(total / size));
  if (last <= 1) return null;
  return (
    <div className="mt-3 flex items-center justify-end gap-2 text-sm text-fg-muted">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        이전
      </Button>
      <span>
        {page} / {last}
      </span>
      <Button variant="secondary" size="sm" disabled={page >= last} onClick={() => onChange(page + 1)}>
        다음
      </Button>
    </div>
  );
};

export const BackButton = ({ onClick, label = '목록으로' }: { onClick: () => void; label?: string }) => (
  <Button variant="ghost" size="sm" onClick={onClick} className="mb-3">
    ← {label}
  </Button>
);
