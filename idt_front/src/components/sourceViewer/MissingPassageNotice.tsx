// Design Ref: source-passage-viewer §5.4·FR-12 (Analysis 갭 #1) — 위치를 못 찾은 구절의 공용 안내.
// 텍스트·PDF·docx 뷰어가 같은 문구·발췌·전환 버튼을 쓴다.
interface MissingPassageNoticeProps {
  /** 기본 안내 대신 쓸 문구 (예: "…3쪽을 보여 줍니다") */
  message?: string;
  excerpt?: string;
  /** 있으면 [텍스트로 보기] 버튼을 보여 준다 (원본 뷰어 전용) */
  onShowText?: () => void;
}

const DEFAULT_MESSAGE = '원문에서 정확한 위치를 찾지 못했습니다.';

const MissingPassageNotice = ({ message = DEFAULT_MESSAGE, excerpt, onShowText }: MissingPassageNoticeProps) => {
  // 청킹이 한글을 바이트 중간에서 자른 깨진 문자(U+FFFD)는 보여 주지 않는다 (Design §12 M19)
  const clean = excerpt?.replace(/�/g, '').trim();
  return (
    <div role="status" className="m-4 rounded-md border border-warning-border bg-warning-bg p-3 text-sm text-fg-secondary">
      <p className="font-medium text-warning">{message}</p>
      {clean && <p className="mt-2 whitespace-pre-wrap break-words">{clean}</p>}
      {onShowText && (
        <button
          type="button"
          onClick={onShowText}
          className="mt-2 rounded-md border border-border bg-surface px-2.5 py-1 text-xs text-fg-muted transition-colors duration-150 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
        >
          텍스트로 보기
        </button>
      )}
    </div>
  );
};

export default MissingPassageNotice;
