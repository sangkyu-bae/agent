import type { PresentationGeneratorDraft } from '@/types/presentationGenerator';
import Modal from '@/components/common/Modal';
import PresentationGeneratorConfigPanel from './PresentationGeneratorConfigPanel';

interface PresentationGeneratorConfigModalProps {
  isOpen: boolean;
  draft: PresentationGeneratorDraft | null;
  onChange: (draft: PresentationGeneratorDraft) => void;
  onClose: () => void;
}

/**
 * 발표자료생성기 설정 모달 (DocumentGeneratorConfigModal 동형).
 * 편집 내용은 폼 드래프트에 즉시 반영 — 저장은 에이전트 저장에 편승.
 */
const PresentationGeneratorConfigModal = ({
  isOpen,
  draft,
  onChange,
  onClose,
}: PresentationGeneratorConfigModalProps) => {
  if (!isOpen) return null;

  return (
    <Modal
      title="발표자료생성기 — 양식 선택"
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
      <PresentationGeneratorConfigPanel draft={draft} onChange={onChange} />
    </Modal>
  );
};

export default PresentationGeneratorConfigModal;
