// Design Ref: answer-citation-verification §5.1 FR-13 — 검증된 인용이 없는 답변(status=none).
// 칩을 비우지 않고 명시해, 근거 표시가 잘못된 안심을 주지 않게 한다.
import { AlertTriangle } from 'lucide-react';

const CitationNoneBadge = () => (
  <p
    role="status"
    className="flex items-start gap-1.5 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-xs text-warning"
  >
    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
    <span>
      <span className="font-semibold">근거 확인 안 됨</span> — 이 답변은 검색한 문서로 확인된 인용이 없습니다.
    </span>
  </p>
);

export default CitationNoneBadge;
