// Design Ref: kb-document-management §5.4 — DeleteKnowledgeBaseDialog와 같은 ConfirmDialog 래퍼
import ConfirmDialog from '@/components/common/ConfirmDialog';

interface DeleteKbDocumentDialogProps {
  isOpen: boolean;
  filename: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}

const DeleteKbDocumentDialog = ({
  isOpen,
  filename,
  onClose,
  onConfirm,
  isPending,
  error,
}: DeleteKbDocumentDialogProps) => (
  <ConfirmDialog
    isOpen={isOpen}
    title="문서 삭제"
    description={
      <>
        <span className="font-semibold text-fg">{filename}</span> 문서를
        삭제할까요? 삭제하면 복구할 수 없으며 이 문서의 청크와 요약이 검색에서
        제외됩니다.
      </>
    }
    confirmLabel="삭제"
    variant="danger"
    onClose={onClose}
    onConfirm={onConfirm}
    isPending={isPending}
    error={error}
  />
);

export default DeleteKbDocumentDialog;
