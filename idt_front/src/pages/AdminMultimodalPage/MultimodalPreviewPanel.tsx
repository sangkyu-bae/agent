// Design Ref: multimodal-extractor §5.1/§5.4 미리보기 탭 — PDF 업로드 → 요약 바 → 요소 카드
import { useRef, useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useMultimodalPreview } from '@/hooks/useMultimodalPreview';
import { ApiError } from '@/services/api/ApiError';
import { PREVIEW_MAX_FILE_BYTES, type MultimodalPreviewResponse } from '@/types/multimodal';
import MultimodalElementCard from './MultimodalElementCard';

interface MultimodalPreviewPanelProps {
  /** 409 MULTIMODAL_NOT_CONFIGURED/DISABLED 시 설정 탭 유도 */
  onGoToSettings: () => void;
}

const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

const Stat = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded-lg bg-zinc-50 px-3 py-2">
    <div className="text-[11px] text-zinc-500">{label}</div>
    <div className="text-[15px] font-semibold text-zinc-900">{value}</div>
  </div>
);

const MultimodalPreviewPanel = ({ onGoToSettings }: MultimodalPreviewPanelProps) => {
  const [file, setFile] = useState<File | null>(null);
  const [debug, setDebug] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<{ message: string; status?: number } | null>(null);
  const [result, setResult] = useState<MultimodalPreviewResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const preview = useMultimodalPreview();

  const onPick = (f: File | null) => {
    setClientError(null);
    setServerError(null);
    if (!f) return setFile(null);
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setFile(null);
      return setClientError('PDF 파일만 업로드할 수 있습니다.');
    }
    if (f.size > PREVIEW_MAX_FILE_BYTES) {
      setFile(null);
      return setClientError('30MB 이하 파일만 업로드할 수 있습니다.');
    }
    setFile(f);
  };

  const run = async () => {
    if (!file) return;
    setServerError(null);
    try {
      setResult(await preview.mutateAsync({ file, debug }));
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined;
      setServerError({ message: getErrorMessage(err, '미리보기 실행에 실패했습니다.'), status });
    }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-zinc-200 bg-white p-5">
        <label htmlFor="mm-preview-file" className="mb-1.5 block text-[13px] font-medium text-zinc-700">
          PDF 파일
        </label>
        <input
          id="mm-preview-file"
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          className="block w-full text-[13px] text-zinc-700 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-50 file:px-3 file:py-1.5 file:text-[13px] file:font-medium file:text-violet-700"
        />
        <p className="mt-1 text-[12px] text-zinc-400">30MB 이하. 결과는 저장되지 않습니다.</p>
        {clientError && <p className="mt-1 text-[12px] text-red-500">{clientError}</p>}

        <div className="mt-4 flex items-center gap-4">
          <label className="flex items-center gap-2 text-[13px] text-zinc-700">
            <input
              type="checkbox"
              checked={debug}
              onChange={(e) => setDebug(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-violet-600"
            />
            debug (필터 제외 목록 포함)
          </label>
          <LoadingButton
            isPending={preview.isPending}
            pendingText="비전 호출 중…"
            disabled={!file}
            onClick={run}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-50"
          >
            실행
          </LoadingButton>
        </div>

        {serverError && (
          <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-600">
            {serverError.message}
            {serverError.status === 409 && (
              <>
                {' '}
                <button type="button" onClick={onGoToSettings} className="font-medium underline">
                  설정 탭에서 모델을 먼저 선택하세요
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {result && (
        <section aria-label="미리보기 결과" className="space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            <Stat label="후보" value={result.total_candidates} />
            <Stat label="필터 제외" value={result.dropped_by_filter} />
            <Stat label="상한 skip" value={result.skipped_by_limit} />
            <Stat label="성공" value={result.succeeded} />
            <Stat label="실패" value={result.failed} />
            <Stat label="모델" value={`${result.provider}/${result.model_name}`} />
            <Stat
              label="소요"
              value={`${result.timings_ms.extract ?? 0}+${result.timings_ms.describe ?? 0}ms`}
            />
          </div>

          {result.elements.length === 0 ? (
            <p className="text-[13px] text-zinc-500">추출된 이미지가 없습니다.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {result.elements.map((el) => (
                <MultimodalElementCard key={el.element_id} element={el} />
              ))}
            </div>
          )}

          {result.dropped && (
            <div className="rounded-2xl border border-zinc-200 bg-white p-4">
              <h3 className="mb-2 text-[13px] font-semibold text-zinc-800">
                필터 제외 목록 ({result.dropped.length})
              </h3>
              {result.dropped.length === 0 ? (
                <p className="text-[12px] text-zinc-400">없음</p>
              ) : (
                <table className="w-full text-[12px]">
                  <thead className="text-left text-zinc-500">
                    <tr>
                      <th className="py-1">페이지</th>
                      <th>사유</th>
                      <th>크기</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 text-zinc-700">
                    {result.dropped.map((d, i) => (
                      <tr key={i}>
                        <td className="py-1">p.{d.page}</td>
                        <td>{d.reason}</td>
                        <td>
                          {d.width}×{d.height}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
};

export default MultimodalPreviewPanel;
