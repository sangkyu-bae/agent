// eval-hub: 선택 테스트셋의 QA 쌍 테이블 — 검색어는 클라이언트 필터
import { useTestsetDetail } from '@/hooks/useEval';

interface TestsetDetailPanelProps {
  testsetId: string;
  search: string;
}

const TestsetDetailPanel = ({ testsetId, search }: TestsetDetailPanelProps) => {
  const { data, isLoading } = useTestsetDetail(testsetId);

  if (isLoading) {
    return <p className="py-8 text-center text-[13px] text-zinc-400">불러오는 중...</p>;
  }
  if (!data) return null;

  const keyword = search.trim().toLowerCase();
  const filtered = keyword
    ? data.cases.filter(
        (c) =>
          c.question.toLowerCase().includes(keyword) ||
          (c.ground_truth ?? '').toLowerCase().includes(keyword),
      )
    : data.cases;

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-zinc-200">
      <div className="border-b border-zinc-100 bg-zinc-50 px-4 py-2.5 text-[12.5px] text-zinc-500">
        <span className="font-medium text-zinc-700">{data.name}</span>
        {' — '}QA {filtered.length}건{keyword && ` (검색: "${search.trim()}")`}
      </div>
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-zinc-100 text-[11.5px] uppercase tracking-widest text-zinc-400">
            <th className="w-12 px-4 py-2.5">#</th>
            <th className="w-1/2 px-4 py-2.5">질문</th>
            <th className="px-4 py-2.5">정답</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-50">
          {filtered.map((c, i) => (
            <tr key={i} className="align-top hover:bg-violet-50/30">
              <td className="px-4 py-3 text-[12.5px] text-zinc-400">{i + 1}</td>
              <td className="px-4 py-3 text-[13px] leading-relaxed text-zinc-800">
                {c.question}
              </td>
              <td className="px-4 py-3 text-[13px] leading-relaxed text-zinc-500">
                {c.ground_truth ?? <span className="text-zinc-300">—</span>}
              </td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr>
              <td colSpan={3} className="px-4 py-8 text-center text-[13px] text-zinc-400">
                검색 결과가 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default TestsetDetailPanel;
