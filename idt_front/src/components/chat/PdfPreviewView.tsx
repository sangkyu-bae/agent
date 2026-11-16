// Design Ref: document-file-preview §5.3 — PDF는 브라우저 내장 뷰어(iframe)로 표시한다.
import { useEffect, useRef } from 'react';

interface PdfPreviewViewProps {
  blob: Blob;
  filename: string;
}

const PdfPreviewView = ({ blob, filename }: PdfPreviewViewProps) => {
  const frameRef = useRef<HTMLIFrameElement>(null);

  // blob URL은 외부 리소스라 effect에서 만들고 해제한다 (Design §7: unmount 시 revoke)
  useEffect(() => {
    // 응답 Content-Type과 무관하게 내장 뷰어가 PDF로 인식하도록 타입을 고정한다
    const objectUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
    if (frameRef.current) frameRef.current.src = objectUrl;
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  return (
    <iframe
      ref={frameRef}
      title={`${filename} 미리보기`}
      className="h-[70vh] w-full rounded-lg border border-border bg-surface-muted"
    />
  );
};

export default PdfPreviewView;
