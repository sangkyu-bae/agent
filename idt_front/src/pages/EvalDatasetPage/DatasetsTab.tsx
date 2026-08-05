// eval-hub: 데이터셋 탭 — 검색·샘플 다운로드·생성 3방식·목록/빈상태 (revlu 시안)
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useDeleteTestset, useTestsets } from '@/hooks/useEval';
import CreateTestsetModal from './CreateTestsetModal';
import TestsetDetailPanel from './TestsetDetailPanel';

const SAMPLE_CSV_ROWS = [
  'question,ground_truth',
  '"여신 한도 산정 기준은 무엇인가요?","여신 한도는 담보 가치와 신용 등급을 기준으로 산정합니다."',
  '"연체 이자율은 어떻게 적용되나요?","연체 이자율은 약정 이자율에 연체 가산 이자율을 더해 적용합니다."',
];

const downloadSampleCsv = () => {
  const blob = new Blob(['﻿' + SAMPLE_CSV_ROWS.join('\n')], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'eval_dataset_sample.csv';
  a.click();
  URL.revokeObjectURL(url);
};

const DatasetsTab = () => {
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading } = useTestsets();
  const deleteMutation = useDeleteTestset();

  const testsets = data?.items ?? [];
  const keyword = search.trim().toLowerCase();
  const visible = keyword
    ? testsets.filter((t) => t.name.toLowerCase().includes(keyword))
    : testsets;

  const handleDelete = (testsetId: string) => {
    deleteMutation.mutate(testsetId, {
      onSuccess: () => {
        if (selectedId === testsetId) setSelectedId(null);
      },
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="relative w-72">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="QA 쌍 검색..."
            aria-label="QA 쌍 검색"
            className="w-full rounded-xl border border-zinc-200 bg-zinc-50 py-2 pl-9 pr-3 text-[13px] focus:border-violet-400 focus:bg-white focus:outline-none"
          />
          <svg
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
            fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.34-4.34m1.34-5.16a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z" />
          </svg>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={downloadSampleCsv}
            className="flex items-center gap-1.5 rounded-xl border border-zinc-200 px-3.5 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
          >
            ⬇ 샘플 데이터셋 다운로드
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 rounded-xl bg-zinc-900 px-3.5 py-2 text-[13px] font-medium text-white hover:bg-zinc-800"
          >
            + 데이터셋 생성
          </button>
        </div>
      </div>

      {isLoading && (
        <p className="py-16 text-center text-[13px] text-zinc-400">불러오는 중...</p>
      )}

      {!isLoading && testsets.length === 0 && (
        <div className="flex flex-col items-center py-24">
          <svg
            className="mb-3 h-10 w-10 text-zinc-300"
            fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375" />
          </svg>
          <p className="text-[13.5px] text-zinc-500">사용 가능한 데이터셋이 없습니다.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] text-zinc-600 hover:border-violet-300 hover:text-violet-600"
          >
            + 시작하려면 첫 번째 데이터셋을 생성하세요.
          </button>
        </div>
      )}

      {!isLoading && testsets.length > 0 && (
        <div className="space-y-2">
          {visible.map((t) => (
            <div
              key={t.id}
              className={`flex cursor-pointer items-center justify-between rounded-xl border px-4 py-3 transition-colors ${
                selectedId === t.id
                  ? 'border-violet-300 bg-violet-50/40'
                  : 'border-zinc-200 hover:border-zinc-300'
              }`}
              onClick={() => setSelectedId(selectedId === t.id ? null : t.id)}
            >
              <div>
                <p className="text-[13.5px] font-medium text-zinc-800">{t.name}</p>
                <p className="mt-0.5 text-[12px] text-zinc-400">
                  {t.description || '설명 없음'} · QA {t.case_count}건 ·{' '}
                  {new Date(t.created_at).toLocaleDateString('ko-KR')}
                </p>
              </div>
              <LoadingButton
                isPending={deleteMutation.isPending && deleteMutation.variables === t.id}
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(t.id);
                }}
                aria-label={`${t.name} 삭제`}
                className="rounded-lg px-2.5 py-1.5 text-[12px] text-zinc-400 hover:bg-red-50 hover:text-red-500"
              >
                삭제
              </LoadingButton>
            </div>
          ))}
          {visible.length === 0 && (
            <p className="py-8 text-center text-[13px] text-zinc-400">
              이름에 "{search.trim()}"이(가) 포함된 데이터셋이 없습니다.
            </p>
          )}
        </div>
      )}

      {selectedId && <TestsetDetailPanel testsetId={selectedId} search={search} />}

      {showCreate && <CreateTestsetModal onClose={() => setShowCreate(false)} />}
    </div>
  );
};

export default DatasetsTab;
