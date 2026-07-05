// LLM-WIKI-001: 위키 상세/편집 패널 (본문 미리보기 + source_refs + 편집).
import { useState } from 'react';

import Modal from '@/components/common/Modal';
import { useUpdateArticle } from '@/hooks/useWiki';
import { WIKI_STATUS_LABELS } from '@/types/wiki';
import type { WikiArticle } from '@/types/wiki';

interface WikiDetailPanelProps {
  article: WikiArticle;
  currentUserId: string;
  onClose: () => void;
}

const WikiDetailPanel = ({
  article,
  currentUserId,
  onClose,
}: WikiDetailPanelProps) => {
  const [editMode, setEditMode] = useState(false);
  const [title, setTitle] = useState(article.title);
  const [content, setContent] = useState(article.content);
  const update = useUpdateArticle();

  const canSave =
    currentUserId !== '' && title.trim() !== '' && content.trim() !== '';

  const handleSave = () => {
    if (!canSave) return;
    update.mutate(
      { id: article.id, data: { title, content, editor_id: currentUserId } },
      { onSuccess: () => setEditMode(false) },
    );
  };

  const badge = WIKI_STATUS_LABELS[article.status];

  return (
    <Modal
      size="2xl"
      scroll="content"
      onClose={onClose}
      footer={
        editMode ? (
          <>
            <button
              onClick={() => setEditMode(false)}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              onClick={handleSave}
              disabled={!canSave || update.isPending}
              className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white hover:bg-violet-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {update.isPending ? '저장 중…' : '저장'}
            </button>
          </>
        ) : (
          <>
            <button
              onClick={onClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-100"
            >
              닫기
            </button>
            <button
              onClick={() => setEditMode(true)}
              className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white hover:bg-violet-700 active:scale-95"
            >
              편집
            </button>
          </>
        )
      }
    >
      {/* 헤더 */}
      <div className="mb-4 flex items-start justify-between gap-3">
        {editMode ? (
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label="제목"
            className="flex-1 rounded-xl border border-zinc-300 px-3 py-2 text-[15px] outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        ) : (
          <h2 className="text-xl font-bold text-zinc-900">{article.title}</h2>
        )}
        <span className={`shrink-0 rounded-lg px-2 py-1 text-[12px] ${badge.color}`}>
          {badge.label}
        </span>
      </div>

      {/* 메타 */}
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-zinc-500">
        <span>출처유형: {article.source_type}</span>
        <span>신뢰도: {article.confidence.toFixed(2)}</span>
        <span>버전: v{article.version}</span>
      </div>

      {/* 본문 */}
      <div className="mb-4">
        <h3 className="mb-1.5 text-[13px] font-semibold text-zinc-700">본문</h3>
        {editMode ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            aria-label="본문"
            rows={8}
            className="block w-full resize-none rounded-xl border border-zinc-300 px-3 py-2 text-[14px] leading-relaxed outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
          />
        ) : (
          <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-zinc-800">
            {article.content}
          </p>
        )}
      </div>

      {/* 출처 추적 */}
      <div>
        <h3 className="mb-1.5 text-[13px] font-semibold text-zinc-700">
          출처 ({article.source_refs.length})
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {article.source_refs.map((ref) => (
            <span
              key={ref}
              className="rounded-lg bg-zinc-100 px-2 py-1 text-[12px] text-zinc-600"
            >
              {ref}
            </span>
          ))}
        </div>
      </div>
    </Modal>
  );
};

export default WikiDetailPanel;
