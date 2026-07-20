// wiki-user-facing: 위키 문서 단독 뷰 — 채팅 근거 배지(SourceCitation)의 착지점.
import { Link, useParams } from 'react-router-dom';

import { useWikiArticle } from '@/hooks/useWiki';
import { WIKI_STATUS_LABELS } from '@/types/wiki';

const KnowledgeArticlePage = () => {
  const { articleId } = useParams<{ articleId: string }>();
  const { data: article, isLoading, isError } = useWikiArticle(articleId ?? '');

  if (isLoading) {
    return <div className="p-8 text-sm text-zinc-500">문서를 불러오는 중…</div>;
  }
  if (isError || !article) {
    return (
      <div className="p-8 text-sm text-zinc-500">
        문서를 찾을 수 없습니다. 삭제되었거나 접근할 수 없는 문서입니다.
      </div>
    );
  }

  const statusMeta = WIKI_STATUS_LABELS[article.status];

  return (
    <div className="mx-auto max-w-3xl p-8">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-zinc-400">
        <span>📖 지식 문서</span>
        {article.path && <span>· {article.path}</span>}
        <span className={`rounded px-1.5 py-0.5 ${statusMeta.color}`}>
          {statusMeta.label}
        </span>
      </div>
      <h1 className="mb-4 text-xl font-bold text-zinc-800">{article.title}</h1>
      <div className="whitespace-pre-wrap rounded-lg border border-zinc-200 bg-white p-5 text-sm leading-6 text-zinc-700">
        {article.content}
      </div>
      <div className="mt-4 flex items-center justify-between text-[11px] text-zinc-400">
        <span>
          출처: {article.source_refs.join(', ')} · v{article.version}
          {article.updated_at && ` · 갱신 ${article.updated_at.slice(0, 10)}`}
        </span>
        <Link
          to={`/agents/${article.agent_id}/knowledge`}
          className="text-violet-600 hover:underline"
        >
          이 에이전트의 전체 지식 보기 →
        </Link>
      </div>
    </div>
  );
};

export default KnowledgeArticlePage;
