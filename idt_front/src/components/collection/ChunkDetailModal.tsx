import { useEffect } from 'react';
import type { ChunkDetail } from '@/types/collection';
import { CHUNK_TYPE_BADGE } from '@/types/collection';

interface ChunkDetailModalProps {
  chunk: ChunkDetail;
  onClose: () => void;
}

const ChunkDetailModal = ({ chunk, onClose }: ChunkDetailModalProps) => {
  const typeBadge = CHUNK_TYPE_BADGE[chunk.chunk_type];
  const metaKeys = Object.keys(chunk.metadata);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative mx-4 flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-zinc-100 px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-100 text-[13px] font-bold text-violet-600">
              #{chunk.chunk_index}
            </span>
            <span className={`rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${typeBadge.bg} ${typeBadge.color}`}>
              {typeBadge.label}
            </span>
            <span className="text-[12px] text-zinc-400">
              ID: {chunk.chunk_id}
            </span>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {/* Content Section */}
          <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-violet-500">
            Content
          </h4>
          <div className="w-full rounded-xl bg-zinc-50 px-5 py-4">
            <p className="whitespace-pre-wrap text-[14px] leading-[1.85] text-zinc-700">
              {chunk.content}
            </p>
          </div>

          {/* Metadata Section */}
          {metaKeys.length > 0 && (
            <div className="mt-5">
              <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-widest text-violet-500">
                Metadata
              </h4>
              <div className="w-full overflow-x-auto rounded-xl border border-zinc-100 bg-zinc-50">
                <table className="w-full">
                  <tbody className="divide-y divide-zinc-100">
                    {metaKeys.map((key) => (
                      <tr key={key}>
                        <td className="whitespace-nowrap px-4 py-2 text-[12.5px] font-medium text-zinc-500">
                          {key}
                        </td>
                        <td className="break-all px-4 py-2 font-mono text-[12.5px] text-zinc-600">
                          {typeof chunk.metadata[key] === 'object'
                            ? JSON.stringify(chunk.metadata[key])
                            : String(chunk.metadata[key])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChunkDetailModal;
