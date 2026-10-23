// Design Ref: ui-redesign-chat §5.3 — PageHeader(compact) + Badge + IconButton. props 변경 없음.
import { Link } from 'react-router-dom';
import { Download, FolderOpen, Trash2 } from 'lucide-react';
import Badge from '@/components/ui/Badge';
import IconButton from '@/components/ui/IconButton';
import PageHeader from '@/components/ui/PageHeader';

interface ChatHeaderProps {
  title?: string;
  messageCount?: number;
  /** wiki-navigation S3: 사용자 에이전트 선택 시에만 전달. 없으면 워크스페이스 링크 미노출 */
  agentId?: string | null;
}

const ChatHeader = ({ title = '새 대화', messageCount = 0, agentId }: ChatHeaderProps) => (
  <PageHeader
    compact
    title={
      <span className="flex items-center gap-2">
        <span className="truncate">{title}</span>
        {messageCount > 0 && <Badge tone="neutral">{messageCount}</Badge>}
      </span>
    }
    actions={
      <>
        {agentId && (
          <Link
            to={`/agents/${agentId}/workspace`}
            title="에이전트 워크스페이스"
            aria-label="에이전트 워크스페이스"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-fg-subtle transition-colors duration-150 hover:bg-surface-sunken hover:text-fg"
          >
            <FolderOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          </Link>
        )}
        <Badge tone="success" dot pulse className="hidden sm:inline-flex">
          RAG · Agent
        </Badge>
        <IconButton aria-label="대화 내보내기">
          <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
        <IconButton aria-label="대화 삭제" tone="danger">
          <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
        </IconButton>
      </>
    }
  />
);

export default ChatHeader;
