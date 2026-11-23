// Design Ref: document-revision §4.2 #5·§5.2 — 최신 개정 취소. 이전 버전을 먼저 검색에 복귀시킨다.
import { useId, useState } from 'react';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import { useRollbackRevision } from '@/hooks/useDocumentRevision';
import type { KbDocumentInfo, RollbackMode } from '@/types/knowledgeBase';
import { revisionErrorMessage } from './revisionErrors';

interface RevisionRollbackDialogProps {
  kbId: string;
  document: KbDocumentInfo;
  isOpen: boolean;
  onClose: () => void;
}

const RevisionRollbackDialog = ({
  kbId,
  document,
  isOpen,
  onClose,
}: RevisionRollbackDialogProps) => {
  const [mode, setMode] = useState<RollbackMode>('detach');
  const rollback = useRollbackRevision(kbId);
  const group = useId();

  if (!isOpen) return null;

  const version = document.version_no ?? 1;
  const close = () => {
    if (rollback.isPending) return;
    rollback.reset();
    setMode('detach');
    onClose();
  };
  const submit = () =>
    rollback.mutate({ documentId: document.document_id, mode }, { onSuccess: close });

  return (
    <Modal
      onClose={close}
      title="개정 되돌리기"
      subtitle={`${document.filename} · v${version}`}
      size="sm"
      disableClose={rollback.isPending}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close} disabled={rollback.isPending}>
            취소
          </Button>
          <Button variant="primary" onClick={submit} isPending={rollback.isPending}>
            되돌리기
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-sm text-fg-secondary">
        <p>이전 버전(v{version - 1})을 다시 검색에 사용합니다. 이 버전은 어떻게 할까요?</p>
        <fieldset className="space-y-2">
          <legend className="sr-only">이 버전 처리 방식</legend>
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name={group}
              checked={mode === 'detach'}
              onChange={() => setMode('detach')}
              className="mt-0.5"
            />
            <span>
              별도 문서로 남기기
              <span className="block text-xs text-fg-muted">
                이 파일은 독립 문서(v1)로 계속 검색됩니다.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name={group}
              checked={mode === 'delete'}
              onChange={() => setMode('delete')}
              className="mt-0.5"
            />
            <span>
              이 버전을 삭제
              <span className="block text-xs text-fg-muted">
                청크와 요약을 지우며 복구할 수 없습니다.
              </span>
            </span>
          </label>
        </fieldset>
        {rollback.isError && (
          <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-danger">
            {revisionErrorMessage(rollback.error)}
          </p>
        )}
      </div>
    </Modal>
  );
};

export default RevisionRollbackDialog;
