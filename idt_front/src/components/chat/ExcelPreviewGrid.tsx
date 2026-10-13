// excel-preview Design §5.3 — 그리드 교체 경계 (FR-12).
// columns/rows만 받는 순수 표시 컴포넌트. 전문 그리드(ag-grid 등) 도입 시 이 파일만 교체.
// 셀은 React 텍스트 노드로만 렌더 — dangerouslySetInnerHTML 금지 (XSS, Design §7).

interface ExcelPreviewGridProps {
  columns: string[];
  rows: string[][];
}

const ExcelPreviewGrid = ({ columns, rows }: ExcelPreviewGridProps) => (
  <div className="overflow-auto rounded-lg border border-zinc-200">
    <table className="min-w-full border-collapse text-[13px]">
      <thead className="sticky top-0 bg-zinc-50">
        <tr>
          {columns.map((col, i) => (
            <th
              key={i}
              className="whitespace-nowrap border-b border-r border-zinc-200 px-3 py-2 text-left font-semibold text-zinc-900 last:border-r-0"
            >
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r} className="odd:bg-white even:bg-zinc-50/50">
            {row.map((cell, c) => (
              <td
                key={c}
                className="whitespace-nowrap border-b border-r border-zinc-100 px-3 py-1.5 text-zinc-700 last:border-r-0"
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default ExcelPreviewGrid;
