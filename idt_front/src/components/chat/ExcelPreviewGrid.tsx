// excel-preview Design §5.3 — 그리드 교체 경계 (FR-12).
// columns/rows만 받는 순수 표시 컴포넌트. 전문 그리드(ag-grid 등) 도입 시 이 파일만 교체.
// 셀은 React 텍스트 노드로만 렌더 — dangerouslySetInnerHTML 금지 (XSS, Design §7).

interface ExcelPreviewGridProps {
  columns: string[];
  rows: string[][];
}

const ExcelPreviewGrid = ({ columns, rows }: ExcelPreviewGridProps) => (
  <div className="overflow-auto rounded-md border border-border">
    <table className="min-w-full border-collapse text-sm">
      <thead className="sticky top-0 bg-surface-muted">
        <tr>
          {columns.map((col, i) => (
            <th
              key={i}
              className="whitespace-nowrap border-b border-r border-border px-3 py-2 text-left font-semibold text-fg last:border-r-0"
            >
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r} className="odd:bg-surface even:bg-surface-muted">
            {row.map((cell, c) => (
              <td
                key={c}
                className="whitespace-nowrap border-b border-r border-border px-3 py-1.5 text-fg-secondary last:border-r-0"
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
