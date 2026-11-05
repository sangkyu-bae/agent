// Design Ref: ui-redesign-chat §5.3 — PageHeader(compact) + Badge + IconButton. props 변경 없음.
import { Link } from 'react-router-dom';
import { Download, FolderOpen, Pencil, Trash2 } from 'lucide-react';
import Badge from '@/components/ui/Badge';
import IconButton from '@/components/ui/IconButton';
import PageHeader from '@/components/ui/PageHeader';
import { buildAgentEditPath } from '@/utils/agentEditLink';

interface ChatHeaderProps {
  title?: string;
  messageCount?: number;
  /** wiki-navigation S3: 사용자 에이전트 선택 시에만 전달. 없으면 워크스페이스 링크 미노출 */
  agentId?: string | null;
  /** agent-edit-entry FR-07: 내 에이전트(owned·forked)일 때만 수정 링크 노출 */
  canEdit?: boolean;
}

const HEADER_LINK_CLASS =
  'inline-flex h-9 w-9 items-center justify-center rounded-md text-fg-subtle transition-colors duration-150 hover:bg-surface-sunken hover:text-fg';

const ChatHeader = ({ title = '새 대화', messageCount = 0, agentId, canEdit = false }: ChatHeaderProps) => (
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
        {agentId && canEdit && (
          <Link
            to={buildAgentEditPath(agentId, '/chatpage')}
            title="에이전트 수정"
            aria-label="에이전트 수정"
            className={HEADER_LINK_CLASS}
          >
            <Pencil className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          </Link>
        )}
        {agentId && (
          <Link
            to={`/agents/${agentId}/workspace`}
            title="에이전트 워크스페이스"
            aria-label="에이전트 워크스페이스"
            className={HEADER_LINK_CLASS}
          >
            <FolderOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
          </Link>
        )}
        {/* cn 은 클래스를 병합하지 않아 Badge 의 inline-flex 가 hidden 을 이긴다 → 숨김은 감싸는 요소가 맡는다 */}
        <span className="hidden sm:inline-flex">
          <Badge tone="success" dot pulse>
            RAG · Agent
          </Badge>
        </span>
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
