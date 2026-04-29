import WeightSlider from './WeightSlider';
import { WEIGHT_PRESETS } from '@/types/collection';

interface HybridSearchPanelProps {
  bm25Weight: number;
  vectorWeight: number;
  topK: number;
  onBm25WeightChange: (value: number) => void;
  onVectorWeightChange: (value: number) => void;
  onTopKChange: (value: number) => void;
}

const TOP_K_OPTIONS = [3, 5, 10, 20] as const;

const HybridSearchPanel = ({
  bm25Weight,
  vectorWeight,
  topK,
  onBm25WeightChange,
  onVectorWeightChange,
  onTopKChange,
}: HybridSearchPanelProps) => {
  return (
    <div className="space-y-4 rounded-xl border border-zinc-200 bg-zinc-50/50 p-4">
      {/* Top K */}
      <div className="flex items-center gap-4">
        <label className="w-24 shrink-0 text-[13px] font-medium text-zinc-600">결과 수</label>
        <div className="flex items-center gap-1">
          {TOP_K_OPTIONS.map((k) => (
            <button
              key={k}
              onClick={() => onTopKChange(k)}
              className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition-all ${
                topK === k
                  ? 'bg-violet-600 text-white shadow-sm'
                  : 'text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700'
              }`}
            >
              Top {k}
            </button>
          ))}
        </div>
      </div>

      <WeightSlider label="BM25 가중치" value={bm25Weight} onChange={onBm25WeightChange} />
      <WeightSlider label="벡터 가중치" value={vectorWeight} onChange={onVectorWeightChange} />

      {/* Presets */}
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-zinc-400">프리셋:</span>
        {Object.entries(WEIGHT_PRESETS).map(([key, preset]) => (
          <button
            key={key}
            onClick={() => {
              onBm25WeightChange(preset.bm25_weight);
              onVectorWeightChange(preset.vector_weight);
            }}
            className={`rounded-lg border px-2.5 py-1 text-[11.5px] font-medium transition-all ${
              bm25Weight === preset.bm25_weight && vectorWeight === preset.vector_weight
                ? 'border-violet-300 bg-violet-50 text-violet-600'
                : 'border-zinc-200 bg-white text-zinc-500 hover:border-zinc-300 hover:bg-zinc-50'
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
};

export default HybridSearchPanel;
