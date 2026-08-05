// eval-hub: QA 쌍 행 편집기 — 직접 입력과 문서 생성 draft 검토가 공용 사용
import type { TestCaseItem } from '@/types/eval';

interface ManualCaseEditorProps {
  cases: TestCaseItem[];
  onChange: (cases: TestCaseItem[]) => void;
}

const ManualCaseEditor = ({ cases, onChange }: ManualCaseEditorProps) => {
  const updateCase = (index: number, patch: Partial<TestCaseItem>) => {
    onChange(cases.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };

  const removeCase = (index: number) => {
    onChange(cases.filter((_, i) => i !== index));
  };

  const addCase = () => {
    onChange([...cases, { question: '', ground_truth: null }]);
  };

  return (
    <div className="space-y-3">
      {cases.map((c, i) => (
        <div key={i} className="rounded-xl border border-zinc-200 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11.5px] font-semibold uppercase tracking-widest text-zinc-400">
              QA {i + 1}
            </span>
            <button
              type="button"
              onClick={() => removeCase(i)}
              aria-label={`QA ${i + 1} 삭제`}
              className="text-[12px] text-zinc-400 hover:text-red-500"
            >
              삭제
            </button>
          </div>
          <input
            value={c.question}
            onChange={(e) => updateCase(i, { question: e.target.value })}
            placeholder="질문"
            aria-label={`질문 ${i + 1}`}
            className="mb-2 w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px] focus:border-violet-400 focus:outline-none"
          />
          <textarea
            value={c.ground_truth ?? ''}
            onChange={(e) =>
              updateCase(i, { ground_truth: e.target.value || null })
            }
            placeholder="정답 (선택 — 정확성 계열 메트릭에 필요)"
            aria-label={`정답 ${i + 1}`}
            rows={2}
            className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-[13px] focus:border-violet-400 focus:outline-none"
          />
        </div>
      ))}
      <button
        type="button"
        onClick={addCase}
        className="w-full rounded-xl border border-dashed border-zinc-300 py-2.5 text-[13px] text-zinc-500 hover:border-violet-300 hover:text-violet-600"
      >
        + QA 쌍 추가
      </button>
    </div>
  );
};

export default ManualCaseEditor;
