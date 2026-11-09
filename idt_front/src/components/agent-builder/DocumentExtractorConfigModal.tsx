import { useState } from 'react';
import type {
  AgentDocumentTemplateResponse,
  DocumentExtractorDraft,
} from '@/types/documentExtractor';
import { SAVED_TEMPLATE_TEXT } from '@/types/documentExtractor';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import DocumentExtractorConfigPanel from './DocumentExtractorConfigPanel';
import SavedTemplateView from './SavedTemplateView';

interface DocumentExtractorConfigModalProps {
  isOpen: boolean;
  draft: DocumentExtractorDraft | null;
  onChange: (draft: DocumentExtractorDraft | null) => void;
  onClose: () => void;
  /** wizard-template-request FR-13/G3: 드래프트 없을 때 패널 상단 안내 (미지정=기본 상수) */
  emptyNotice?: string;
  /** extractor-template-preview §5.2: 서버에 저장된 양식이 있다 (form.savedTemplateId) */
  hasSavedTemplate?: boolean;
  /** 저장 양식 조회 결과 (null = 404, undefined = 로딩 전·오류) */
  savedTemplate?: AgentDocumentTemplateResponse | null;
  isSavedTemplateLoading?: boolean;
  isSavedTemplateError?: boolean;
}

type ExtractorModalMode = 'saved' | 'upload';

/**
 * 문서추출기 양식 등록 모달 (tool-config-modal Design §2.3).
 * 업로드/재추천이 서버 뮤테이션이므로 즉시 반영 + 닫기만 제공한다.
 * 배경 오클릭으로 닫히는 사고 방지를 위해 closeOnBackdrop 비활성.
 *
 * Design Ref: extractor-template-preview §5.2 — 드래프트가 없고 저장 양식이 있으면
 * 보기 모드로 연다. 드래프트가 생기면 항상 편집 패널(드래프트 우선).
 */
const DocumentExtractorConfigModal = ({
  isOpen,
  draft,
  onChange,
  onClose,
  emptyNotice,
  hasSavedTemplate = false,
  savedTemplate,
  isSavedTemplateLoading = false,
  isSavedTemplateError = false,
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
      {/* isOpen=false 에서 언마운트되므로 mode 는 열 때마다 초기화된다 */}
      <ExtractorModalBody
        draft={draft}
        onChange={onChange}
        emptyNotice={emptyNotice}
        hasSavedTemplate={hasSavedTemplate}
        savedTemplate={savedTemplate}
        isSavedTemplateLoading={isSavedTemplateLoading}
        isSavedTemplateError={isSavedTemplateError}
      />
    </Modal>
  );
};

type ExtractorModalBodyProps = Omit<DocumentExtractorConfigModalProps, 'isOpen' | 'onClose'>;

const ExtractorModalBody = ({
  draft,
  onChange,
  emptyNotice,
  hasSavedTemplate = false,
  savedTemplate,
  isSavedTemplateLoading = false,
  isSavedTemplateError = false,
}: ExtractorModalBodyProps) => {
  const [mode, setMode] = useState<ExtractorModalMode>(
    hasSavedTemplate ? 'saved' : 'upload',
  );

  if (!draft && hasSavedTemplate && mode === 'saved') {
    return (
      <SavedTemplateView
        template={savedTemplate}
        isLoading={isSavedTemplateLoading}
        isError={isSavedTemplateError}
        onReplace={() => setMode('upload')}
      />
    );
  }

  return (
    <div className="space-y-3">
      {!draft && hasSavedTemplate && (
        <Button variant="ghost" size="sm" onClick={() => setMode('saved')}>
          {SAVED_TEMPLATE_TEXT.backToSaved}
        </Button>
      )}
      <DocumentExtractorConfigPanel
        draft={draft}
        onChange={onChange}
        emptyNotice={emptyNotice}
      />
    </div>
  );
};

export default DocumentExtractorConfigModal;
