import { useState } from 'react';
import { DISTANCE_METRICS, COLLECTION_SCOPES, SCOPE_LABELS } from '@/types/collection';
import type { DistanceMetric, CollectionScope, CreateCollectionRequest } from '@/types/collection';
import { useEmbeddingModelList } from '@/hooks/useEmbeddingModels';

interface CreateCollectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateCollectionRequest) => void;
  isPending: boolean;
  error: string | null;
}

const NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

const CreateCollectionModal = ({
  isOpen,
  onClose,
  onSubmit,
  isPending,
  error,
}: CreateCollectionModalProps) => {
  const [name, setName] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [vectorSize, setVectorSize] = useState(1536);
  const [distance, setDistance] = useState<DistanceMetric>('Cosine');
  const [scope, setScope] = useState<CollectionScope>('PERSONAL');
  const [departmentId, setDepartmentId] = useState('');
  const [nameError, setNameError] = useState('');

  const {
    data: modelData,
    isLoading: isModelsLoading,
    isError: isModelsError,
  } = useEmbeddingModelList();

  const useFallback = isModelsError;
  const selectedModelInfo = modelData?.models.find(
    (m) => m.model_name === selectedModel,
  );

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError('컬렉션 이름을 입력해주세요');
      return;
    }
    if (!NAME_PATTERN.test(name)) {
      setNameError('영숫자, _, - 만 사용할 수 있습니다');
      return;
    }
    setNameError('');

    const base: CreateCollectionRequest = useFallback
      ? { name, vector_size: vectorSize, distance }
      : { name, embedding_model: selectedModel, distance };
    onSubmit({
      ...base,
      scope,
      department_id: scope === 'DEPARTMENT' ? departmentId : undefined,
    });
  };

  const handleClose = () => {
    setName('');
    setSelectedModel('');
    setVectorSize(1536);
    setDistance('Cosine');
    setScope('PERSONAL');
    setDepartmentId('');
    setNameError('');
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-[15px] font-semibold text-zinc-900">
          새 컬렉션 생성
        </h2>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
              컬렉션 이름
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameError('');
              }}
              placeholder="my-collection"
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
            />
            {nameError && (
              <p className="mt-1 text-[12px] text-red-500">{nameError}</p>
            )}
          </div>

          {isModelsLoading ? (
            <div>
              <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                임베딩 모델
              </label>
              <p className="text-[13px] text-zinc-400">
                모델 목록을 불러오는 중...
              </p>
            </div>
          ) : useFallback ? (
            <div>
              <p className="mb-2 flex items-center gap-1 text-[12px] text-amber-600">
                <span>⚠</span> 모델 목록을 불러올 수 없습니다
              </p>
              <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                벡터 차원 수
              </label>
              <input
                type="number"
                value={vectorSize}
                onChange={(e) => setVectorSize(Number(e.target.value))}
                min={1}
                className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 outline-none transition-all focus:border-violet-400"
              />
            </div>
          ) : (
            <div>
              <label htmlFor="embedding-model-select" className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                임베딩 모델
              </label>
              <select
                id="embedding-model-select"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 outline-none transition-all focus:border-violet-400"
              >
                <option value="">모델을 선택하세요</option>
                {modelData?.models.map((m) => (
                  <option key={m.id} value={m.model_name}>
                    {m.display_name}
                  </option>
                ))}
              </select>
              {selectedModelInfo && (
                <p className="mt-1.5 text-[12px] text-violet-500">
                  {selectedModelInfo.vector_dimension}차원
                </p>
              )}
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
              거리 메트릭
            </label>
            <select
              value={distance}
              onChange={(e) => setDistance(e.target.value as DistanceMetric)}
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 outline-none transition-all focus:border-violet-400"
            >
              {DISTANCE_METRICS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
              접근 범위
            </label>
            <div className="space-y-2">
              {COLLECTION_SCOPES.map((s) => (
                <label key={s} className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="radio"
                    name="scope"
                    value={s}
                    checked={scope === s}
                    onChange={() => setScope(s)}
                    className="h-4 w-4 accent-violet-600"
                  />
                  <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${SCOPE_LABELS[s].bg} ${SCOPE_LABELS[s].color}`}>
                    {SCOPE_LABELS[s].label}
                  </span>
                  <span className="text-[12px] text-zinc-400">
                    {s === 'PERSONAL' && '나만 접근 가능'}
                    {s === 'DEPARTMENT' && '소속 부서원 접근'}
                    {s === 'PUBLIC' && '전체 접근 가능'}
                  </span>
                </label>
              ))}
            </div>
            {scope === 'DEPARTMENT' && (
              <div className="mt-3">
                <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                  부서 ID
                </label>
                <input
                  type="text"
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  placeholder="dept-uuid"
                  className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
                />
              </div>
            )}
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              {isPending ? (
                <svg
                  className="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                '생성'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateCollectionModal;
