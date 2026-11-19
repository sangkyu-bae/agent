// Design Ref: source-passage-viewer §6 — 패널 렌더 예외를 안내로 바꿔 채팅 화면을 지킨다.
// 대상(resetKey)이 바뀌면 오류 상태를 풀어 다른 칩은 다시 열 수 있다.
import { Component, type ErrorInfo, type ReactNode } from 'react';

import SourceViewerShell from './SourceViewerShell';

interface SourceViewerBoundaryProps {
  filename: string;
  resetKey: unknown;
  onClose: () => void;
  children: ReactNode;
}

interface SourceViewerBoundaryState {
  hasError: boolean;
}

class SourceViewerBoundary extends Component<SourceViewerBoundaryProps, SourceViewerBoundaryState> {
  state: SourceViewerBoundaryState = { hasError: false };

  static getDerivedStateFromError(): SourceViewerBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[SourceViewer] panel render failed', error, info.componentStack);
  }

  componentDidUpdate(prev: SourceViewerBoundaryProps) {
    if (this.state.hasError && prev.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render() {
    const { filename, onClose, children } = this.props;
    if (!this.state.hasError) return children;
    return (
      <SourceViewerShell filename={filename} onClose={onClose}>
        <p role="alert" className="p-4 text-sm text-fg-secondary">원문을 열 수 없습니다.</p>
      </SourceViewerShell>
    );
  }
}

export default SourceViewerBoundary;
