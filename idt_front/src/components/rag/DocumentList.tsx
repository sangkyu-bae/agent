import { FileText, Trash2, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { formatFileSize, formatDate } from '@/utils/formatters';
import type { Document, DocumentStatus } from '@/types/rag';

interface DocumentListProps {
  documents: Document[];
  selectedId: string | null;
  onSelect: (docId: string) => void;
  onDelete: (docId: string) => void;
  isDeleting?: boolean;
}

const STATUS_CONFIG: Record<DocumentStatus, { label: string; classes: string; icon: React.ReactNode }> = {
  ready:      { label: '준비',    classes: 'bg-emerald-50 text-emerald-600 border-emerald-200',   icon: <CheckCircle2 className="h-3 w-3" /> },
  processing: { label: '처리 중', classes: 'bg-amber-50 text-amber-600 border-amber-200',         icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  uploading:  { label: '업로드',  classes: 'bg-blue-50 text-blue-600 border-blue-200',            icon: <Loader2 className="h-3 w-3 animate-spin" /> },
  error:      { label: '오류',    classes: 'bg-red-50 text-red-500 border-red-200',               icon: <AlertCircle className="h-3 w-3" /> },
};

const DocumentList = ({ documents, selectedId, onSelect, onDelete, isDeleting }: DocumentListProps) => {
  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-400">
        <FileText className="mb-3 h-10 w-10 opacity-30" />
        <p className="text-[14px]">업로드된 문서가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-zinc-100 bg-zinc-50">
            {['파일명', '크기', '상태', '청크', '업로드일', ''].map((h) => (
              <th key={h} className="px-4 py-3 text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const status = STATUS_CONFIG[doc.status];
            const isSelected = doc.id === selectedId;
            const canSelect = doc.status === 'ready';

            return (
              <tr
                key={doc.id}
                onClick={() => canSelect && onSelect(doc.id)}
                className={[
                  'border-b border-zinc-100 transition-colors last:border-0',
                  canSelect ? 'cursor-pointer' : 'cursor-default',
                  isSelected
                    ? 'bg-violet-50'
                    : canSelect
                    ? 'hover:bg-zinc-50'
                    : 'opacity-60',
                ].join(' ')}
              >
                {/* 파일명 */}
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2.5">
                    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${isSelected ? 'border-violet-200 bg-violet-100' : 'border-zinc-200 bg-zinc-100'}`}>
                      <FileText className={`h-4 w-4 ${isSelected ? 'text-violet-500' : 'text-zinc-400'}`} />
                    </div>
                    <div>
                      <p className={`text-[13.5px] font-medium ${isSelected ? 'text-violet-700' : 'text-zinc-800'}`}>
                        {doc.name}
                      </p>
                      {doc.errorMessage && (
                        <p className="mt-0.5 text-[11px] text-red-400">{doc.errorMessage}</p>
                      )}
                    </div>
                  </div>
                </td>
                {/* 크기 */}
                <td className="px-4 py-3.5 text-[13px] text-zinc-500">{formatFileSize(doc.size)}</td>
                {/* 상태 */}
                <td className="px-4 py-3.5">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11.5px] font-medium ${status.classes}`}>
                    {status.icon}
                    {status.label}
                  </span>
                </td>
                {/* 청크 수 */}
                <td className="px-4 py-3.5 text-[13px] text-zinc-500">
                  {doc.chunkCount != null ? `${doc.chunkCount}개` : '—'}
                </td>
                {/* 업로드일 */}
                <td className="px-4 py-3.5 text-[12px] text-zinc-400">{formatDate(doc.uploadedAt)}</td>
                {/* 삭제 */}
                <td className="px-4 py-3.5">
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(doc.id); }}
                    disabled={isDeleting}
                    className="rounded-lg p-1.5 text-zinc-300 transition-colors hover:bg-red-50 hover:text-red-500"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default DocumentList;
