// Design Ref: golden-sample-blueprint §5.1 — /admin/blueprints (목록 · 추출/편집)
import { useState } from 'react';
import BlueprintEditor from './BlueprintEditor';
import BlueprintList from './BlueprintList';

type Mode = { kind: 'list' } | { kind: 'create' } | { kind: 'edit'; id: string };

const AdminBlueprintsPage = () => {
  const [mode, setMode] = useState<Mode>({ kind: 'list' });

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            Admin
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">발표자료 양식 (Blueprint)</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            Golden Sample(PDF/PPTX) 1부에서 스타일·페이지 패턴·서사를 추출해 저장하면, 에이전트가
            그 양식대로 발표자료를 생성합니다.
          </p>
        </div>
        {mode.kind === 'list' ? (
          <button
            type="button"
            onClick={() => setMode({ kind: 'create' })}
            className="rounded-xl bg-zinc-900 px-4 py-2.5 text-[13.5px] font-medium text-white transition-all hover:bg-zinc-800 active:scale-95"
          >
            + 새 blueprint
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setMode({ kind: 'list' })}
            className="rounded-xl border border-zinc-200 px-4 py-2.5 text-[13.5px] font-medium text-zinc-700 hover:bg-zinc-50"
          >
            ← 목록
          </button>
        )}
      </div>

      {mode.kind === 'list' && <BlueprintList onEdit={(id) => setMode({ kind: 'edit', id })} />}
      {mode.kind === 'create' && (
        <BlueprintEditor blueprintId={null} onSaved={() => setMode({ kind: 'list' })} />
      )}
      {mode.kind === 'edit' && (
        <BlueprintEditor blueprintId={mode.id} onSaved={() => setMode({ kind: 'list' })} />
      )}
    </div>
  );
};

export default AdminBlueprintsPage;
