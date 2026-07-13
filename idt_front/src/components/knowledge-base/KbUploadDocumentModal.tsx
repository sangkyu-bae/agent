import { useRef, useState } from 'react';
import Modal from '@/components/common/Modal';
import { useUploadKbDocument } from '@/hooks/useKnowledgeBases';
import type { KbUploadResponse } from '@/types/knowledgeBase';

interface KbUploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  kbId: string;
  kbName: string;
}

type ModalStatus = 'idle' | 'loading' | 'done' | 'error';

const StoreResultRow = ({
  label,
  status,
  error,
}: {
  label: string;
  status: string;
  error?: string | null;
}) => (
  <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 text-[13px]">
    <span className="font-medium text-zinc-600">{label}</span>
    {status === 'success' ? (
      <span className="font-semibold text-emerald-600">저장 완료</span>
    ) : (
      <span className="font-semibold text-red-500" title={error ?? undefined}>
        실패
      </span>
    )}
  </div>
);

const KbUploadDocumentModal = ({
  isOpen,
  onClose,
  kbId,
  kbName,
}: KbUploadDocumentModalProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<ModalStatus>('idle');
  const [result, setResult] = useState<KbUploadResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useUploadKbDocument(kbId);

  if (!isOpen) return null;

  const handleUpload = () => {
    if (!file) return;
    setStatus('loading');
    uploadMutation.mutate(file, {
      onSuccess: (data) => {
        setResult(data);
        setStatus('done');
      },
      onError: (err) => {
        setErrorMsg(
          err.message || '업로드에 실패했습니다. 잠시 후 다시 시도해주세요.',
        );
        setStatus('error');
      },
    });
  };

  const handleClose = () => {
    if (status === 'loading') return;
    setFile(null);
    setStatus('idle');
    setResult(null);
    setErrorMsg('');
    onClose();
  };

  return (
    <Modal
      onClose={handleClose}
      title="문서 업로드"
      subtitle={kbName}
      size="md"
      disableClose={status === 'loading'}
      showCloseButton={false}
    >
      {status === 'idle' || status === 'error' ? (
        <div className="space-y-4">
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            aria-label="업로드할 문서 파일"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-700 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-50 file:px-3 file:py-1.5 file:text-[13px] file:font-medium file:text-violet-600"
          />
          <p className="text-[12px] text-zinc-400">
            문서 파싱과 임베딩이 함께 진행되어 크기에 따라 수십 초가 걸릴 수
            있습니다.
          </p>

          {status === 'error' && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {errorMsg}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              닫기
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={!file}
              className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              업로드
            </button>
          </div>
        </div>
      ) : status === 'loading' ? (
        <div className="flex flex-col items-center gap-3 py-10">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-violet-200 border-t-violet-600" />
          <p className="text-[14px] text-zinc-600">
            업로드 중... 창을 닫지 마세요
          </p>
        </div>
      ) : (
        result && (
          <div className="space-y-3">
            <p className="text-[14px] text-zinc-700">
              <span className="font-semibold">{result.filename}</span>{' '}
              업로드가 완료되었습니다.
            </p>
            <div className="grid grid-cols-2 gap-2 text-[13px]">
              <div className="rounded-lg bg-zinc-50 px-3 py-2">
                <span className="text-zinc-400">청크 수</span>{' '}
                <span className="font-semibold text-zinc-800">
                  {result.chunk_count}
                </span>
              </div>
              <div className="rounded-lg bg-zinc-50 px-3 py-2">
                <span className="text-zinc-400">청킹 방식</span>{' '}
                <span className="font-semibold text-zinc-800">
                  {result.chunking_strategy === 'clause_aware'
                    ? '조항 단위'
                    : '기본'}
                </span>
              </div>
            </div>
            <StoreResultRow
              label="벡터 저장 (Qdrant)"
              status={result.qdrant.status}
              error={result.qdrant.error}
            />
            <StoreResultRow
              label="키워드 색인 (ES)"
              status={result.es.status}
              error={result.es.error}
            />
            {result.section_summary && (
              <p className="rounded-lg bg-violet-50 px-3 py-2 text-[13px] text-violet-600">
                섹션 요약을 백그라운드에서 생성하고 있습니다.
              </p>
            )}
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={handleClose}
                className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                확인
              </button>
            </div>
          </div>
        )
      )}
    </Modal>
  );
};

export default KbUploadDocumentModal;
