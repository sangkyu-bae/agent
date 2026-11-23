// Design Ref: document-revision §4.2 #7 — 버전 라벨·시행일 수정 (검색에는 영향 없음).
import { useState } from 'react';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import Input from '@/components/ui/Input';
import { useUpdateRevisionMeta } from '@/hooks/useDocumentRevision';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import { revisionErrorMessage } from './revisionErrors';

interface RevisionMetaDialogProps {
  kbId: string;
  document: KbDocumentInfo;
  isOpen: boolean;
  onClose: () => void;
}

const RevisionMetaDialog = ({ kbId, document, isOpen, onClose }: RevisionMetaDialogProps) => {
  const [label, setLabel] = useState(document.version_label ?? '');
  const [effectiveDate, setEffectiveDate] = useState(document.effective_date ?? '');
  const update = useUpdateRevisionMeta(kbId);

  if (!isOpen) return null;

  const close = () => {
    if (update.isPending) return;
    update.reset();
    onClose();
  };
  const submit = () =>
    update.mutate(
      {
        documentId: document.document_id,
        body: {
          version_label: label.trim() || null,
          effective_date: effectiveDate || null,
        },
      },
      { onSuccess: close },
    );

  return (
    <Modal
      onClose={close}
      title="버전 정보 수정"
      subtitle={`${document.filename} · v${document.version_no ?? 1}`}
      size="sm"
      disableClose={update.isPending}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close} disabled={update.isPending}>
            취소
          </Button>
          <Button variant="primary" onClick={submit} isPending={update.isPending}>
            저장
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <Input
          label="버전 라벨"
          maxLength={100}
          placeholder="예: 2026-11 개정"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Input
          label="시행일"
          type="date"
          hint="표시용입니다. 검색 전환 시점에는 영향이 없습니다."
          value={effectiveDate}
          onChange={(e) => setEffectiveDate(e.target.value)}
        />
        {update.isError && (
          <p role="alert" className="rounded-md bg-danger-bg px-3 py-2 text-sm text-danger">
            {revisionErrorMessage(update.error)}
          </p>
        )}
      </div>
    </Modal>
  );
};

export default RevisionMetaDialog;
