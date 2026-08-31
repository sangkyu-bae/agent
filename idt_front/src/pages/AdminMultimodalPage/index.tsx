// Design Ref: multimodal-extractor §5.1 — /admin/multimodal (설정 · 미리보기 2탭)
// 2차 네비(관리자 그룹 탭)는 레이아웃이 소유하므로 여기서는 페이지 내부 탭만 둔다.
import { useState } from 'react';
import MultimodalPreviewPanel from './MultimodalPreviewPanel';
import MultimodalSettingsForm from './MultimodalSettingsForm';

type Tab = 'settings' | 'preview';

const tabs: { key: Tab; label: string }[] = [
  { key: 'settings', label: '설정' },
  { key: 'preview', label: '미리보기' },
];

const AdminMultimodalPage = () => {
  const [tab, setTab] = useState<Tab>('settings');

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Admin</p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">멀티모달 추출</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          문서의 그림·차트·이미지형 표를 비전 모델로 해석하는 모듈의 전역 설정과 미리보기입니다.
        </p>
      </div>

      <div role="tablist" aria-label="멀티모달 추출 탭" className="mb-5 flex gap-1 border-b border-zinc-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-[14px] font-medium transition-colors ${
              tab === t.key
                ? 'border-violet-600 text-violet-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'settings' ? (
          <MultimodalSettingsForm />
        ) : (
          <MultimodalPreviewPanel onGoToSettings={() => setTab('settings')} />
        )}
      </div>
    </div>
  );
};

export default AdminMultimodalPage;
