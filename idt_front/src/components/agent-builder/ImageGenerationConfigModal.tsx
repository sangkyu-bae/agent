import type { ImageGenerationDraft } from '@/types/imageGeneration';
import Modal from '@/components/common/Modal';
import ImageGenerationConfigPanel from './ImageGenerationConfigPanel';

interface ImageGenerationConfigModalProps {
  isOpen: boolean;
  draft: ImageGenerationDraft | null;
  onChange: (draft: ImageGenerationDraft) => void;
  onClose: () => void;
}

/**
 * 이미지 생성 설정 모달 (PresentationGeneratorConfigModal 동형).
 * 편집 내용은 폼 드래프트에 즉시 반영 — 저장은 에이전트 저장에 편승.
 */
const ImageGenerationConfigModal = ({
  isOpen,
  draft,
  onChange,
  onClose,
}: ImageGenerationConfigModalProps) => {
  if (!isOpen) return null;

  return (
    <Modal
      title="이미지 생성 — 모델·크기·품질"
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
      <ImageGenerationConfigPanel draft={draft} onChange={onChange} />
    </Modal>
  );
};

export default ImageGenerationConfigModal;
