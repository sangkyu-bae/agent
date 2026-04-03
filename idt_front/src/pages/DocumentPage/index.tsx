import { useState, useRef } from 'react';
import { Upload, FolderOpen, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';
import { useDocuments, useDocumentChunks, useUploadDocument, useDeleteDocument } from '@/hooks/useDocuments';
import DocumentList from '@/components/rag/DocumentList';
import ChunkViewer from '@/components/rag/ChunkViewer';
import VectorSearchPanel from '@/components/rag/VectorSearchPanel';

const DocumentPage = () => {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: docData, isLoading: isLoadingDocs } = useDocuments();
  const { data: chunks = [], isLoading: isLoadingChunks } = useDocumentChunks(selectedDocId);
  const { mutate: uploadDoc, isPending: isUploading } = useUploadDocument();
  const { mutate: deleteDoc, isPending: isDeleting } = useDeleteDocument();

  const documents = docData?.items ?? [];
  const selectedDoc = documents.find((d) => d.id === selectedDocId) ?? null;

  // 통계
  const stats = {
    total: docData?.total ?? 0,
    ready: documents.filter((d) => d.status === 'ready').length,
    processing: documents.filter((d) => d.status === 'processing').length,
    error: documents.filter((d) => d.status === 'error').length,
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadDoc({ file });
    e.target.value = '';
  };

  const handleDelete = (docId: string) => {
    if (docId === selectedDocId) setSelectedDocId(null);
    deleteDoc(docId);
  };

  return (
    <div className="bg-zinc-50" style={{ height: '100%', overflowY: 'auto' }}>
      <div className="mx-auto max-w-6xl px-6 py-8">

        {/* 헤더 */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <FolderOpen className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">RAG</p>
              <h1 className="text-3xl font-bold tracking-tight text-zinc-900">문서 관리</h1>
            </div>
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-60"
          >
            {isUploading
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <Upload className="h-4 w-4" />}
            문서 업로드
          </button>
          <input ref={fileInputRef} type="file" accept=".pdf,.txt,.docx,.md" className="hidden" onChange={handleFileChange} />
        </div>

        {/* 통계 카드 */}
        <div className="mb-6 grid grid-cols-4 gap-4">
          {[
            { label: '전체 문서', value: stats.total, color: 'text-zinc-700', bg: 'bg-white' },
            { label: '준비 완료', value: stats.ready, color: 'text-emerald-600', bg: 'bg-emerald-50', icon: <CheckCircle2 className="h-4 w-4 text-emerald-400" /> },
            { label: '처리 중',   value: stats.processing, color: 'text-amber-600', bg: 'bg-amber-50', icon: <Loader2 className="h-4 w-4 animate-spin text-amber-400" /> },
            { label: '오류',      value: stats.error, color: 'text-red-500', bg: 'bg-red-50', icon: <AlertCircle className="h-4 w-4 text-red-400" /> },
          ].map(({ label, value, color, bg, icon }) => (
            <div key={label} className={`flex items-center gap-3 rounded-2xl border border-zinc-200 ${bg} px-4 py-3 shadow-sm`}>
              {icon && <div>{icon}</div>}
              <div>
                <p className="text-[11.5px] font-medium text-zinc-400">{label}</p>
                <p className={`text-[22px] font-bold ${color}`}>{value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* 문서 리스트 */}
        {isLoadingDocs ? (
          <div className="flex items-center justify-center py-16 text-zinc-400">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            <span className="text-[14px]">문서 목록을 불러오는 중...</span>
          </div>
        ) : (
          <DocumentList
            documents={documents}
            selectedId={selectedDocId}
            onSelect={setSelectedDocId}
            onDelete={handleDelete}
            isDeleting={isDeleting}
          />
        )}

        {/* 청크 뷰어 (문서 선택 시) */}
        {selectedDoc && (
          <ChunkViewer
            document={selectedDoc}
            chunks={chunks}
            isLoading={isLoadingChunks}
          />
        )}

        {/* 벡터 검색 테스트 */}
        <VectorSearchPanel />
      </div>
    </div>
  );
};

export default DocumentPage;
