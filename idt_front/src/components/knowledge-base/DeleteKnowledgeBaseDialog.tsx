import ConfirmDialog from '@/components/common/ConfirmDialog';

interface DeleteKnowledgeBaseDialogProps {
  isOpen: boolean;
  kbName: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}

const DeleteKnowledgeBaseDialog = ({
  isOpen,
  kbName,
  onClose,
  onConfirm,
  isPending,
  error,
}: DeleteKnowledgeBaseDialogProps) => (
  <ConfirmDialog
    isOpen={isOpen}
    title="지식베이스 삭제"
    description={
      <>
        <span className="font-semibold text-zinc-900">{kbName}</span>{' '}
        지식베이스를 삭제할까요? 삭제 후에도 저장된 벡터 데이터는 정리
        작업 전까지 남아 있습니다.
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

export default DeleteKnowledgeBaseDialog;
