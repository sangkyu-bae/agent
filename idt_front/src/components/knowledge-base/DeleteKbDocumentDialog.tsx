// Design Ref: kb-document-management §5.4 — DeleteKnowledgeBaseDialog와 같은 ConfirmDialog 래퍼
// document-revision §4.2 #9: 이전 버전이 있으면 "이전 버전을 다시 검색에 사용" 선택(기본 켬)
import ConfirmDialog from '@/components/common/ConfirmDialog';

interface DeleteKbDocumentDialogProps {
  isOpen: boolean;
  filename: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
  /** 삭제 대상이 v2 이상이면 직전 버전 번호, 아니면 생략 */
  previousVersionNo?: number | null;
  restorePrevious?: boolean;
  onRestorePreviousChange?: (value: boolean) => void;
}

const DeleteKbDocumentDialog = ({
  isOpen,
  filename,
  onClose,
  onConfirm,
  isPending,
  error,
  previousVersionNo,
  restorePrevious = true,
  onRestorePreviousChange,
}: DeleteKbDocumentDialogProps) => (
  <ConfirmDialog
    isOpen={isOpen}
    title="문서 삭제"
    description={
      <>
        <span className="font-semibold text-fg">{filename}</span> 문서를
        삭제할까요? 삭제하면 복구할 수 없으며 이 문서의 청크와 요약이 검색에서
        제외됩니다.
        {previousVersionNo && onRestorePreviousChange && (
          <span className="mt-3 block">
            <label className="flex items-center gap-2 text-fg-secondary">
              <input
                type="checkbox"
                checked={restorePrevious}
                onChange={(e) => onRestorePreviousChange(e.target.checked)}
              />
              이전 버전(v{previousVersionNo})을 다시 검색에 사용
            </label>
            {!restorePrevious && (
              <span className="mt-1 block text-warning">
                이 문서의 모든 버전이 검색에서 빠집니다.
              </span>
            )}
          </span>
        )}
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
