import type { DocumentGeneratorDraft } from '@/types/documentGenerator';
import Modal from '@/components/common/Modal';
import DocumentGeneratorConfigPanel from './DocumentGeneratorConfigPanel';

interface DocumentGeneratorConfigModalProps {
  isOpen: boolean;
  draft: DocumentGeneratorDraft | null;
  onChange: (draft: DocumentGeneratorDraft) => void;
  onClose: () => void;
}

/**
 * 문서생성기 문서 유형 편집 모달 (DocumentExtractorConfigModal 동형).
 * 편집 내용은 폼 드래프트에 즉시 반영 — 저장은 에이전트 저장에 편승.
 */
const DocumentGeneratorConfigModal = ({
  isOpen,
  draft,
  onChange,
  onClose,
}: DocumentGeneratorConfigModalProps) => {
  if (!isOpen) return null;

  return (
    <Modal
      title="문서생성기 — 문서 유형"
      size="lg"
      scroll="body"
      closeOnBackdrop={false}
      onClose={onClose}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
        >
          완료
        </button>
      }
    >
      <DocumentGeneratorConfigPanel draft={draft} onChange={onChange} />
    </Modal>
  );
};

export default DocumentGeneratorConfigModal;
