import { useState } from 'react';
import Modal from '@/components/common/Modal';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useLlmModels } from '@/hooks/useLlmModels';
import {
  useChunkingProfiles,
  useCreateChunkingProfile,
  useUpdateChunkingProfile,
  useSetDefaultChunkingProfile,
  useDeleteChunkingProfile,
} from '@/hooks/useChunkingProfiles';
import { formatDate } from '@/utils/formatters';
import { isValidRegex } from '@/components/knowledge-base/customChunkingForm';
import BoundaryRulesEditor from './BoundaryRulesEditor';
import type {
  BoundaryRule,
  ChunkingProfile,
  ChunkingProfileRequest,
} from '@/types/chunkingProfile';
import type { LlmModel } from '@/types/llmModel';

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

/** authClient가 detail을 ApiError(message, status)로 정규화한다 */
const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

// ── 등록/수정 폼 모달 ─────────────────────────────────────

interface FormState {
  name: string;
  description: string;
  parent_chunk_size: string;
  chunk_size: string;
  chunk_overlap: string;
  rules: BoundaryRule[];
  is_default: boolean;
  summary_llm_model_id: string; // '' = 요약 비활성
}

const emptyForm: FormState = {
  name: '',
  description: '',
  parent_chunk_size: '2000',
  chunk_size: '500',
  chunk_overlap: '50',
  rules: [],
  is_default: false,
  summary_llm_model_id: '',
};

// PUT 전체 교체(D2) — 목록 응답의 전체 필드로 프리필한다
const fromProfile = (p: ChunkingProfile): FormState => ({
  name: p.name,
  description: p.description ?? '',
  parent_chunk_size: String(p.parent_chunk_size),
  chunk_size: String(p.chunk_size),
  chunk_overlap: String(p.chunk_overlap),
  rules: p.boundary_rules.map((r) => ({ ...r })),
  is_default: p.is_default,
  summary_llm_model_id: p.summary_llm_model_id ?? '',
});

interface FormModalProps {
  isOpen: boolean;
  profile: ChunkingProfile | null; // null = 등록
  models: LlmModel[];
  onClose: () => void;
  onSubmit: (req: ChunkingProfileRequest) => void;
  isPending: boolean;
  error: string | null;
  setError: (msg: string | null) => void;
}

const ProfileFormModal = ({
  isOpen,
  profile,
  models,
  onClose,
  onSubmit,
  isPending,
  error,
  setError,
}: FormModalProps) => {
  const isEdit = !!profile;
  const [form, setForm] = useState<FormState>(emptyForm);
  const [initialized, setInitialized] = useState(false);

  // 모달이 열릴 때 1회 초기화
  if (isOpen && !initialized) {
    setForm(profile ? fromProfile(profile) : emptyForm);
    setInitialized(true);
  }
  if (!isOpen && initialized) setInitialized(false);
  if (!isOpen) return null;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  // 활성 모델 + (수정 중 비활성 모델을 참조하면 해당 옵션 유지 — D3)
  const activeModels = models.filter((m) => m.is_active);
  const current = form.summary_llm_model_id;
  const inactiveCurrent =
    current && !activeModels.some((m) => m.id === current)
      ? models.find((m) => m.id === current) ?? null
      : null;
  const unknownCurrent =
    current &&
    !activeModels.some((m) => m.id === current) &&
    !inactiveCurrent;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.name.trim()) {
      setError('이름은 필수입니다.');
      return;
    }
    if (form.rules.length === 0) {
      setError('경계 규칙을 1개 이상 추가하세요.');
      return;
    }
    if (form.rules.some((r) => !r.pattern.trim() || !isValidRegex(r.pattern))) {
      setError('유효하지 않은 정규식 패턴이 있습니다.');
      return;
    }
    const parent = Number(form.parent_chunk_size);
    const size = Number(form.chunk_size);
    const overlap = Number(form.chunk_overlap);
    if (
      !Number.isInteger(parent) ||
      parent <= 0 ||
      !Number.isInteger(size) ||
      size <= 0 ||
      !Number.isInteger(overlap) ||
      overlap < 0
    ) {
      setError('청크 크기는 양의 정수, 오버랩은 0 이상의 정수여야 합니다.');
      return;
    }

    onSubmit({
      name: form.name.trim(),
      description: form.description.trim() || null,
      boundary_rules: form.rules,
      parent_chunk_size: parent,
      chunk_size: size,
      chunk_overlap: overlap,
      is_default: form.is_default,
      summary_llm_model_id: form.summary_llm_model_id || null,
    });
  };

  return (
    <Modal
      onClose={onClose}
      title={isEdit ? '청킹 프로파일 수정' : '청킹 프로파일 등록'}
      size="lg"
      scroll="content"
      showCloseButton={false}
    >
      {/* noValidate: 브라우저 기본 검증 대신 커스텀 인라인 에러로 통일 */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className={labelCls}>
              이름 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="예: 금융 약관 조항 프로파일"
              maxLength={100}
              className={inputCls}
            />
          </div>
          <div className="flex-1">
            <label className={labelCls}>설명</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="프로파일 설명 (선택)"
              maxLength={255}
              className={inputCls}
            />
          </div>
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className={labelCls}>Parent 크기</label>
            <input
              type="number"
              value={form.parent_chunk_size}
              onChange={(e) => set('parent_chunk_size', e.target.value)}
              min={1}
              aria-label="Parent 크기"
              className={inputCls}
            />
          </div>
          <div className="flex-1">
            <label className={labelCls}>Chunk 크기</label>
            <input
              type="number"
              value={form.chunk_size}
              onChange={(e) => set('chunk_size', e.target.value)}
              min={1}
              aria-label="Chunk 크기"
              className={inputCls}
            />
          </div>
          <div className="flex-1">
            <label className={labelCls}>Overlap</label>
            <input
              type="number"
              value={form.chunk_overlap}
              onChange={(e) => set('chunk_overlap', e.target.value)}
              min={0}
              aria-label="Overlap"
              className={inputCls}
            />
          </div>
        </div>

        <div>
          <label className={labelCls}>
            경계 규칙 <span className="text-red-400">*</span>
          </label>
          <BoundaryRulesEditor
            rules={form.rules}
            onChange={(rules) => set('rules', rules)}
          />
        </div>

        <div>
          <label className={labelCls}>요약 LLM</label>
          <select
            value={form.summary_llm_model_id}
            onChange={(e) => set('summary_llm_model_id', e.target.value)}
            aria-label="요약 LLM"
            className={inputCls}
          >
            <option value="">사용 안 함 (요약 비활성)</option>
            {activeModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name}
              </option>
            ))}
            {inactiveCurrent && (
              <option value={inactiveCurrent.id}>
                {inactiveCurrent.display_name} (비활성)
              </option>
            )}
            {unknownCurrent && (
              <option value={current}>{current} (등록 정보 없음)</option>
            )}
          </select>
          <p className="mt-1 text-[12px] text-zinc-400">
            조항 청킹 KB 업로드 시 섹션 요약·키워드 추출에 사용됩니다. 미지정 시
            요약이 실행되지 않습니다.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[13px] text-zinc-700">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => set('is_default', e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            기본 프로파일
          </label>
          <span className="text-[12px] text-zinc-400">
            지정 시 기존 기본 프로파일은 자동 해제됩니다.
          </span>
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
          >
            {isPending ? '저장 중...' : isEdit ? '저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

// ── 페이지 ─────────────────────────────────────────────────

const AdminChunkingProfilesPage = () => {
  const { data, isLoading, isError, refetch } = useChunkingProfiles();
  const profiles = data ?? [];
  // 비활성 포함 전체 모델 — 테이블 표시 매핑 + 폼 드롭다운 공용 (D3)
  const { data: models = [] } = useLlmModels(true);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editing, setEditing] = useState<ChunkingProfile | null>(null);
  const [deleting, setDeleting] = useState<ChunkingProfile | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const createMutation = useCreateChunkingProfile();
  const updateMutation = useUpdateChunkingProfile();
  const setDefaultMutation = useSetDefaultChunkingProfile();
  const deleteMutation = useDeleteChunkingProfile();

  const llmName = (id: string | null): string | null => {
    if (!id) return null;
    return models.find((m) => m.id === id)?.display_name ?? id;
  };

  const handleCreate = (req: ChunkingProfileRequest) => {
    createMutation.mutate(req, {
      onSuccess: () => setIsCreateOpen(false),
      onError: (err) =>
        setFormError(getErrorMessage(err, '프로파일 등록에 실패했습니다.')),
    });
  };

  const handleUpdate = (req: ChunkingProfileRequest) => {
    if (!editing) return;
    updateMutation.mutate(
      { id: editing.profile_id, data: req },
      {
        onSuccess: () => setEditing(null),
        onError: (err) =>
          setFormError(getErrorMessage(err, '프로파일 수정에 실패했습니다.')),
      },
    );
  };

  const handleSetDefault = (profile: ChunkingProfile) => {
    setActionError(null);
    setDefaultMutation.mutate(profile.profile_id, {
      onError: (err) =>
        setActionError(getErrorMessage(err, '기본 지정에 실패했습니다.')),
    });
  };

  const handleDelete = () => {
    if (!deleting) return;
    deleteMutation.mutate(deleting.profile_id, {
      onSuccess: () => setDeleting(null),
      onError: (err) =>
        setDeleteError(getErrorMessage(err, '삭제에 실패했습니다.')),
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            Admin
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">청킹 프로파일</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            조항 청킹 경계 규칙과 섹션 요약 LLM을 프로파일 단위로 관리합니다.
          </p>
        </div>
        <button
          onClick={() => {
            setFormError(null);
            setIsCreateOpen(true);
          }}
          className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          프로파일 등록
        </button>
      </div>

      {actionError && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
          {actionError}
        </p>
      )}

      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : isError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">청킹 프로파일 목록을 불러오지 못했습니다.</p>
          <button
            onClick={() => refetch()}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            다시 시도
          </button>
        </div>
      ) : profiles.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">등록된 청킹 프로파일이 없습니다.</p>
          <button
            onClick={() => {
              setFormError(null);
              setIsCreateOpen(true);
            }}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            + 첫 번째 프로파일 등록하기
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">이름</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">사이즈</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">경계 규칙</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">요약 LLM</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">수정일</th>
                <th className="w-[240px] px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {profiles.map((p) => (
                <tr key={p.profile_id} className="transition-colors hover:bg-zinc-50/50">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] font-medium text-zinc-900">{p.name}</span>
                      {p.is_default && (
                        <span className="rounded-md bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-600">
                          기본
                        </span>
                      )}
                    </div>
                    {p.description && (
                      <div className="text-[12px] text-zinc-400">{p.description}</div>
                    )}
                  </td>
                  <td className="px-5 py-4 font-mono text-[12.5px] text-zinc-500">
                    {`parent ${p.parent_chunk_size} · chunk ${p.chunk_size} · overlap ${p.chunk_overlap}`}
                  </td>
                  <td
                    className="px-5 py-4 text-[13px] text-zinc-600"
                    title={p.boundary_rules.map((r) => r.pattern).join('\n')}
                  >
                    {p.boundary_rules.length}개
                  </td>
                  <td className="px-5 py-4">
                    {p.summary_llm_model_id ? (
                      <span className="text-[13px] text-zinc-600">
                        {llmName(p.summary_llm_model_id)}
                      </span>
                    ) : (
                      <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11.5px] font-medium text-zinc-400">
                        요약 비활성
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-[13px] text-zinc-500">
                    {p.updated_at ? formatDate(p.updated_at) : '–'}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => {
                          setFormError(null);
                          setEditing(p);
                        }}
                        aria-label={`${p.name} 수정`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 active:scale-95"
                      >
                        수정
                      </button>
                      {!p.is_default && (
                        <button
                          onClick={() => handleSetDefault(p)}
                          aria-label={`${p.name} 기본 지정`}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-200 hover:text-violet-600 active:scale-95"
                        >
                          기본 지정
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setDeleteError(null);
                          setDeleting(p);
                        }}
                        aria-label={`${p.name} 삭제`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95"
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 등록 모달 */}
      <ProfileFormModal
        isOpen={isCreateOpen}
        profile={null}
        models={models}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreate}
        isPending={createMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 수정 모달 */}
      <ProfileFormModal
        isOpen={!!editing}
        profile={editing}
        models={models}
        onClose={() => setEditing(null)}
        onSubmit={handleUpdate}
        isPending={updateMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 삭제 확인 */}
      <ConfirmDialog
        isOpen={!!deleting}
        title="프로파일 삭제"
        description={
          <>
            <b>{deleting?.name}</b> 프로파일을 삭제합니다. 이 프로파일을 참조 중인
            지식베이스는 다음 업로드부터 기본 프로파일로 폴백됩니다.
          </>
        }
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
        error={deleteError}
      />
    </div>
  );
};

export default AdminChunkingProfilesPage;
