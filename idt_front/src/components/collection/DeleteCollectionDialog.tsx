import ConfirmDialog from '@/components/common/ConfirmDialog';

interface DeleteCollectionDialogProps {
  isOpen: boolean;
  collectionName: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}

const DeleteCollectionDialog = ({
  isOpen,
  collectionName,
  onClose,
  onConfirm,
  isPending,
  error,
}: DeleteCollectionDialogProps) => (
  <ConfirmDialog
    isOpen={isOpen}
    title="컬렉션 삭제"
    description={
      <>
        &lsquo;{collectionName}&rsquo; 컬렉션을 삭제하시겠습니까?
        <br />
        <span className="text-red-500">이 작업은 되돌릴 수 없습니다.</span>
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

export default DeleteCollectionDialog;
