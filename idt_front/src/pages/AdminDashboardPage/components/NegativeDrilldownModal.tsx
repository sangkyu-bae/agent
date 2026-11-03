// Design Ref: negative-feedback-drilldown §5 — 👎 답변의 질문·답변·근거·런 링크 모달.
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import MarkdownRenderer from '@/components/chat/MarkdownRenderer';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import { useNegativeDrilldown } from '@/hooks/useMessageFeedback';
import { ApiError } from '@/services/api/ApiError';
import type { RetrievalDto } from '@/types/agentRunAdmin';
import type {
  MessageRunRetrievals,
  NegativeDrilldown,
  QueryRetrievalGroup,
  RecentNegativeItem,
} from '@/types/messageFeedback';
import { formatLocalDateTime } from '@/utils/formatters';

interface NegativeDrilldownModalProps {
  item: RecentNegativeItem;
  onClose: () => void;
}

const LINK_CLASS = 'text-sm font-medium text-brand-700 hover:underline';

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section>
    <h3 className="mb-1.5 text-xs font-medium text-fg-subtle">{title}</h3>
    {children}
  </section>
);

const Notice = ({ children }: { children: ReactNode }) => (
  <p className="text-sm text-fg-muted">{children}</p>
);

const SourceRow = ({ source }: { source: RetrievalDto }) => (
  <li className="text-sm">
    <p className="text-fg-secondary">
      {source.rank_index !== null && `${source.rank_index}. `}
      {source.collection_name}
      {source.score !== null && ` · ${source.score.toFixed(2)}`}
    </p>
    {source.content_preview && (
      <p className="mt-0.5 line-clamp-2 text-fg-muted">{source.content_preview}</p>
    )}
  </li>
);

const GroupBlock = ({ group }: { group: QueryRetrievalGroup }) => (
  <div>
    <p className="mb-1 text-sm font-medium text-fg">
      {group.search_query ?? '쿼리 정보 없음'}
      {group.search_mode && (
        <span className="ml-2 text-xs font-normal text-fg-subtle">{group.search_mode}</span>
      )}
    </p>
    <ul className="space-y-1.5">
      {group.sources.map((source) => (
        <SourceRow key={source.id} source={source} />
      ))}
    </ul>
  </div>
);

const RunCard = ({ run }: { run: MessageRunRetrievals }) => (
  <div className="rounded-xl border border-border bg-surface p-4">
    <div className="mb-2 flex items-center justify-between gap-3">
      <span className="font-mono text-xs text-fg-subtle">실행 {run.run_id.slice(0, 8)}</span>
      <div className="flex items-center gap-3">
        <Link to={`/admin/agent-runs/${run.run_id}`} className={LINK_CLASS}>
          런 상세
        </Link>
        {run.langsmith_run_url && (
          <a
            href={run.langsmith_run_url}
            target="_blank"
            rel="noopener noreferrer"
            className={LINK_CLASS}
          >
            LangSmith
          </a>
        )}
      </div>
    </div>
    {run.groups.length === 0 ? (
      <Notice>이 실행은 문서 검색을 사용하지 않았습니다</Notice>
    ) : (
      <div className="space-y-3">
        {run.groups.map((group, index) => (
          <GroupBlock key={`${group.search_query ?? ''}-${index}`} group={group} />
        ))}
      </div>
    )}
  </div>
);

const DrilldownBody = ({
  data,
  comment,
}: {
  data: NegativeDrilldown;
  comment: string | null | undefined;
}) => (
  <div className="space-y-5">
    <Section title="👎 이유">
      <p className="whitespace-pre-wrap text-base text-fg">{comment || '코멘트 없음'}</p>
    </Section>
    <Section title="질문">
      {data.question === null ? (
        <Notice>질문을 찾지 못했습니다</Notice>
      ) : (
        <p className="whitespace-pre-wrap text-base text-fg">{data.question}</p>
      )}
    </Section>
    <Section title="답변">
      <div className="rounded-xl bg-surface-muted p-4 text-base leading-[1.7] text-fg">
        <MarkdownRenderer content={data.answer} />
      </div>
    </Section>
    {/* Plan FR-13: 질문 복원 실패 시 런을 조회하지 않으므로 근거 영역을 그리지 않는다 */}
    {data.question !== null && (
      <Section title="실행 근거">
        {data.runs.length === 0 ? (
          <Notice>연결된 실행 기록이 없습니다</Notice>
        ) : (
          <div className="space-y-3">
            {data.runs.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </div>
        )}
      </Section>
    )}
  </div>
);

const NegativeDrilldownModal = ({ item, onClose }: NegativeDrilldownModalProps) => {
  const { data, isLoading, error, refetch, isFetching } = useNegativeDrilldown(item.message_id);
  const isNotFound = error instanceof ApiError && error.status === 404;
  const evaluatedAt = formatLocalDateTime(item.created_at);

  return (
    <Modal
      onClose={onClose}
      title="답변 드릴다운"
      subtitle={evaluatedAt ? `${item.agent_id} · ${evaluatedAt}` : item.agent_id}
      size="3xl"
      scroll="body"
    >
      {isLoading && <Notice>불러오는 중…</Notice>}
      {isNotFound && <Notice>원본 대화를 찾을 수 없습니다</Notice>}
      {error && !isNotFound && (
        <div className="flex items-center gap-3">
          <Notice>불러오지 못했습니다</Notice>
          <Button
            variant="secondary"
            size="sm"
            isPending={isFetching}
            pendingText="다시 시도 중…"
            onClick={() => void refetch()}
          >
            다시 시도
          </Button>
        </div>
      )}
      {data && !error && <DrilldownBody data={data} comment={item.comment} />}
    </Modal>
  );
};

export default NegativeDrilldownModal;
