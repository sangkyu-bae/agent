// Design Ref: document-revision §4.2 #3·#8 — 검색 제외 표식 반영 실패 문서 재시도.
import Button from '@/components/ui/Button';
import { useRetryRevisionSync } from '@/hooks/useDocumentRevision';
import type { DocumentVersion } from '@/types/knowledgeBase';
import { revisionErrorMessage } from './revisionErrors';

interface PendingSyncBannerProps {
  kbId: string;
  items: DocumentVersion[];
}

const PendingSyncBanner = ({ kbId, items }: PendingSyncBannerProps) => {
  const retry = useRetryRevisionSync(kbId);

  if (items.length === 0) return null;

  return (
    <div
      role="alert"
      className="mt-4 space-y-2 rounded-xl border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning"
    >
      <p className="font-semibold">
        검색 제외 반영이 끝나지 않은 문서가 있습니다. 반영 전까지는 이전 버전도 함께
        검색될 수 있습니다.
      </p>
      <ul className="space-y-1.5">
        {items.map((v) => {
          const name = `${v.filename} v${v.version_no}`;
          return (
            <li key={v.document_id} className="flex items-center justify-between gap-3">
              <span>
                {name} ({v.revision_status === 'superseded' ? '이전 버전' : '현재 버전'})
              </span>
              <Button
                size="sm"
                variant="secondary"
                aria-label={`${name} 다시 반영`}
                isPending={retry.isPending && retry.variables === v.document_id}
                onClick={() => retry.mutate(v.document_id)}
              >
                다시 반영
              </Button>
            </li>
          );
        })}
      </ul>
      {retry.isError && <p>{revisionErrorMessage(retry.error)}</p>}
    </div>
  );
};

export default PendingSyncBanner;
