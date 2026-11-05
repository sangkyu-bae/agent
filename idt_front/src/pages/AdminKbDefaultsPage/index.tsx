// Design Ref: agent-kb-quick-setup §5.1/§5.4 — /admin/kb-defaults (기본 임베딩 모델 1개)
// 2차 네비는 레이아웃이 소유한다 (layout-owned-nav-tabs 위키). 서버 404/409 메시지는 그대로 노출.
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useEmbeddingModelList } from '@/hooks/useEmbeddingModels';
import { useAdminKbDefaults, useUpdateAdminKbDefaults } from '@/hooks/useKbDefaults';
import type { AdminKbDefaultsResponse } from '@/types/kbQuickSetup';

const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

const AdminKbDefaultsPage = () => {
  const defaults = useAdminKbDefaults();
  const models = useEmbeddingModelList();
  const update = useUpdateAdminKbDefaults();

  const [selected, setSelected] = useState<string>('');
  const [syncedFrom, setSyncedFrom] = useState<AdminKbDefaultsResponse | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // 서버 상태가 바뀌면(첫 로드·저장 성공) 선택값 재동기화 — MultimodalSettingsForm 과 동일 패턴
  if (defaults.data && defaults.data !== syncedFrom) {
    setSyncedFrom(defaults.data);
    setSelected(
      defaults.data.default_embedding_model_id != null
        ? String(defaults.data.default_embedding_model_id)
        : '',
    );
  }

  const isDirty =
    !!defaults.data &&
    selected !== (defaults.data.default_embedding_model_id?.toString() ?? '');

  const handleSave = async () => {
    if (!selected) return;
    setSaveError(null);
    setSaved(false);
    try {
      await update.mutateAsync({ default_embedding_model_id: Number(selected) });
      setSaved(true);
    } catch (err) {
      setSaveError(getErrorMessage(err, '저장하지 못했습니다'));
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Admin</p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">지식베이스 기본값</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          에이전트 빌더에서 문서를 올릴 때 자동으로 만들어지는 지식베이스가 쓰는 기본값입니다.
        </p>
      </div>

      {defaults.isLoading ? (
        <p className="text-[13px] text-zinc-400">불러오는 중...</p>
      ) : defaults.isError ? (
        <p role="alert" className="text-[13px] text-red-600">설정을 불러오지 못했습니다</p>
      ) : (
        <div className="space-y-4 rounded-2xl border border-zinc-200 bg-white p-6">
          {!defaults.data?.configured && (
            <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700">
              미설정이면 사용자가 빌더에서 문서를 올릴 수 없습니다
            </p>
          )}
          {(defaults.data?.warnings ?? []).map((w) => (
            <p key={w} role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700">
              {w}
            </p>
          ))}

          <div>
            <label htmlFor="kb-default-embedding-model" className="mb-1.5 block text-[13px] font-medium text-zinc-700">
              기본 임베딩 모델
            </label>
            <select
              id="kb-default-embedding-model"
              aria-label="기본 임베딩 모델"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
            >
              <option value="">— 미선택 —</option>
              {(models.data?.models ?? []).map((m) => (
                <option key={m.id} value={String(m.id)}>
                  {m.display_name} ({m.vector_dimension}차원)
                </option>
              ))}
            </select>
            <p className="mt-1.5 text-[12px] text-zinc-400">
              변경은 이후 자동 생성되는 지식베이스에만 적용됩니다
            </p>
          </div>

          <div className="flex items-center gap-3">
            <LoadingButton
              type="button"
              isPending={update.isPending}
              pendingText="저장 중..."
              disabled={!selected || !isDirty}
              onClick={handleSave}
              className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              저장
            </LoadingButton>
            {saved && <span className="text-[12.5px] text-emerald-600">저장되었습니다</span>}
            {saveError && (
              <span role="alert" className="text-[12.5px] text-red-600">
                {saveError}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminKbDefaultsPage;
