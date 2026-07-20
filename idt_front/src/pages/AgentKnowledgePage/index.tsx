// wiki-user-facing: 에이전트 지식 브라우저 — path 트리 탐색 + 문서 뷰 + 소유자 작성/관리.
// 저장은 DB, 경험은 파일 위키(폴더·문서성). 서버가 최종 인가 — 프론트는 표시 제어만.
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useAgentDetail } from '@/hooks/useAgentStore';
import {
  useCreateWiki,
  useDeprecateArticle,
  useUpdateArticle,
  useWikiArticle,
  useWikiTree,
} from '@/hooks/useWiki';
import { useAuthStore } from '@/store/authStore';
import {
  WIKI_STATUS_LABELS,
  type WikiTreeGroup,
  type WikiTreeItem,
} from '@/types/wiki';

const UNCLASSIFIED_LABEL = '미분류';

/** 설계 결정 ⑥: 서버는 path 문자열 그룹만 주고, 계층은 프론트가 `/` split로 조립한다. */
interface FolderNode {
  name: string;
  children: Map<string, FolderNode>;
  items: WikiTreeItem[];
}

const buildFolderTree = (groups: WikiTreeGroup[]): FolderNode => {
  const root: FolderNode = { name: '', children: new Map(), items: [] };
  groups.forEach((group) => {
    if (group.path === null) return; // 미분류는 별도 렌더
    let node = root;
    group.path.split('/').forEach((segment) => {
      let child = node.children.get(segment);
      if (!child) {
        child = { name: segment, children: new Map(), items: [] };
        node.children.set(segment, child);
      }
      node = child;
    });
    node.items.push(...group.items);
  });
  return root;
};

interface ArticleFormState {
  title: string;
  content: string;
  path: string;
}

const emptyForm: ArticleFormState = { title: '', content: '', path: '' };

const AgentKnowledgePage = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const { data: tree } = useWikiTree(agentId ?? '');
  const { data: agent } = useAgentDetail(agentId ?? null);
  const { user } = useAuthStore();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ArticleFormState>(emptyForm);

  const { data: article } = useWikiArticle(selectedId ?? '');
  const createMutation = useCreateWiki();
  const updateMutation = useUpdateArticle();
  const deprecateMutation = useDeprecateArticle();

  const isOwner = Boolean(
    agent && user && agent.owner_user_id === String(user.id),
  );
  const knownPaths = useMemo(
    () =>
      (tree?.groups ?? [])
        .map((g) => g.path)
        .filter((p): p is string => p !== null),
    [tree],
  );
  const folderTree = useMemo(
    () => buildFolderTree(tree?.groups ?? []),
    [tree],
  );
  const unclassified = useMemo(
    () => (tree?.groups ?? []).find((g) => g.path === null)?.items ?? [],
    [tree],
  );

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setFormOpen(true);
  };

  const openEdit = () => {
    if (!article) return;
    setEditingId(article.id);
    setForm({
      title: article.title,
      content: article.content,
      path: article.path ?? '',
    });
    setFormOpen(true);
  };

  const submitForm = async () => {
    const path = form.path.trim() === '' ? null : form.path.trim();
    if (editingId) {
      await updateMutation.mutateAsync({
        id: editingId,
        data: { title: form.title, content: form.content, path },
      });
    } else {
      await createMutation.mutateAsync({
        agent_id: agentId ?? '',
        title: form.title,
        content: form.content,
        path,
      });
    }
    setFormOpen(false);
  };

  return (
    <div className="flex h-full">
      {/* 트리 패널 */}
      <aside className="w-72 shrink-0 overflow-y-auto border-r border-zinc-200 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-zinc-700">
            📖 지식 {tree ? `(${tree.total})` : ''}
          </h2>
          {/* agent-workspace-view: 워크스페이스 상호 링크 */}
          <Link
            to={`/agents/${agentId}/workspace`}
            className="text-[11px] text-violet-600 hover:underline"
          >
            워크스페이스 →
          </Link>
          {isOwner && (
            <button
              onClick={openCreate}
              className="rounded bg-violet-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-violet-700"
            >
              문서 작성
            </button>
          )}
        </div>
        {[...folderTree.children.values()].map((node) => (
          <Folder
            key={node.name}
            node={node}
            depth={0}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ))}
        {unclassified.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 text-[11px] font-semibold text-zinc-500">
              📁 {UNCLASSIFIED_LABEL}
            </p>
            <ItemList
              items={unclassified}
              depth={0}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
        )}
        {tree && tree.total === 0 && (
          <p className="text-xs text-zinc-400">등록된 지식이 없습니다.</p>
        )}
      </aside>

      {/* 문서 뷰 패널 */}
      <main className="flex-1 overflow-y-auto p-6">
        {formOpen ? (
          <div className="mx-auto max-w-2xl">
            <h3 className="mb-3 text-sm font-bold text-zinc-700">
              {editingId ? '문서 수정' : '새 지식 문서'}
            </h3>
            <input
              aria-label="제목"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="제목"
              className="mb-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm"
            />
            <input
              aria-label="분류 경로"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              placeholder="분류 경로 (예: 여신/한도 — 비우면 미분류)"
              list="known-paths"
              className="mb-2 w-full rounded border border-zinc-300 px-3 py-2 text-sm"
            />
            <datalist id="known-paths">
              {knownPaths.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
            <textarea
              aria-label="본문"
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              placeholder="이 에이전트가 알아야 할 내용을 작성하세요"
              rows={10}
              className="mb-3 w-full rounded border border-zinc-300 px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                onClick={submitForm}
                disabled={!form.title.trim() || !form.content.trim()}
                className="rounded bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
              >
                저장
              </button>
              <button
                onClick={() => setFormOpen(false)}
                className="rounded border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600"
              >
                취소
              </button>
            </div>
          </div>
        ) : article ? (
          <div className="mx-auto max-w-2xl">
            <div className="mb-1 flex items-center gap-2 text-[11px] text-zinc-400">
              {article.path && <span>{article.path}</span>}
              <span
                className={`rounded px-1.5 py-0.5 ${WIKI_STATUS_LABELS[article.status].color}`}
              >
                {WIKI_STATUS_LABELS[article.status].label}
              </span>
              <span>· {article.source_type}</span>
            </div>
            <h3 className="mb-3 text-lg font-bold text-zinc-800">
              {article.title}
            </h3>
            <div className="whitespace-pre-wrap rounded-lg border border-zinc-200 bg-white p-4 text-sm leading-6 text-zinc-700">
              {article.content}
            </div>
            <p className="mt-2 text-[11px] text-zinc-400">
              출처: {article.source_refs.join(', ')} · v{article.version}
              {article.updated_at && ` · 갱신 ${article.updated_at.slice(0, 10)}`}
            </p>
            {isOwner && article.source_type === 'human' && (
              <div className="mt-3 flex gap-2">
                <button
                  onClick={openEdit}
                  className="rounded border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50"
                >
                  수정
                </button>
                <button
                  onClick={() => deprecateMutation.mutate(article.id)}
                  className="rounded border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
                >
                  폐기
                </button>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-zinc-400">
            왼쪽 트리에서 문서를 선택하세요.
          </p>
        )}
      </main>
    </div>
  );
};

interface TreeSelectionProps {
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const Folder = ({
  node,
  depth,
  selectedId,
  onSelect,
}: TreeSelectionProps & { node: FolderNode }) => (
  <div className="mb-1" style={{ paddingLeft: depth * 12 }}>
    <p className="mb-1 text-[11px] font-semibold text-zinc-500">
      📁 {node.name}
    </p>
    <ItemList
      items={node.items}
      depth={depth + 1}
      selectedId={selectedId}
      onSelect={onSelect}
    />
    {[...node.children.values()].map((child) => (
      <Folder
        key={child.name}
        node={child}
        depth={depth + 1}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    ))}
  </div>
);

const ItemList = ({
  items,
  depth,
  selectedId,
  onSelect,
}: TreeSelectionProps & { items: WikiTreeItem[] }) => (
  <ul style={{ paddingLeft: depth * 12 }}>
    {items.map((item) => (
      <li key={item.id}>
        <button
          onClick={() => onSelect(item.id)}
          className={`w-full truncate rounded px-2 py-1 text-left text-xs ${
            selectedId === item.id
              ? 'bg-violet-50 font-semibold text-violet-700'
              : 'text-zinc-600 hover:bg-zinc-50'
          }`}
        >
          {item.title}
        </button>
      </li>
    ))}
  </ul>
);

export default AgentKnowledgePage;
