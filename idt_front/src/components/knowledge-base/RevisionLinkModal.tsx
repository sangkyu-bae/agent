// Design Ref: document-revision §4.2 #6 — 이미 올라간 두 문서를 개정 관계로 사후 연결.
import { useId, useState } from 'react';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import { useLinkRevision } from '@/hooks/useDocumentRevision';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import { revisionErrorMessage } from './revisionErrors';

interface RevisionLinkModalProps {
  kbId: string;
  /** 신버전(이 문서가 대체한다) */
  document: KbDocumentInfo;
  /** 같은 KB 의 활성 문서 목록 — 자기 자신은 제외해 보여준다 */
  candidates: KbDocumentInfo[];
  isOpen: boolean;
  onClose: () => void;
}

const RevisionLinkModal = ({
  kbId,
  document,
  candidates,
  isOpen,
  onClose,
}: RevisionLinkModalProps) => {
  const options = candidates.filter((c) => c.document_id !== document.document_id);
  const [targetId, setTargetId] = useState('');
  const link = useLinkRevision(kbId);
  const selectId = useId();

  if (!isOpen) return null;

  const close = () => {
    if (link.isPending) return;
    link.reset();
    setTargetId('');
    onClose();
  };
  const submit = () =>
    link.mutate(
      { documentId: document.document_id, supersedesDocumentId: targetId },
      { onSuccess: close },
    );

  return (
    <Modal
      onClose={close}
      title="대체한 문서 지정"
      subtitle={document.filename}
      size="sm"
      disableClose={link.isPending}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close} disabled={link.isPending}>
            취소
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={!targetId}
            isPending={link.isPending}
          >
            연결
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-sm text-fg-secondary">
        <p>
          이 문서가 개정본으로 대체하는 기존 문서를 고르세요. 고른 문서는 이전 버전이 되어
          검색에서 제외됩니다.
        </p>
        <div>
          <label htmlFor={selectId} className="mb-1 block text-xs text-fg-muted">
            대체되는 문서
          </label>
          <select
            id={selectId}
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            className="h-10 w-full rounded-md border border-border bg-surface px-2 text-base text-fg"
          >
            <option value="">문서를 선택하세요</option>
            {options.map((c) => (
              <option key={c.document_id} value={c.document_id}>
                {c.filename} (v{c.version_no ?? 1})
              </option>
            ))}
          </select>
        </div>
        {link.isError && (
          <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-danger">
            {revisionErrorMessage(link.error)}
          </p>
        )}
      </div>
    </Modal>
  );
};

export default RevisionLinkModal;
