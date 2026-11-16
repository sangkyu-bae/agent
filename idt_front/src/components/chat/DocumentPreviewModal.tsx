// Design Ref: document-file-preview §5 — 산출 .docx·.pdf 미리보기 모달.
// 상태는 documentPreviewStore가 소유하고 ChatPage에 1회 마운트한다 (excel-preview §5.3과 같은 구조).
// 다운로드는 documentExtractorService.downloadGeneratedFile 재사용 (Plan FR-06).
import { useCallback, useState } from 'react';
import { Loader2 } from 'lucide-react';

import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import DocxPreviewView from './DocxPreviewView';
import PdfPreviewView from './PdfPreviewView';
import { useGeneratedFileBlob } from '@/hooks/useGeneratedFileBlob';
import {
  useDocumentPreviewStore,
  type DocumentPreviewTarget,
} from '@/store/documentPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import { DOCX_PREVIEW_MAX_BYTES } from '@/types/filePreview';
import {
  DocumentRenderError,
  DocumentTooLargeError,
  previewErrorView,
} from '@/utils/filePreviewError';

type RenderState = 'rendering' | 'done' | DocumentRenderError;

interface ContentProps {
  target: DocumentPreviewTarget;
  onClose: () => void;
}

const DocumentPreviewModalContent = ({ target, onClose }: ContentProps) => {
  const { data: blob, isPending, isError, error } = useGeneratedFileBlob(target.fileId);
  const [renderState, setRenderState] = useState<RenderState>('rendering');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // DocxPreviewView effect deps — identity 고정 (React Compiler 린트: 억제 주석 대신 useCallback)
  const handleRendered = useCallback(() => setRenderState('done'), []);
  const handleFailed = useCallback((err: unknown) => {
    // Design §6.1: 사용자 데이터 없이 원인만 남긴다
    console.warn('[document-preview] render failed', err);
    setRenderState(new DocumentRenderError(err));
  }, []);

  const handleDownload = () => {
    setDownloading(true);
    setDownloadError(null);
    documentExtractorService
      .downloadGeneratedFile(target.fileId, target.filename)
      .catch(() => {
        // 캐시된 미리보기 중 TTL 만료 등 (Design §5.3 캐시 정책)
        setDownloadError('다운로드에 실패했습니다. 파일이 만료되었을 수 있습니다.');
      })
      .finally(() => setDownloading(false));
  };

  const isDocx = target.kind === 'docx';
  const tooLarge = isDocx && !!blob && blob.size > DOCX_PREVIEW_MAX_BYTES;
  const failure: unknown = isError
    ? error
    : tooLarge
      ? new DocumentTooLargeError()
      : renderState instanceof DocumentRenderError
        ? renderState
        : null;
  const failed = failure ? previewErrorView(failure) : null;
  const loading = !failed && (isPending || (isDocx && renderState === 'rendering'));
  const showDownload = !failed || failed.canDownload;

  return (
    <Modal
      onClose={onClose}
      title={target.filename}
      subtitle="다운로드 전 미리보기 — 원본과 일부 서식이 다를 수 있습니다"
      size="4xl"
      scroll="body"
      footer={
        <>
          {downloadError && (
            <span role="alert" className="mr-auto self-center text-xs text-danger">
              {downloadError}
            </span>
          )}
          {showDownload && (
            <Button
              size="sm"
              isPending={downloading}
              pendingText="다운로드 중…"
              onClick={handleDownload}
            >
              다운로드
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onClose}>
            닫기
          </Button>
        </>
      }
    >
      {loading && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-fg-subtle">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden="true" />
          문서를 불러오는 중…
        </div>
      )}

      {failed && (
        <div role="alert" className="py-16 text-center text-sm text-fg-muted">
          {failed.message}
        </div>
      )}

      {/* docx는 렌더가 끝날 때까지 호스트를 숨긴 채 마운트해 둔다 (렌더 대상이 필요) */}
      {blob && !failed && isDocx && (
        <div className={renderState === 'done' ? undefined : 'hidden'}>
          <DocxPreviewView blob={blob} onRendered={handleRendered} onFailed={handleFailed} />
        </div>
      )}
      {blob && !failed && target.kind === 'pdf' && (
        <PdfPreviewView blob={blob} filename={target.filename} />
      )}
    </Modal>
  );
};

/** target이 null이면 렌더하지 않는다. fileId 전환 시 key로 렌더 상태를 초기화한다. */
const DocumentPreviewModal = () => {
  const target = useDocumentPreviewStore((s) => s.target);
  const close = useDocumentPreviewStore((s) => s.close);

  if (!target) return null;
  return <DocumentPreviewModalContent key={target.fileId} target={target} onClose={close} />;
};

export default DocumentPreviewModal;
