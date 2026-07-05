import { useEffect, useState } from 'react';
import type { LlmModel } from '@/types/llmModel';
import type { ModelSettingsValue } from '@/types/agentBuilder';
import Dropdown from '@/components/common/Dropdown';
import Modal from '@/components/common/Modal';

interface ModelSettingsModalProps {
  isOpen: boolean;
  models?: LlmModel[];
  current: ModelSettingsValue;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onApply: (value: ModelSettingsValue) => void;
  onClose: () => void;
}

/**
 * 모델 설정 팝업 (chat_model.png).
 * - 모델 선택 + 온도(temperature)만 form에 적용.
 * - 최대 토큰 / Top P / Top K 는 UI 표시 전용(비활성·미저장) — Design §5.3.
 */
const ModelSettingsModal = ({
  isOpen,
  models,
  current,
  isLoading = false,
  isError = false,
  onRetry,
  onApply,
  onClose,
}: ModelSettingsModalProps) => {
  const [model, setModel] = useState(current.model);
  const [temperature, setTemperature] = useState(current.temperature);

  // 열릴 때마다 현재 form 값으로 로컬 상태 초기화.
  useEffect(() => {
    if (isOpen) {
      setModel(current.model);
      setTemperature(current.temperature);
    }
  }, [isOpen, current.model, current.temperature]);

  if (!isOpen) return null;

  const hasActiveKey = (models ?? []).some((m) => m.is_active);

  const handleSave = () => {
    onApply({ model, temperature });
    onClose();
  };

  return (
    <Modal
      title="모델 설정"
      size="md"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-xl bg-zinc-900 px-5 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
          >
            저장
          </button>
        </>
      }
    >
      <>
        {/* 모델 선택 */}
        <div className="mt-1">
          <label className="mb-1.5 block text-[13px] font-semibold text-zinc-700">모델 선택</label>
          {isLoading ? (
            <div className="h-[44px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
          ) : isError ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-5">
              <p className="text-[13px] text-zinc-500">모델 목록을 불러올 수 없습니다</p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
                >
                  다시 시도
                </button>
              )}
            </div>
          ) : (
            <>
              <Dropdown
                variant="model"
                value={model}
                onChange={setModel}
                placeholder="모델 선택"
                options={(models ?? []).map((m) => ({
                  value: m.model_name,
                  label: `${m.provider}:${m.display_name}`,
                  badge: m.is_active ? undefined : 'API 키 미등록',
                }))}
              />
              {!hasActiveKey && (
                <p className="mt-2 text-[12px] leading-relaxed text-amber-600">
                  모든 모델에 필요한 API 키가 등록되지 않았습니다. 설정 &gt; Secrets에서 키를 등록하세요.
                </p>
              )}
            </>
          )}
        </div>

        <hr className="my-5 border-zinc-100" />

        {/* 파라미터 */}
        <p className="mb-3 text-[12.5px] font-semibold text-zinc-500">파라미터</p>

        {/* 온도 (활성) */}
        <div className="mb-4">
          <div className="mb-1.5 flex items-center justify-between">
            <label className="text-[13px] font-semibold text-zinc-700">온도</label>
            <span className="rounded-lg bg-zinc-100 px-2.5 py-1 text-[12.5px] font-semibold tabular-nums text-zinc-700">
              {temperature.toFixed(1)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            aria-label="온도"
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-violet-600"
          />
        </div>

        {/* 비활성 파라미터 (UI만, 미저장) */}
        {(['최대 토큰', 'Top P', 'Top K'] as const).map((label) => (
          <div className="mb-3" key={label}>
            <label className="mb-1 block text-[13px] font-semibold text-zinc-400">{label}</label>
            <input
              type="text"
              disabled
              placeholder="(선택)"
              title="준비중 — 현재 적용되지 않습니다"
              className="w-full cursor-not-allowed rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2.5 text-[13.5px] text-zinc-400"
            />
          </div>
        ))}

        <div className="mt-2">
          <button
            type="button"
            disabled
            title="준비중"
            className="cursor-not-allowed text-[12.5px] font-medium text-violet-300"
          >
            ↗ 모델 관리
          </button>
          <p className="mt-1 text-[11.5px] text-zinc-400">
            모델 설정 페이지에서 모델 정의를 추가하거나 편집하세요
          </p>
        </div>
      </>
    </Modal>
  );
};

export default ModelSettingsModal;
