import { Link } from 'react-router-dom';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import { SCOPE_LABELS } from '@/types/collection';

interface KnowledgeBaseTableProps {
  knowledgeBases: KnowledgeBaseInfo[];
  isLoading: boolean;
  isError: boolean;
  currentUserId: number | null;
  currentUserRole: string | null;
  onCreate: () => void;
  onDelete: (kbId: string) => void;
  onRefresh: () => void;
}

/** kb-management-ui D8: 삭제 버튼은 소유자/관리자에게만 표시 (실권한은 백엔드 403) */
const canDelete = (
  kb: KnowledgeBaseInfo,
  userId: number | null,
  role: string | null,
) => role === 'admin' || (userId !== null && kb.owner_id === userId);

const KnowledgeBaseTable = ({
  knowledgeBases,
  isLoading,
  isError,
  currentUserId,
  currentUserRole,
  onCreate,
  onDelete,
  onRefresh,
}: KnowledgeBaseTableProps) => {
  if (isLoading) {
    return (
      <p className="py-12 text-center text-[14px] text-zinc-400">
        지식베이스 목록을 불러오는 중...
      </p>
    );
  }

  if (isError) {
    return (
      <div className="py-12 text-center">
        <p className="text-[14px] text-red-500">
          지식베이스 목록을 불러오지 못했습니다
        </p>
        <button
          onClick={onRefresh}
          className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-[13px] text-zinc-400">
          총 {knowledgeBases.length}개
        </p>
        <button
          onClick={onCreate}
          className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          + 새 지식베이스
        </button>
      </div>

      {knowledgeBases.length === 0 ? (
        <p className="py-12 text-center text-[14px] text-zinc-400">
          아직 지식베이스가 없습니다. 새 지식베이스를 만들어 문서를
          업로드해보세요.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-2xl border border-zinc-200">
          <table className="w-full text-left text-[14px]">
            <thead className="bg-zinc-50 text-[12px] text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">이름</th>
                <th className="px-4 py-3 font-medium">공개 범위</th>
                <th className="px-4 py-3 font-medium">설명</th>
                <th className="px-4 py-3 font-medium">컬렉션</th>
                <th className="px-4 py-3 font-medium">생성일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {knowledgeBases.map((kb) => (
                <tr key={kb.kb_id} className="hover:bg-zinc-50/60">
                  <td className="px-4 py-3">
                    <Link
                      to={`/knowledge-bases/${kb.kb_id}`}
                      className="font-medium text-violet-600 hover:underline"
                    >
                      {kb.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${SCOPE_LABELS[kb.scope].bg} ${SCOPE_LABELS[kb.scope].color}`}
                    >
                      {SCOPE_LABELS[kb.scope].label}
                    </span>
                  </td>
                  <td className="max-w-[280px] truncate px-4 py-3 text-zinc-500">
                    {kb.description || '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-[12.5px] text-zinc-500">
                    {kb.collection_name}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">
                    {kb.created_at ? kb.created_at.slice(0, 10) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {canDelete(kb, currentUserId, currentUserRole) && (
                      <button
                        onClick={() => onDelete(kb.kb_id)}
                        aria-label={`${kb.name} 삭제`}
                        className="rounded-lg border border-red-200 px-3 py-1.5 text-[12.5px] font-medium text-red-500 transition-all hover:bg-red-50"
                      >
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default KnowledgeBaseTable;
