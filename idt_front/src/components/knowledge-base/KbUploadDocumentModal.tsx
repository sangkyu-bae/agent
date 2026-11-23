// Design Ref: document-revision §5.1·§5.2 — 파일 선택 → 개정 사전 점검 → 운영자 결정 → 업로드.
import { useRef, useState } from 'react';
import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import { useCheckKbRevision } from '@/hooks/useDocumentRevision';
import { useUploadKbDocument } from '@/hooks/useKnowledgeBases';
import { ApiError } from '@/services/api/ApiError';
import {
  REVISION_ERROR_CODE,
  type KbUploadResponse,
  type RevisionApplyResult,
  type RevisionCheckResponse,
} from '@/types/knowledgeBase';
import RevisionCheckResult from './RevisionCheckResult';
import {
  canUpload,
  initialDecision,
  toUploadOptions,
  type RevisionDecision,
} from './revisionDecision';

interface KbUploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  kbId: string;
  kbName: string;
}

type ModalStatus = 'idle' | 'loading' | 'done' | 'error';
type CheckState = 'none' | 'checking' | 'ready' | 'failed';

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

/** 업로드 응답의 개정 결과 안내 (Design §5.4) */
const RevisionOutcome = ({ revision }: { revision: RevisionApplyResult }) => {
  if (revision.applied) {
    return (
      <div className="space-y-1 rounded-xl border border-success-border bg-success-bg px-3 py-2 text-sm text-success">
        <p>
          v{revision.version_no} 버전으로 개정되었습니다. 이전 버전은 검색에서 제외됩니다.
        </p>
        {revision.sync_state === 'pending' && (
          <p className="text-warning">
            이전 버전을 검색에서 빼는 작업이 끝나지 않았습니다. 문서 목록에서 다시
            시도하세요.
          </p>
        )}
      </div>
    );
  }
  if (revision.reason === 'ingest_incomplete') {
    return (
      <p className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning">
        저장이 일부 실패해 개정을 적용하지 않고 새 문서로 올렸습니다. 이전 버전은
        그대로 검색됩니다.
      </p>
    );
  }
  return null;
};

const uploadErrorMessage = (err: Error): { message: string; recheck: boolean } => {
  if (err instanceof ApiError) {
    if (err.code === REVISION_ERROR_CODE.DUPLICATE_DOCUMENT) {
      return { message: '이미 같은 파일이 있습니다. 다른 파일을 선택하세요.', recheck: false };
    }
    if (err.code === REVISION_ERROR_CODE.REVISION_TARGET_INVALID) {
      return {
        message: '대상 문서의 상태가 바뀌었습니다. 다시 점검한 뒤 올려 주세요.',
        recheck: true,
      };
    }
  }
  return {
    message: err.message || '업로드에 실패했습니다. 잠시 후 다시 시도해주세요.',
    recheck: false,
  };
};

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
  const [canRecheck, setCanRecheck] = useState(false);
  const [checkState, setCheckState] = useState<CheckState>('none');
  const [check, setCheck] = useState<RevisionCheckResponse | null>(null);
  const [decision, setDecision] = useState<RevisionDecision>(initialDecision(null));
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useUploadKbDocument(kbId);
  const checkMutation = useCheckKbRevision(kbId);

  if (!isOpen) return null;

  const runCheck = (target: File) => {
    setCheckState('checking');
    setCheck(null);
    setDecision(initialDecision(null));
    checkMutation.mutate(target, {
      onSuccess: (data) => {
        setCheck(data);
        setDecision(initialDecision(data));
        setCheckState('ready');
      },
      // 점검이 실패해도 새 문서 업로드는 막지 않는다 (Plan SC-7)
      onError: () => setCheckState('failed'),
    });
  };

  const handleFileChange = (next: File | null) => {
    setFile(next);
    setStatus('idle');
    setErrorMsg('');
    setCanRecheck(false);
    if (next) runCheck(next);
    else setCheckState('none');
  };

  const handleUpload = () => {
    if (!file) return;
    setStatus('loading');
    uploadMutation.mutate(
      { file, revision: toUploadOptions(decision, check?.check_id ?? null) },
      {
        onSuccess: (data) => {
          setResult(data);
          setStatus('done');
        },
        onError: (err) => {
          const { message, recheck } = uploadErrorMessage(err);
          setErrorMsg(message);
          setCanRecheck(recheck);
          setStatus('error');
        },
      },
    );
  };

  const handleRecheck = () => {
    if (!file) return;
    setStatus('idle');
    setErrorMsg('');
    setCanRecheck(false);
    runCheck(file);
  };

  const handleClose = () => {
    if (status === 'loading') return;
    setFile(null);
    setStatus('idle');
    setResult(null);
    setErrorMsg('');
    setCanRecheck(false);
    setCheckState('none');
    setCheck(null);
    onClose();
  };

  const uploadDisabled =
    !file ||
    checkState === 'checking' ||
    (checkState === 'ready' && !canUpload(check, decision));

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
            accept=".pdf,.xlsx,.xls,.hwp,.hwpx"
            aria-label="업로드할 문서 파일"
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
            className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-700 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-50 file:px-3 file:py-1.5 file:text-[13px] file:font-medium file:text-violet-600"
          />
          <p className="text-[12px] text-zinc-400">
            지원 형식: PDF, 엑셀(.xlsx/.xls), 한글(.hwp/.hwpx) — 엑셀은
            시트 단위로 저장됩니다. 문서 파싱과 임베딩이 함께 진행되어 크기에 따라 수십
            초가 걸릴 수 있습니다.
          </p>

          {checkState === 'checking' && (
            <p
              role="status"
              className="flex items-center gap-2 rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-fg-secondary"
            >
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600"
              />
              기존 문서의 개정본인지 확인하는 중...
            </p>
          )}
          {checkState === 'failed' && (
            <p className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2.5 text-sm text-warning">
              개정 여부를 확인하지 못했습니다. 새 문서로 올릴 수 있습니다.
            </p>
          )}
          {checkState === 'ready' && check && (
            <RevisionCheckResult result={check} decision={decision} onChange={setDecision} />
          )}

          {status === 'error' && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {errorMsg}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            {canRecheck && (
              <Button variant="secondary" onClick={handleRecheck}>
                다시 점검
              </Button>
            )}
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
              disabled={uploadDisabled}
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
            {result.revision && <RevisionOutcome revision={result.revision} />}
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
