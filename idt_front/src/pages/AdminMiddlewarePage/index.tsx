import { useState } from 'react';
import {
  useMiddlewareCatalog,
  useSetMiddlewareFlags,
} from '@/hooks/useMiddlewareCatalog';
import { useLlmModels } from '@/hooks/useLlmModels';
import type { MiddlewareCatalogItem } from '@/types/middleware';
import LoadingButton from '@/components/common/LoadingButton';

/** authClient가 detail을 ApiError(message, status)로 정규화한다 */
const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

type FlagField = 'is_builtin' | 'is_enforced';

/**
 * 관리자 미들웨어 관리 — builtin-middleware D10.
 * 카탈로그 목록에서 빌트인(생성 시 기본 적용)/강제(항상 적용)를 토글하고,
 * 기본 설정값을 타입별 필드 폼으로 편집한다 (JSON 원문 편집 없음 — Design §12.3).
 */
const AdminMiddlewarePage = () => {
  const { data: middlewares, isLoading, isError, refetch } = useMiddlewareCatalog();
  const setFlagsMutation = useSetMiddlewareFlags();
  const [error, setError] = useState<string | null>(null);
  // 행 단위 pending — 같은 행 이중 클릭 차단 (mutation-pending-guard 선례)
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [editingType, setEditingType] = useState<string | null>(null);

  const handleToggle = (item: MiddlewareCatalogItem, field: FlagField) => {
    const key = `${item.middleware_type}:${field}`;
    if (pendingKey) return;
    setError(null);
    setPendingKey(key);
    setFlagsMutation.mutate(
      {
        middlewareType: item.middleware_type,
        body: { [field]: !item[field] },
      },
      {
        onSettled: () => setPendingKey(null),
        onError: (err) =>
          setError(getErrorMessage(err, '미들웨어 설정 변경에 실패했습니다.')),
      },
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          Admin
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">미들웨어 관리</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          에이전트 실행 미들웨어의 빌트인(생성 시 기본 적용)·강제(모든 실행에 항상 적용)
          여부와 기본 설정값을 관리합니다. 강제 미들웨어는 기존 에이전트에도 즉시 적용됩니다.
        </p>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[52px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-10">
          <p className="text-[13px] text-zinc-500">미들웨어 목록을 불러올 수 없습니다</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            다시 시도
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200">
          <table className="w-full text-left">
            <thead className="bg-zinc-50 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">
              <tr>
                <th className="px-5 py-3">미들웨어</th>
                <th className="px-5 py-3">설명</th>
                <th className="px-5 py-3 text-center">빌트인</th>
                <th className="px-5 py-3 text-center">강제</th>
                <th className="px-5 py-3 text-center">설정</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white">
              {(middlewares ?? []).map((m) => (
                <MiddlewareRow
                  key={m.middleware_type}
                  item={m}
                  pendingKey={pendingKey}
                  onToggle={handleToggle}
                  isEditing={editingType === m.middleware_type}
                  onEditToggle={() =>
                    setEditingType((cur) =>
                      cur === m.middleware_type ? null : m.middleware_type,
                    )
                  }
                  onEditError={(msg) => setError(msg)}
                  onEditDone={() => setEditingType(null)}
                />
              ))}
              {(middlewares ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-[13px] text-zinc-400">
                    등록된 미들웨어가 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// ── 행 + 토글 스위치 ─────────────────────────────────────────

interface MiddlewareRowProps {
  item: MiddlewareCatalogItem;
  pendingKey: string | null;
  onToggle: (item: MiddlewareCatalogItem, field: FlagField) => void;
  isEditing: boolean;
  onEditToggle: () => void;
  onEditError: (msg: string) => void;
  onEditDone: () => void;
}

const MiddlewareRow = ({
  item,
  pendingKey,
  onToggle,
  isEditing,
  onEditToggle,
  onEditError,
  onEditDone,
}: MiddlewareRowProps) => (
  <>
    <tr>
      <td className="px-5 py-3.5">
        <span className="text-[13.5px] font-medium text-zinc-800">{item.name}</span>
        {item.is_enforced && (
          <span className="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-600">🔒 강제</span>
        )}
        {item.is_builtin && !item.is_enforced && (
          <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600">기본</span>
        )}
      </td>
      <td className="max-w-md px-5 py-3.5">
        <p className="line-clamp-2 text-[12.5px] text-zinc-500">{item.description}</p>
      </td>
      {(['is_builtin', 'is_enforced'] as const).map((field) => (
        <td key={field} className="px-5 py-3.5 text-center">
          <button
            type="button"
            role="switch"
            aria-checked={!!item[field]}
            aria-label={`${item.name} ${field === 'is_builtin' ? '빌트인' : '강제'}`}
            disabled={pendingKey === `${item.middleware_type}:${field}`}
            onClick={() => onToggle(item, field)}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
              item[field] ? 'bg-violet-600' : 'bg-zinc-300'
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                item[field] ? 'translate-x-[18px]' : 'translate-x-[3px]'
              }`}
            />
          </button>
        </td>
      ))}
      <td className="px-5 py-3.5 text-center">
        <button
          type="button"
          onClick={onEditToggle}
          className="rounded-lg px-2.5 py-1 text-[12px] font-medium text-violet-600 transition-colors hover:bg-violet-50"
        >
          {isEditing ? '닫기' : '편집'}
        </button>
      </td>
    </tr>
    {isEditing && (
      <tr>
        <td colSpan={5} className="bg-zinc-50/70 px-5 py-4">
          <MiddlewareConfigEditor
            item={item}
            onError={onEditError}
            onDone={onEditDone}
          />
        </td>
      </tr>
    )}
  </>
);

// ── 타입별 설정 편집 폼 (Design §12.3 — JSON 원문 편집 없음) ──

interface ConfigEditorProps {
  item: MiddlewareCatalogItem;
  onError: (msg: string) => void;
  onDone: () => void;
}

const numberOf = (v: unknown, fallback: number): number =>
  typeof v === 'number' ? v : fallback;

export const MiddlewareConfigEditor = ({ item, onError, onDone }: ConfigEditorProps) => {
  const [config, setConfig] = useState<Record<string, unknown>>({
    ...item.default_config,
  });
  const setFlagsMutation = useSetMiddlewareFlags();
  const { data: llmModels } = useLlmModels();
  const isRetry =
    item.middleware_type === 'model_retry' || item.middleware_type === 'tool_retry';
  const isCallLimit = item.middleware_type === 'model_call_limit';
  const isFallback = item.middleware_type === 'model_fallback';
  const fallbackModels = Array.isArray(config.fallback_models)
    ? (config.fallback_models as string[])
    : [];

  const setField = (key: string, value: unknown) =>
    setConfig((prev) => ({ ...prev, [key]: value }));

  const handleSave = () => {
    setFlagsMutation.mutate(
      { middlewareType: item.middleware_type, body: { default_config: config } },
      {
        onSuccess: onDone,
        onError: (err) =>
          onError(getErrorMessage(err, '기본 설정 저장에 실패했습니다.')),
      },
    );
  };

  const numberInput = (
    label: string,
    key: string,
    fallback: number,
    opts: { min?: number; max?: number; step?: number } = {},
  ) => (
    <label className="flex items-center gap-2 text-[12.5px] text-zinc-600">
      {label}
      <input
        type="number"
        value={numberOf(config[key], fallback)}
        min={opts.min}
        max={opts.max}
        step={opts.step ?? 1}
        onChange={(e) => setField(key, Number(e.target.value))}
        aria-label={`${item.name} ${label}`}
        className="w-24 rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[13px] outline-none focus:border-violet-400"
      />
    </label>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        {isRetry && (
          <>
            {numberInput('최대 재시도', 'max_retries', 3, { min: 0, max: 10 })}
            {numberInput('백오프 배수', 'backoff_factor', 2.0, { min: 1, step: 0.5 })}
            {numberInput('초기 지연(초)', 'initial_delay', 1.0, { min: 0, step: 0.5 })}
          </>
        )}
        {isCallLimit && (
          <>
            {numberInput('run당 호출 상한', 'run_limit', 10, { min: 1, max: 50 })}
            <label className="flex items-center gap-2 text-[12.5px] text-zinc-600">
              한도 도달 시
              <select
                value={String(config.exit_behavior ?? 'end')}
                onChange={(e) => setField('exit_behavior', e.target.value)}
                aria-label={`${item.name} 한도 도달 시 동작`}
                className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[13px] outline-none focus:border-violet-400"
              >
                <option value="end">정상 종료 (end)</option>
                <option value="error">에러 (error)</option>
              </select>
            </label>
          </>
        )}
        {isFallback && (
          <div className="w-full">
            <p className="mb-1.5 text-[12.5px] text-zinc-600">
              폴백 모델 (등록·활성 모델만 선택 가능)
            </p>
            {(llmModels ?? []).length === 0 ? (
              <p className="text-[12px] text-zinc-400">등록된 활성 모델이 없습니다</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(llmModels ?? []).map((model) => {
                  const selected = fallbackModels.includes(model.model_name);
                  return (
                    <button
                      key={model.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() =>
                        setField(
                          'fallback_models',
                          selected
                            ? fallbackModels.filter((n) => n !== model.model_name)
                            : [...fallbackModels, model.model_name],
                        )
                      }
                      className={`rounded-lg border px-2.5 py-1 text-[12px] transition-colors ${
                        selected
                          ? 'border-violet-400 bg-violet-50 text-violet-700'
                          : 'border-zinc-200 bg-white text-zinc-500 hover:border-zinc-300'
                      }`}
                    >
                      {model.model_name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
      <div className="flex justify-end">
        <LoadingButton
          isPending={setFlagsMutation.isPending}
          pendingText="저장 중…"
          onClick={handleSave}
          className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
        >
          설정 저장
        </LoadingButton>
      </div>
    </div>
  );
};

export default AdminMiddlewarePage;
