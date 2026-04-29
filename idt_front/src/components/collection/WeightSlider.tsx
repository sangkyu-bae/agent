interface WeightSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
}

const WeightSlider = ({ label, value, onChange }: WeightSliderProps) => {
  return (
    <div className="flex items-center gap-4">
      <label className="w-24 shrink-0 text-[13px] font-medium text-zinc-600">
        {label}
      </label>
      <input
        type="range"
        min={0}
        max={1}
        step={0.1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-zinc-200 accent-violet-600"
      />
      <span className="w-10 text-right text-[13px] font-semibold tabular-nums text-zinc-800">
        {value.toFixed(1)}
      </span>
    </div>
  );
};

export default WeightSlider;
