// Design Ref: answer-citation-verification §5.4 — 미사용(또는 검색된) 구절 접힘 목록. 기본 접힘.
import { ChevronRight } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

import { cn } from '@/utils/cn';

interface UnusedSourcesDisclosureProps {
  label: string;
  children: ReactNode;
}

const UnusedSourcesDisclosure = ({ label, children }: UnusedSourcesDisclosureProps) => {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? regionId : undefined}
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-xs text-fg-subtle transition-colors duration-150 hover:text-fg"
      >
        <ChevronRight
          className={cn('h-3.5 w-3.5 transition-transform duration-150', open && 'rotate-90')}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        {label}
      </button>
      {open && (
        <div id={regionId} className="mt-2">
          {children}
        </div>
      )}
    </div>
  );
};

export default UnusedSourcesDisclosure;
