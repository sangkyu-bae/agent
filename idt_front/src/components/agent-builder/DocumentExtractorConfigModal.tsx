import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import Modal from '@/components/common/Modal';
import DocumentExtractorConfigPanel from './DocumentExtractorConfigPanel';

interface DocumentExtractorConfigModalProps {
  isOpen: boolean;
  draft: DocumentExtractorDraft | null;
  onChange: (draft: DocumentExtractorDraft | null) => void;
  onClose: () => void;
}

/**
 * 문서추출기 양식 등록 모달 (tool-config-modal Design §2.3).
 * 업로드/재추천이 서버 뮤테이션이므로 즉시 반영 + 닫기만 제공한다.
 * 배경 오클릭으로 닫히는 사고 방지를 위해 closeOnBackdrop 비활성.
 */
const DocumentExtractorConfigModal = ({
  isOpen,
  draft,
  onChange,
  onClose,
}: DocumentExtractorConfigModalProps) => {
  if (!isOpen) return null;

  return (
    <Modal
      title="문서추출기 — 양식 등록"
      size="full"
      scroll="body"
      contentClassName="h-[80vh]"
      closeOnBackdrop={false}
      onClose={onClose}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
        >
          닫기
        </button>
      }
    >
      <DocumentExtractorConfigPanel draft={draft} onChange={onChange} />
    </Modal>
  );
};

export default DocumentExtractorConfigModal;
