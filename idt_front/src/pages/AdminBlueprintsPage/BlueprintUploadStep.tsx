// Design §5.4 추출 — 파일 선택 + 추출 호출 (multipart, 진행 표시)
import { useState, type ChangeEvent } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useExtractBlueprint } from '@/hooks/useBlueprints';
import { BLUEPRINT_LIMITS, type BlueprintExtractResponse } from '@/types/blueprint';
import { isAcceptedSampleFile } from '@/utils/blueprintValidators';

interface BlueprintUploadStepProps {
  onExtracted: (result: BlueprintExtractResponse) => void;
}

const BlueprintUploadStep = ({ onExtracted }: BlueprintUploadStepProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const extract = useExtractBlueprint();

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0] ?? null;
    setFile(picked);
    setLocalError(
      picked && !isAcceptedSampleFile(picked)
        ? `PDF 또는 PPTX 파일만, ${BLUEPRINT_LIMITS.upload_max_bytes / 1024 / 1024}MB 이하로 올려주세요.`
        : null
    );
  };

  const run = () => {
    if (!file || localError) return;
    extract.mutate({ file, maxPages: BLUEPRINT_LIMITS.max_pages_default }, { onSuccess: onExtracted });
  };

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-5">
      <h2 className="text-[15px] font-semibold text-zinc-800">1. Golden Sample 업로드</h2>
      <p className="mt-1 text-[12.5px] text-zinc-400">
        대표 발표자료 1부를 올리면 페이지별 레이아웃 패턴(비전 분석)·팔레트·폰트·서사 구조를
        추출합니다. PPTX 원본이면 좌표 정확도가 높습니다.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          aria-label="Golden Sample 파일"
          type="file"
          accept=".pdf,.pptx"
          onChange={onPick}
          className="text-[13px] text-zinc-600 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-[12.5px] file:font-medium"
        />
        <LoadingButton
          isPending={extract.isPending}
          pendingText="추출 중 (비전 분류 → 서사 종합)…"
          disabled={!file || !!localError}
          onClick={run}
          className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-40"
        >
          추출 시작
        </LoadingButton>
      </div>
      {localError && (
        <p role="alert" className="mt-2 text-[12.5px] text-red-600">
          {localError}
        </p>
      )}
      {extract.isError && (
        <p role="alert" className="mt-2 text-[12.5px] text-red-600">
          {extract.error.message}
        </p>
      )}
    </section>
  );
};

export default BlueprintUploadStep;
