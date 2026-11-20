// Design Ref: source-passage-viewer §5.3, §11.2 F3 — ChatPage 에 1줄로 마운트되는 진입점.
// 대상이 생길 때만 패널 코드를 지연 로드하고, 패널 오류는 Boundary 가 가둔다.
import { lazy, Suspense } from 'react';

import { useSourceViewerStore } from '@/store/sourceViewerStore';

import SourceViewerBoundary from './SourceViewerBoundary';

const SourceViewerPanel = lazy(() => import('./SourceViewerPanel'));

const SourceViewerMount = () => {
  const target = useSourceViewerStore((s) => s.target);
  const close = useSourceViewerStore((s) => s.close);
  if (!target) return null;
  return (
    <SourceViewerBoundary filename={target.filename} resetKey={target} onClose={close}>
      <Suspense fallback={null}>
        <SourceViewerPanel />
      </Suspense>
    </SourceViewerBoundary>
  );
};

export default SourceViewerMount;
