import { useState } from 'react';
import { Layers, Hash, X, FileText, Info } from 'lucide-react';
import type { Document, DocumentChunk } from '@/types/rag';

interface ChunkViewerProps {
  document: Document;
  chunks: DocumentChunk[];
  isLoading: boolean;
}

interface ChunkMetaModalProps {
  chunk: DocumentChunk;
  onClose: () => void;
}

const ChunkSkeleton = () => (
  <div className="animate-pulse space-y-3 rounded-2xl border border-zinc-100 bg-zinc-50 p-4">
    <div className="flex items-center gap-2">
      <div className="h-6 w-6 rounded-lg bg-zinc-200" />
      <div className="h-4 w-20 rounded bg-zinc-200" />
    </div>
    <div className="space-y-2">
      <div className="h-3 rounded bg-zinc-200" />
      <div className="h-3 w-5/6 rounded bg-zinc-200" />
      <div className="h-3 w-4/6 rounded bg-zinc-200" />
    </div>
  </div>
);

const ChunkMetaModal = ({ chunk, onClose }: ChunkMetaModalProps) => {
  const systemMeta = [
    { label: 'Chunk ID', value: chunk.id },
    { label: 'Document ID', value: chunk.documentId },
    { label: 'Chunk Index', value: `#${chunk.chunkIndex}` },
    { label: 'Token Count', value: `${chunk.tokenCount} tokens` },
  ];

  const extraMeta = chunk.metadata ? Object.entries(chunk.metadata) : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 */}
        <div className="flex items-center justify-between rounded-t-2xl border-b border-zinc-100 px-5 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-xl shadow-sm"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <Info className="h-4 w-4 text-white" />
            </div>
            <div>
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
                청크 메타데이터
              </p>
              <p className="text-[14px] font-semibold text-zinc-900">
                청크 #{chunk.chunkIndex}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-xl text-zinc-400 transition-all hover:bg-zinc-100 hover:text-zinc-600"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 시스템 메타데이터 */}
        <div className="px-5 pt-4">
          <p className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
            <Hash className="h-3 w-3" />
            시스템 정보
          </p>
          <div className="overflow-hidden rounded-xl border border-zinc-100 bg-zinc-50">
            {systemMeta.map(({ label, value }, idx) => (
              <div
                key={label}
                className={`flex items-start gap-4 px-4 py-2.5 ${idx !== systemMeta.length - 1 ? 'border-b border-zinc-100' : ''}`}
              >
                <span className="w-28 shrink-0 text-[12px] font-medium text-zinc-400">{label}</span>
                <span className="break-all text-[12px] font-mono text-zinc-700">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 추가 메타데이터 (있을 경우) */}
        {extraMeta.length > 0 && (
          <div className="px-5 pt-3">
            <p className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
              <Info className="h-3 w-3" />
              추가 메타데이터
            </p>
            <div className="overflow-hidden rounded-xl border border-zinc-100 bg-zinc-50">
              {extraMeta.map(([key, val], idx) => (
                <div
                  key={key}
                  className={`flex items-start gap-4 px-4 py-2.5 ${idx !== extraMeta.length - 1 ? 'border-b border-zinc-100' : ''}`}
                >
                  <span className="w-28 shrink-0 text-[12px] font-medium text-zinc-400">{key}</span>
                  <span className="break-all text-[12px] font-mono text-zinc-700">
                    {typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 청크 내용 전문 */}
        <div className="px-5 pt-3 pb-5">
          <p className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
            <FileText className="h-3 w-3" />
            내용 전문
          </p>
          <div className="max-h-48 overflow-y-auto rounded-xl border border-zinc-100 bg-zinc-50 px-4 py-3">
            <p className="whitespace-pre-wrap text-[13px] leading-[1.7] text-zinc-700">
              {chunk.content}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

const ChunkViewer = ({ document, chunks, isLoading }: ChunkViewerProps) => {
  const [selectedChunk, setSelectedChunk] = useState<DocumentChunk | null>(null);

  return (
    <div className="mt-6">
      {/* 헤더 */}
      <div className="mb-4 flex items-center gap-3">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-xl shadow-sm"
          style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
        >
          <Layers className="h-4 w-4 text-white" />
        </div>
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">청킹 결과</p>
          <p className="text-[15px] font-semibold text-zinc-900">{document.name}</p>
        </div>
        {!isLoading && (
          <span className="ml-auto rounded-full bg-violet-100 px-3 py-1 text-[12px] font-semibold text-violet-600">
            총 {chunks.length}개 청크
          </span>
        )}
      </div>

      {/* 청크 그리드 */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <ChunkSkeleton key={i} />)}
        </div>
      ) : chunks.length === 0 ? (
        <div className="flex items-center justify-center rounded-2xl border border-dashed border-zinc-200 py-12 text-zinc-400">
          <p className="text-[14px]">청킹 데이터가 없습니다.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {chunks.map((chunk) => (
            <button
              key={chunk.id}
              type="button"
              onClick={() => setSelectedChunk(chunk)}
              className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-violet-300 hover:shadow-xl text-left w-full cursor-pointer"
            >
              {/* 청크 인덱스 + 토큰 수 */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <div
                    className="flex h-6 w-6 items-center justify-center rounded-lg text-[11px] font-bold text-white"
                    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
                  >
                    {chunk.chunkIndex + 1}
                  </div>
                  <span className="text-[11.5px] font-medium text-zinc-400">청크 #{chunk.chunkIndex}</span>
                </div>
                <span className="flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-500">
                  <Hash className="h-3 w-3" />
                  {chunk.tokenCount} tokens
                </span>
              </div>

              {/* 내용 */}
              <p className="line-clamp-5 text-[13px] leading-[1.7] text-zinc-600">
                {chunk.content}
              </p>

              {/* hover 힌트 */}
              <div className="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white to-transparent group-hover:from-violet-50/30" />
              <span className="absolute bottom-2 right-3 text-[11px] font-medium text-violet-400 opacity-0 transition-opacity group-hover:opacity-100">
                메타데이터 보기 →
              </span>
            </button>
          ))}
        </div>
      )}

      {/* 메타데이터 모달 */}
      {selectedChunk && (
        <ChunkMetaModal
          chunk={selectedChunk}
          onClose={() => setSelectedChunk(null)}
        />
      )}
    </div>
  );
};

export default ChunkViewer;
