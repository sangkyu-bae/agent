// Design §5.1/§5.4 추출·편집 — 업로드 → 탭 편집 → 저장(POST) / 기존 편집 → 저장(PUT)
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useBlueprint, useCreateBlueprint, useUpdateBlueprint } from '@/hooks/useBlueprints';
import {
  BLUEPRINT_LIMITS,
  type AssetPreview,
  type BlueprintDraft,
  type BlueprintExtractResponse,
  type BlueprintResponse,
} from '@/types/blueprint';
import { excludePatterns, validateBlueprintDraft } from '@/utils/blueprintValidators';
import BlueprintTabs, { type EditorTab } from './BlueprintTabs';
import BlueprintUploadStep from './BlueprintUploadStep';

interface BlueprintEditorProps {
  blueprintId: string | null;
  onSaved: () => void;
}

const toDraft = (r: BlueprintResponse): BlueprintDraft => {
  const rest: BlueprintDraft & Partial<BlueprintResponse> = { ...r };
  delete rest.created_at;
  delete rest.updated_at;
  return rest;
};

interface EditorState {
  draft: BlueprintDraft;
  assets: AssetPreview[];
  pageThumbnails: (string | null)[];
  classification: { succeeded: number; failed: number } | null;
  /** create 전용 — 추출 응답 원본 바이트(되돌려 보냄) */
  assetData: Record<string, string>;
}

const inputClass =
  'w-full rounded-xl border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-800 outline-none focus:border-violet-400';

const BlueprintEditor = ({ blueprintId, onSaved }: BlueprintEditorProps) => {
  const isEdit = blueprintId !== null;
  const detail = useBlueprint(blueprintId);
  const create = useCreateBlueprint();
  const update = useUpdateBlueprint();
  const [state, setState] = useState<EditorState | null>(null);
  const [tab, setTab] = useState<EditorTab>('style');
  const [errors, setErrors] = useState<string[]>([]);
  const [syncedFrom, setSyncedFrom] = useState<string | null>(null);
  // G9: 패턴 제외는 가역 토글 — 저장 직전에만 draft 에 적용
  const [excluded, setExcluded] = useState<string[]>([]);
  const toggleExclude = (id: string) =>
    setExcluded((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  // edit 모드: 상세 도착 시 1회 동기화 (렌더 중 파생 — effect 로 setState 금지)
  if (isEdit && detail.data && syncedFrom !== detail.data.updated_at) {
    setSyncedFrom(detail.data.updated_at);
    setState({
      draft: toDraft(detail.data),
      assets: detail.data.assets.map((a) => ({ ...a, thumbnail_b64: null, data_b64: null })),
      pageThumbnails: [],
      classification: null,
      assetData: {},
    });
  }

  const onExtracted = (r: BlueprintExtractResponse) => {
    setState({
      draft: toDraft(r.draft),
      assets: r.assets,
      pageThumbnails: r.page_thumbnails,
      classification: r.classification,
      assetData: Object.fromEntries(r.assets.filter((a) => a.data_b64).map((a) => [a.id, a.data_b64 as string])),
    });
  };

  const patch = (partial: Partial<BlueprintDraft>) =>
    setState((prev) => (prev ? { ...prev, draft: { ...prev.draft, ...partial } } : prev));

  const save = () => {
    if (!state) return;
    const draft = excludePatterns(state.draft, excluded);
    const found = validateBlueprintDraft(draft);
    setErrors(found);
    if (found.length) return;
    if (isEdit) {
      update.mutate({ id: blueprintId, req: { draft } }, { onSuccess: onSaved });
    } else {
      const assets = draft.assets
        .filter((a) => state.assetData[a.id])
        .map((a) => ({ id: a.id, data_b64: state.assetData[a.id] }));
      create.mutate({ draft, assets }, { onSuccess: onSaved });
    }
  };

  if (isEdit && detail.isLoading) {
    return <div className="h-40 animate-pulse rounded-2xl bg-zinc-100" aria-label="로딩 중" />;
  }
  if (isEdit && detail.isError) {
    return (
      <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700">
        {detail.error.message}
      </p>
    );
  }
  if (!state) return <BlueprintUploadStep onExtracted={onExtracted} />;

  const pending = create.isPending || update.isPending;
  const serverError = create.error?.message ?? update.error?.message ?? null;

  return (
    <div className="space-y-5">
      {state.classification && (
        <p className="rounded-xl bg-violet-50 px-4 py-2.5 text-[12.5px] text-violet-800">
          추출 완료 — 페이지 분류 성공 {state.classification.succeeded} / 실패{' '}
          {state.classification.failed}. 탭에서 검토·편집한 뒤 저장하세요.
        </p>
      )}

      <section className="rounded-2xl border border-zinc-200 bg-white p-5">
        <h2 className="text-[15px] font-semibold text-zinc-800">
          {isEdit ? '2. 편집' : '2. 결과 검토·편집'}
        </h2>
        <BlueprintTabs
          tab={tab}
          onTab={setTab}
          draft={state.draft}
          assets={state.assets}
          pageThumbnails={state.pageThumbnails}
          excluded={excluded}
          onToggleExclude={toggleExclude}
          onPatch={patch}
        />
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-5">
        <h2 className="text-[15px] font-semibold text-zinc-800">3. 이름·저장</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <label htmlFor="bp-name" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
              이름 (필수)
            </label>
            <input
              id="bp-name"
              value={state.draft.name}
              maxLength={BLUEPRINT_LIMITS.name_max}
              onChange={(e) => patch({ name: e.target.value })}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="bp-desc" className="mb-1 block text-[12.5px] font-semibold text-zinc-600">
              설명
            </label>
            <input
              id="bp-desc"
              value={state.draft.description}
              maxLength={BLUEPRINT_LIMITS.description_max}
              onChange={(e) => patch({ description: e.target.value })}
              className={inputClass}
            />
          </div>
        </div>
        {errors.length > 0 && (
          <ul role="alert" className="mt-3 list-disc space-y-0.5 pl-5 text-[12.5px] text-red-600">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        {serverError && (
          <p role="alert" className="mt-3 text-[12.5px] text-red-600">
            {serverError}
          </p>
        )}
        <div className="mt-4 flex justify-end">
          <LoadingButton
            isPending={pending}
            pendingText="저장 중…"
            onClick={save}
            className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white hover:bg-zinc-800"
          >
            저장
          </LoadingButton>
        </div>
      </section>
    </div>
  );
};

export default BlueprintEditor;
