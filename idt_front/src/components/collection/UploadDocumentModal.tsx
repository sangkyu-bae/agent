import { useState, useRef, useEffect, useCallback } from 'react';
import { useUnifiedUpload } from '@/hooks/useUnifiedUpload';
import { formatFileSize } from '@/utils/formatters';
import type {
  UploadModalStatus,
  ChunkingOptions,
  UnifiedUploadResponse,
} from '@/types/unifiedUpload';
import { DEFAULT_CHUNKING_OPTIONS } from '@/types/unifiedUpload';

interface UploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  collectionName: string;
}

const UploadDocumentModal = ({ isOpen, onClose, collectionName }: UploadDocumentModalProps) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [options, setOptions] = useState<ChunkingOptions>(DEFAULT_CHUNKING_OPTIONS);
  const [uploadResult, setUploadResult] = useState<UnifiedUploadResponse | null>(null);
  const [modalStatus, setModalStatus] = useState<UploadModalStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const mutation = useUnifiedUpload(collectionName, {
    onSuccess: (data) => {
      setUploadResult(data);
      if (data.status === 'completed') setModalStatus('success');
      else if (data.status === 'partial') setModalStatus('partial');
      else {
        setModalStatus('error');
        setErrorMessage('벡터 및 검색 저장소 모두 실패했습니다.');
      }
    },
    onError: (error) => {
      setModalStatus('error');
      setErrorMessage(error.message);
    },
  });

  const resetState = useCallback(() => {
    setSelectedFile(null);
    setIsDragOver(false);
    setShowOptions(false);
    setOptions(DEFAULT_CHUNKING_OPTIONS);
    setUploadResult(null);
    setModalStatus('idle');
    setErrorMessage('');
  }, []);

  const handleClose = useCallback(() => {
    if (modalStatus === 'loading') return;
    resetState();
    onClose();
  }, [modalStatus, resetState, onClose]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && modalStatus !== 'loading') handleClose();
    };
    if (isOpen) window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, modalStatus, handleClose]);

  const isValidPdf = (file: File): boolean => file.name.toLowerCase().endsWith('.pdf');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && isValidPdf(file)) setSelectedFile(file);
    else if (file) alert('PDF 파일만 업로드할 수 있습니다.');
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && isValidPdf(file)) setSelectedFile(file);
    else if (file) alert('PDF 파일만 업로드할 수 있습니다.');
  };

  const handleUpload = () => {
    if (!selectedFile) return;
    setModalStatus('loading');
    setErrorMessage('');
    mutation.mutate({
      file: selectedFile,
      params: {
        user_id: 'default-user',
        collection_name: collectionName,
        child_chunk_size: options.childChunkSize,
        child_chunk_overlap: options.childChunkOverlap,
        top_keywords: options.topKeywords,
      },
    });
  };

  const handleRetry = () => {
    setModalStatus('idle');
    setUploadResult(null);
    setErrorMessage('');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-zinc-900">PDF 문서 업로드</h2>
            <p className="mt-0.5 text-[12px] text-zinc-400">
              컬렉션: <span className="font-medium text-violet-500">{collectionName}</span>
            </p>
          </div>
          <button
            onClick={handleClose}
            disabled={modalStatus === 'loading'}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {/* Idle — Drop zone + options */}
          {modalStatus === 'idle' && (
            <>
              {!selectedFile ? (
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                  onDragLeave={() => setIsDragOver(false)}
                  onClick={() => fileInputRef.current?.click()}
                  className={`group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-8 py-12 transition-all duration-200 ${
                    isDragOver
                      ? 'border-violet-400 bg-violet-50/60'
                      : 'border-zinc-200 bg-zinc-50/50 hover:border-violet-300 hover:bg-violet-50/30'
                  }`}
                >
                  <div
                    className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl shadow-md transition-all duration-200 ${
                      isDragOver ? 'scale-110' : 'group-hover:scale-105'
                    }`}
                    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
                  >
                    <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                    </svg>
                  </div>
                  {isDragOver ? (
                    <p className="text-[15px] font-semibold text-violet-600">여기에 놓아주세요</p>
                  ) : (
                    <>
                      <p className="text-[15px] font-semibold text-zinc-700">파일을 드래그하거나 클릭하여 업로드</p>
                      <p className="mt-1.5 text-[12.5px] text-zinc-400">PDF 파일만 지원</p>
                    </>
                  )}
                  <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
                </div>
              ) : (
                <div className="flex items-center justify-between rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50">
                      <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-[13.5px] font-medium text-zinc-800">{selectedFile.name}</p>
                      <p className="text-[12px] text-zinc-400">{formatFileSize(selectedFile.size)}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedFile(null)}
                    className="text-zinc-400 transition-colors hover:text-red-500"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              )}

              {/* Advanced Options */}
              <button
                onClick={() => setShowOptions(!showOptions)}
                className="mt-4 flex items-center gap-1.5 text-[13px] font-medium text-zinc-500 transition-colors hover:text-zinc-700"
              >
                <svg
                  className={`h-4 w-4 transition-transform ${showOptions ? 'rotate-90' : ''}`}
                  fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                </svg>
                고급 옵션
              </button>

              {showOptions && (
                <div className="mt-3 space-y-3 rounded-xl border border-zinc-200 bg-zinc-50/50 p-4">
                  <OptionField
                    label="청크 크기 (토큰)"
                    value={options.childChunkSize}
                    onChange={(v) => setOptions((prev) => ({ ...prev, childChunkSize: v }))}
                    min={100} max={4000} step={100}
                  />
                  <OptionField
                    label="청크 오버랩 (토큰)"
                    value={options.childChunkOverlap}
                    onChange={(v) => setOptions((prev) => ({ ...prev, childChunkOverlap: v }))}
                    min={0} max={500} step={10}
                  />
                  <OptionField
                    label="키워드 수"
                    value={options.topKeywords}
                    onChange={(v) => setOptions((prev) => ({ ...prev, topKeywords: v }))}
                    min={1} max={50} step={1}
                  />
                </div>
              )}
            </>
          )}

          {/* Loading */}
          {modalStatus === 'loading' && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="relative mb-5">
                <div
                  className="h-14 w-14 animate-spin rounded-full border-4 border-zinc-200"
                  style={{ borderTopColor: '#7c3aed' }}
                />
                <div
                  className="absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full"
                  style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)' }}
                />
              </div>
              <p className="text-[15px] font-semibold text-zinc-700">문서 처리 중...</p>
              <p className="mt-1 text-[12.5px] text-zinc-400">
                <span className="font-medium text-violet-500">{selectedFile?.name}</span>을(를)
                분석하고 벡터를 생성하고 있습니다
              </p>
            </div>
          )}

          {/* Success / Partial */}
          {(modalStatus === 'success' || modalStatus === 'partial') && uploadResult && (
            <div className="space-y-4 py-2">
              {/* Status Badge */}
              <div className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] font-semibold ${
                modalStatus === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-600'
                  : 'border-amber-200 bg-amber-50 text-amber-600'
              }`}>
                {modalStatus === 'success' ? (
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                  </svg>
                ) : (
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                  </svg>
                )}
                {modalStatus === 'success' ? '업로드 완료' : '부분 성공'}
              </div>

              {/* Document Summary */}
              <div className="rounded-xl border border-zinc-200 bg-white p-4">
                <div className="grid grid-cols-2 gap-3 text-[13px]">
                  <div><span className="text-zinc-400">파일명</span><p className="mt-0.5 font-medium text-zinc-800">{uploadResult.filename}</p></div>
                  <div><span className="text-zinc-400">페이지 수</span><p className="mt-0.5 font-medium text-zinc-800">{uploadResult.total_pages}</p></div>
                  <div><span className="text-zinc-400">청크 수</span><p className="mt-0.5 font-medium text-zinc-800">{uploadResult.chunk_count}</p></div>
                  <div><span className="text-zinc-400">임베딩 모델</span><p className="mt-0.5 font-medium text-zinc-800">{uploadResult.qdrant.embedding_model}</p></div>
                </div>
              </div>

              {/* Qdrant Result */}
              <StorageResultCard
                title="Qdrant (벡터)"
                status={uploadResult.qdrant.status}
                detail={`${uploadResult.qdrant.stored_ids.length}개 벡터 저장`}
                error={uploadResult.qdrant.error}
              />

              {/* ES Result */}
              <StorageResultCard
                title="Elasticsearch (BM25)"
                status={uploadResult.es.status}
                detail={`${uploadResult.es.indexed_count}개 인덱싱`}
                error={uploadResult.es.error}
              />
            </div>
          )}

          {/* Error */}
          {modalStatus === 'error' && (
            <div className="flex flex-col items-center py-12">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 shadow-md">
                <svg className="h-7 w-7 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                </svg>
              </div>
              <p className="text-[15px] font-semibold text-zinc-700">업로드 ��패</p>
              <p className="mt-1 max-w-sm text-center text-[12.5px] text-zinc-400">{errorMessage}</p>
              <button
                onClick={handleRetry}
                className="mt-4 flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                재시도
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-200 px-6 py-4">
          {modalStatus === 'idle' && (
            <button
              disabled={!selectedFile}
              onClick={handleUpload}
              className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-[14px] font-medium shadow-sm transition-all active:scale-95 ${
                selectedFile
                  ? 'bg-violet-600 text-white hover:bg-violet-700'
                  : 'cursor-not-allowed bg-zinc-100 text-zinc-400'
              }`}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
              </svg>
              업로드 시작
            </button>
          )}
          {(modalStatus === 'success' || modalStatus === 'partial' || modalStatus === 'error') && (
            <button
              onClick={handleClose}
              className="flex w-full items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-[14px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

/* ── Internal sub-components ───────────────────────── */

interface OptionFieldProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}

const OptionField = ({ label, value, onChange, min, max, step }: OptionFieldProps) => (
  <div className="flex items-center justify-between">
    <label className="text-[13px] text-zinc-600">{label}</label>
    <input
      type="number"
      value={value}
      onChange={(e) => {
        const v = Number(e.target.value);
        if (v >= min && v <= max) onChange(v);
      }}
      min={min}
      max={max}
      step={step}
      className="w-24 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-right text-[13px] text-zinc-800 outline-none transition-colors focus:border-violet-400"
    />
  </div>
);

interface StorageResultCardProps {
  title: string;
  status: 'success' | 'failed';
  detail: string;
  error: string | null;
}

const StorageResultCard = ({ title, status, detail, error }: StorageResultCardProps) => (
  <div>
    <div
      className={`flex items-center justify-between rounded-xl border p-3 ${
        status === 'success'
          ? 'border-emerald-200 bg-emerald-50/50'
          : 'border-red-200 bg-red-50/50'
      }`}
    >
      <div className="flex items-center gap-2">
        {status === 'success' ? (
          <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        ) : (
          <svg className="h-4 w-4 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        )}
        <span className="text-[13px] font-medium text-zinc-700">{title}</span>
      </div>
      <span className="text-[12px] text-zinc-500">{detail}</span>
    </div>
    {error && <p className="mt-1 px-3 text-[12px] text-red-500">{error}</p>}
  </div>
);

export default UploadDocumentModal;
