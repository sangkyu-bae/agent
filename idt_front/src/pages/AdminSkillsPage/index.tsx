import { useState } from 'react';
import Dropdown from '@/components/common/Dropdown';
import {
  useSkills,
  useSkill,
  useCreateSkill,
  useUpdateSkill,
  useDeleteSkill,
  useForkSkill,
} from '@/hooks/useSkills';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import Modal from '@/components/common/Modal';
import type {
  Skill,
  SkillSummary,
  SkillScriptType,
  SkillVisibility,
  CreateSkillRequest,
  UpdateSkillRequest,
} from '@/types/skill';

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

const SCRIPT_TYPES: SkillScriptType[] = ['none', 'python', 'shell'];
const VISIBILITIES: SkillVisibility[] = ['private', 'department', 'public'];
const VISIBILITY_LABEL: Record<SkillVisibility, string> = {
  private: '비공개',
  department: '부서',
  public: '전체공개',
};

interface FormState {
  name: string;
  description: string;
  trigger: string;
  instruction: string;
  script_type: SkillScriptType;
  script_content: string;
  visibility: SkillVisibility;
  department_id: string;
}

const emptyForm: FormState = {
  name: '',
  description: '',
  trigger: '',
  instruction: '',
  script_type: 'none',
  script_content: '',
  visibility: 'private',
  department_id: '',
};

const fromSkill = (s: Skill): FormState => ({
  name: s.name,
  description: s.description,
  trigger: s.trigger ?? '',
  instruction: s.instruction,
  script_type: s.script_type,
  script_content: s.script_content ?? '',
  visibility: s.visibility,
  department_id: s.department_id ?? '',
});

interface FormModalProps {
  isOpen: boolean;
  skill: Skill | null; // null = 생성
  onClose: () => void;
  onSubmitCreate: (req: CreateSkillRequest) => void;
  onSubmitUpdate: (data: UpdateSkillRequest) => void;
  isPending: boolean;
  error: string | null;
  setError: (msg: string | null) => void;
}

const SkillFormModal = ({
  isOpen,
  skill,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
  isPending,
  error,
  setError,
}: FormModalProps) => {
  const isEdit = !!skill;
  const [form, setForm] = useState<FormState>(emptyForm);
  const [initialized, setInitialized] = useState(false);

  if (isOpen && !initialized) {
    setForm(skill ? fromSkill(skill) : emptyForm);
    setInitialized(true);
  }
  if (!isOpen && initialized) setInitialized(false);
  if (!isOpen) return null;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!form.name.trim() || !form.instruction.trim()) {
      setError('이름·지시문은 필수입니다.');
      return;
    }
    if (form.visibility === 'department' && !form.department_id.trim()) {
      setError('부서 공개는 부서 ID가 필요합니다.');
      return;
    }
    if (form.script_type === 'none' && form.script_content.trim()) {
      setError("스크립트 타입이 'none'이면 스크립트를 비워야 합니다.");
      return;
    }

    const scriptContent =
      form.script_type === 'none' ? null : form.script_content.trim() || null;
    const departmentId =
      form.visibility === 'department' ? form.department_id.trim() : null;

    if (isEdit) {
      onSubmitUpdate({
        name: form.name.trim(),
        description: form.description.trim(),
        trigger: form.trigger.trim() || null,
        instruction: form.instruction.trim(),
        script_type: form.script_type,
        script_content: scriptContent,
        visibility: form.visibility,
        department_id: departmentId,
      });
    } else {
      onSubmitCreate({
        name: form.name.trim(),
        description: form.description.trim(),
        trigger: form.trigger.trim() || null,
        instruction: form.instruction.trim(),
        script_type: form.script_type,
        script_content: scriptContent,
        visibility: form.visibility,
        department_id: departmentId,
      });
    }
  };

  const isNone = form.script_type === 'none';

  return (
    <Modal
      onClose={onClose}
      title={isEdit ? 'Skill 수정' : 'Skill 만들기'}
      size="lg"
      scroll="content"
      showCloseButton={false}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>
              이름 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="예: 환율 계산기"
              maxLength={255}
              className={inputCls}
              autoFocus
            />
          </div>

          <div>
            <label className={labelCls}>설명</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="스킬에 대한 설명"
              className={inputCls}
            />
          </div>

          <div>
            <label className={labelCls}>트리거 (사용 시점)</label>
            <input
              type="text"
              value={form.trigger}
              onChange={(e) => set('trigger', e.target.value)}
              placeholder="예: 환율, 통화 변환 요청 시"
              className={inputCls}
            />
          </div>

          <div>
            <label className={labelCls}>
              지시문 (instruction) <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.instruction}
              onChange={(e) => set('instruction', e.target.value)}
              placeholder="이런 상황에 이렇게 동작하라 ..."
              rows={5}
              className={inputCls}
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className={labelCls}>스크립트 타입</label>
              <Dropdown
                value={form.script_type}
                onChange={(v) => set('script_type', v as SkillScriptType)}
                options={SCRIPT_TYPES.map((t) => ({ value: t, label: t }))}
                className="w-full"
              />
            </div>
            <div className="flex-1">
              <label className={labelCls}>공개 범위</label>
              <Dropdown
                value={form.visibility}
                onChange={(val) => set('visibility', val as SkillVisibility)}
                options={VISIBILITIES.map((v) => ({ value: v, label: VISIBILITY_LABEL[v] }))}
                className="w-full"
              />
            </div>
          </div>

          {form.visibility === 'department' && (
            <div>
              <label className={labelCls}>
                부서 ID <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={form.department_id}
                onChange={(e) => set('department_id', e.target.value)}
                placeholder="공유할 부서의 ID"
                className={inputCls}
              />
            </div>
          )}

          <div>
            <label className={labelCls}>스크립트 (script_content)</label>
            <textarea
              value={form.script_content}
              onChange={(e) => set('script_content', e.target.value)}
              placeholder={isNone ? "타입이 'none'이면 입력할 수 없습니다." : 'def convert(): ...'}
              rows={4}
              disabled={isNone}
              className={`${inputCls} font-mono text-[12.5px] disabled:bg-zinc-50 disabled:text-zinc-400`}
            />
            <p className="mt-1 text-[12px] text-amber-600">
              ⚠ 스크립트는 저장만 되며 현재 실행되지 않습니다.
            </p>
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
              {isPending ? '저장 중...' : isEdit ? '저장' : '만들기'}
            </button>
          </div>
      </form>
    </Modal>
  );
};

const AdminSkillsPage = () => {
  const { data, isLoading, isError, refetch } = useSkills({ scope: 'all' });
  const skills = data?.skills ?? [];

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SkillSummary | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: editingSkill } = useSkill(editingId);

  const createMutation = useCreateSkill();
  const updateMutation = useUpdateSkill();
  const deleteMutation = useDeleteSkill();
  const forkMutation = useForkSkill();

  const apiError = (err: unknown, fallback: string) =>
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback;

  const handleCreate = (req: CreateSkillRequest) => {
    createMutation.mutate(req, {
      onSuccess: () => setIsCreateOpen(false),
      onError: (err) => setFormError(apiError(err, 'Skill 생성에 실패했습니다.')),
    });
  };

  const handleUpdate = (dataReq: UpdateSkillRequest) => {
    if (!editingId) return;
    updateMutation.mutate(
      { id: editingId, data: dataReq },
      {
        onSuccess: () => setEditingId(null),
        onError: (err) => setFormError(apiError(err, 'Skill 수정에 실패했습니다.')),
      },
    );
  };

  const handleDelete = () => {
    if (!deleting) return;
    deleteMutation.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
  };

  const handleFork = (id: string) => {
    forkMutation.mutate({ id, data: {} });
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Admin</p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">Skill 관리</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            재사용 Skill(지시문 + 스크립트)을 만들고 관리합니다. 스크립트는 저장 전용입니다.
          </p>
        </div>
        <button
          onClick={() => { setFormError(null); setIsCreateOpen(true); }}
          className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Skill 만들기
        </button>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : isError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">Skill 목록을 불러오지 못했습니다.</p>
          <button
            onClick={() => refetch()}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            다시 시도
          </button>
        </div>
      ) : skills.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">등록된 Skill이 없습니다.</p>
          <button
            onClick={() => { setFormError(null); setIsCreateOpen(true); }}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            + 첫 번째 Skill 만들기
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">이름</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">타입</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">공개범위</th>
                <th className="w-[200px] px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {skills.map((s) => (
                <tr key={s.id} className="transition-colors hover:bg-zinc-50/50">
                  <td className="px-5 py-4">
                    <div className="text-[14px] font-medium text-zinc-900">{s.name}</div>
                    <div className="text-[12px] text-zinc-400">{s.description}</div>
                  </td>
                  <td className="px-5 py-4">
                    <span className="rounded-md bg-violet-50 px-2 py-1 text-[11.5px] font-medium text-violet-600">
                      {s.script_type}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11.5px] font-medium text-zinc-500">
                      {VISIBILITY_LABEL[s.visibility]}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      {s.can_edit ? (
                        <button
                          onClick={() => { setFormError(null); setEditingId(s.id); }}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 active:scale-95"
                        >
                          수정
                        </button>
                      ) : (
                        <button
                          onClick={() => handleFork(s.id)}
                          disabled={forkMutation.isPending}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-200 hover:text-violet-600 active:scale-95 disabled:opacity-50"
                        >
                          Fork
                        </button>
                      )}
                      {s.can_delete && (
                        <button
                          onClick={() => setDeleting(s)}
                          aria-label={`${s.name} 삭제`}
                          className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95"
                        >
                          삭제
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 생성 모달 */}
      <SkillFormModal
        isOpen={isCreateOpen}
        skill={null}
        onClose={() => setIsCreateOpen(false)}
        onSubmitCreate={handleCreate}
        onSubmitUpdate={() => {}}
        isPending={createMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 수정 모달 — 상세를 불러온 뒤 표시 */}
      <SkillFormModal
        isOpen={!!editingId && !!editingSkill}
        skill={editingSkill ?? null}
        onClose={() => setEditingId(null)}
        onSubmitCreate={() => {}}
        onSubmitUpdate={handleUpdate}
        isPending={updateMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 삭제 확인 */}
      <ConfirmDialog
        isOpen={!!deleting}
        title="Skill 삭제"
        description={`"${deleting?.name}" Skill을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
};

export default AdminSkillsPage;
