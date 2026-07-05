import { useState } from 'react';
import type { RagToolConfig } from '@/types/ragToolConfig';
import Modal from '@/components/common/Modal';
import RagConfigPanel from './RagConfigPanel';

interface RagConfigModalProps {
  isOpen: boolean;
  config: RagToolConfig;
  onApply: (config: RagToolConfig) => void;
  onClose: () => void;
}

/**
 * 내부 문서 검색 옵션 설정 모달 (tool-config-modal Design §2.2).
 * 로컬 드래프트로 편집하다가 저장 시에만 form에 반영한다 (ModelSettingsModal과 동일 UX).
 * 닫히면 Inner가 언마운트되어 다음 오픈 시 현재 config로 드래프트가 재초기화된다.
 */
const RagConfigModal = ({ isOpen, ...rest }: RagConfigModalProps) => {
  if (!isOpen) return null;
  return <RagConfigModalInner {...rest} />;
};

const RagConfigModalInner = ({
  config,
  onApply,
  onClose,
}: Omit<RagConfigModalProps, 'isOpen'>) => {
  const [draft, setDraft] = useState<RagToolConfig>(config);

  const handleSave = () => {
    onApply(draft);
    onClose();
  };

  return (
    <Modal
      title="내부 문서 검색 설정"
      size="2xl"
      scroll="body"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
          >
            저장
          </button>
        </>
      }
    >
      <RagConfigPanel config={draft} onChange={setDraft} />
    </Modal>
  );
};

export default RagConfigModal;
