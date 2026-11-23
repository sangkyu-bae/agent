// Design Ref: document-revision §5.1 — 문서 행을 펼쳤을 때의 계보 버전 목록.
import Badge from '@/components/ui/Badge';
import { useDocumentVersions } from '@/hooks/useDocumentRevision';

interface DocumentVersionHistoryProps {
  kbId: string;
  documentId: string;
}

const day = (iso: string | null) => (iso ? iso.slice(0, 10) : null);

const DocumentVersionHistory = ({ kbId, documentId }: DocumentVersionHistoryProps) => {
  const { data, isLoading, isError } = useDocumentVersions(kbId, documentId);

  if (isLoading) {
    return <p className="text-sm text-fg-muted">버전 이력을 불러오는 중...</p>;
  }
  if (isError || !data) {
    return <p className="text-sm text-danger">버전 이력을 불러오지 못했습니다.</p>;
  }

  return (
    <ol className="space-y-1.5" aria-label="버전 이력">
      {data.versions.map((v) => {
        const uploaded = day(v.created_at);
        return (
          <li
            key={v.document_id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-secondary"
          >
            <span className="font-semibold text-fg">v{v.version_no}</span>
            {v.version_label && <span>{v.version_label}</span>}
            <span className="text-fg-muted">{v.filename}</span>
            {v.effective_date && (
              <span className="text-fg-muted">시행 {v.effective_date}</span>
            )}
            {uploaded && <span className="text-fg-muted">{uploaded} 업로드</span>}
            {v.revision_status === 'active' ? (
              <Badge tone="success">현재</Badge>
            ) : (
              <Badge tone="neutral">대체됨</Badge>
            )}
            {v.sync_state === 'pending' && <Badge tone="warning">반영 대기</Badge>}
          </li>
        );
      })}
    </ol>
  );
};

export default DocumentVersionHistory;
