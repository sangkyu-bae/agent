// Design Ref: source-passage-viewer §5.1 — 패널 외곽(채팅 위에 겹쳐 띄움, 모바일 전체 화면).
// 패널 본문과 오류 대체 화면이 같은 외곽을 써서 오류가 나도 닫을 수 있다.
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

import IconButton from '@/components/ui/IconButton';

interface SourceViewerShellProps {
  filename: string;
  onClose: () => void;
  children: ReactNode;
}

const SourceViewerShell = ({ filename, onClose, children }: SourceViewerShellProps) => (
  <aside
    aria-label={`${filename} 원문`}
    className="fixed inset-0 z-40 flex flex-col bg-surface shadow-lg md:inset-y-0 md:left-auto md:right-0 md:w-[480px] md:border-l md:border-border"
  >
    <header className="flex items-center gap-2 border-b border-border px-4 py-3">
      <p className="min-w-0 flex-1 truncate text-base font-semibold text-fg" title={filename}>
        {filename}
      </p>
      <IconButton aria-label="원문 패널 닫기" size="sm" onClick={onClose}>
        <X className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
      </IconButton>
    </header>
    {children}
  </aside>
);

export default SourceViewerShell;
