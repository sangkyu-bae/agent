// eval-hub: 데이터셋 생성 모달 — 직접 입력 | 파일 업로드 | 문서에서 생성 (Design §3.5)
// 문서 생성은 draft를 편집기에 프리필하고, 사용자가 검토·저장해야만 저장된다.
import { useRef, useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import {
  useCreateTestset,
  useGenerateDraft,
  useUploadTestset,
} from '@/hooks/useEval';
import type { TestCaseItem } from '@/types/eval';
import ManualCaseEditor from './ManualCaseEditor';

type CreateMode = 'manual' | 'file' | 'generate';

const MODES: { key: CreateMode; label: string }[] = [
  { key: 'manual', label: '직접 입력' },
  { key: 'file', label: '파일 업로드' },
  { key: 'generate', label: '문서에서 생성' },
];

interface CreateTestsetModalProps {
  onClose: () => void;
}

const CreateTestsetModal = ({ onClose }: CreateTestsetModalProps) => {
  const [mode, setMode] = useState<CreateMode>('manual');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [cases, setCases] = useState<TestCaseItem[]>([
    { question: '', ground_truth: null },
  ]);
  const [file, setFile] = useState<File | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createMutation = useCreateTestset();
  const uploadMutation = useUploadTestset();
  const generateMutation = useGenerateDraft();

  const validCases = cases.filter((c) => c.question.trim());

  const handleGenerate = () => {
    if (!file) {
      setError('문서 파일을 선택하세요.');
      return;
    }
    setError('');
    generateMutation.mutate(
      { file },
      {
        onSuccess: (draft) => {
          setCases(draft.items);
          setDraftLoaded(true);
          if (!name) setName(draft.source_filename.replace(/\.[^.]+$/, ''));
        },
        onError: (e) => setError(e.message),
      },
    );
  };

  const handleSubmit = () => {
    if (!name.trim()) {
      setError('데이터셋 이름을 입력하세요.');
      return;
    }
    setError('');

    if (mode === 'file') {
      if (!file) {
        setError('CSV 또는 Excel 파일을 선택하세요.');
        return;
      }
      uploadMutation.mutate(
        { file, name: name.trim(), description },
        { onSuccess: onClose, onError: (e) => setError(e.message) },
      );
      return;
    }

    // manual + generate(검토 후 저장) 공통 경로
    if (validCases.length === 0) {
      setError('질문이 있는 QA 쌍이 1개 이상 필요합니다.');
      return;
    }
    createMutation.mutate(
      { name: name.trim(), description, cases: validCases },
      { onSuccess: onClose, onError: (e) => setError(e.message) },
    );
  };

  const isSaving = createMutation.isPending || uploadMutation.isPending;
  const accept = mode === 'file' ? '.csv,.xlsx' : '.pdf,.docx';

  return (
    <div
      role="dialog"
      aria-label="데이터셋 생성"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-100 px-6 py-4">
          <h2 className="text-[15px] font-semibold text-zinc-900">데이터셋 생성</h2>
          <button
            onClick={onClose}
            aria-label="닫기"
            className="text-zinc-400 hover:text-zinc-600"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="mb-4 inline-flex rounded-xl bg-zinc-100 p-1">
            {MODES.map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => {
                  setMode(m.key);
                  setError('');
                  setFile(null);
                  setDraftLoaded(false);
                }}
                className={`rounded-lg px-3.5 py-1.5 text-[12.5px] font-medium ${
                  mode === m.key
                    ? 'bg-white text-zinc-900 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-800'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="데이터셋 이름"
            aria-label="데이터셋 이름"
            className="mb-2 w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px] focus:border-violet-400 focus:outline-none"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="설명 (선택)"
            aria-label="설명"
            className="mb-4 w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px] focus:border-violet-400 focus:outline-none"
          />

          {(mode === 'file' || (mode === 'generate' && !draftLoaded)) && (
            <div className="mb-4">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-full rounded-xl border-2 border-dashed border-zinc-200 px-4 py-8 text-[13px] text-zinc-500 hover:border-violet-300 hover:bg-violet-50/30"
              >
                {file
                  ? file.name
                  : mode === 'file'
                    ? 'CSV / Excel 파일 선택 (question, ground_truth 컬럼)'
                    : 'PDF / DOCX 문서 선택 — AI가 QA 쌍 초안을 생성합니다'}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept={accept}
                className="hidden"
                aria-label="파일 선택"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {mode === 'generate' && (
                <LoadingButton
                  isPending={generateMutation.isPending}
                  pendingText="QA 초안 생성 중..."
                  onClick={handleGenerate}
                  className="mt-3 w-full rounded-xl bg-violet-600 py-2.5 text-[13px] font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                >
                  초안 생성
                </LoadingButton>
              )}
            </div>
          )}

          {mode === 'generate' && draftLoaded && (
            <p className="mb-3 rounded-lg bg-violet-50 px-3 py-2 text-[12px] text-violet-700">
              생성된 초안 {cases.length}건 — 검토·수정 후 저장하세요. 저장 전까지 서버에 남지 않습니다.
            </p>
          )}

          {(mode === 'manual' || (mode === 'generate' && draftLoaded)) && (
            <ManualCaseEditor cases={cases} onChange={setCases} />
          )}

          {error && (
            <p role="alert" className="mt-3 text-[12.5px] text-red-500">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-zinc-100 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-xl border border-zinc-200 px-4 py-2 text-[13px] text-zinc-600 hover:bg-zinc-50"
          >
            취소
          </button>
          {(mode !== 'generate' || draftLoaded) && (
            <LoadingButton
              isPending={isSaving}
              pendingText="저장 중..."
              onClick={handleSubmit}
              className="rounded-xl bg-zinc-900 px-4 py-2 text-[13px] font-medium text-white hover:bg-zinc-800 disabled:opacity-60"
            >
              데이터셋 저장
            </LoadingButton>
          )}
        </div>
      </div>
    </div>
  );
};

export default CreateTestsetModal;
