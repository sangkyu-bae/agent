// excel-preview Design §5 — 산출 .xlsx 프리뷰 모달.
// 상태는 excelPreviewStore가 소유(§5.3 확정), ChatPage에 1회 마운트.
// 다운로드는 documentExtractorService.downloadGeneratedFile 재사용 (FR-13).
import { useState } from 'react';

import Modal from '@/components/common/Modal';
import LoadingButton from '@/components/common/LoadingButton';
import ExcelPreviewGrid from './ExcelPreviewGrid';
import { useExcelPreview } from '@/hooks/useExcelPreview';
import { useExcelPreviewStore, type ExcelPreviewTarget } from '@/store/excelPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import { ApiError } from '@/services/api/ApiError';
import type { ExcelPreviewSheet } from '@/types/excelPreview';

/** FR-11 오류 상태 매핑 (Design §6.1). canDownload=false면 다운로드 버튼 숨김 */
const errorView = (error: unknown): { message: string; canDownload: boolean } => {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return { message: '파일이 만료되었거나 찾을 수 없습니다.', canDownload: false };
    }
    if (error.status === 403) {
      return { message: '본인이 생성한 파일만 볼 수 있습니다.', canDownload: false };
    }
    if (error.status === 415 || error.status === 422) {
      return {
        message: '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.',
        canDownload: true,
      };
    }
  }
  return {
    message: '미리보기를 불러오지 못했습니다. 다시 시도해주세요.',
    canDownload: true,
  };
};

const truncatedNotice = (sheet: ExcelPreviewSheet): string =>
  `전체 ${sheet.total_rows.toLocaleString()}행 × ${sheet.total_cols.toLocaleString()}열 중 ` +
  `상위 ${sheet.rows.length.toLocaleString()}행 × ${sheet.columns.length.toLocaleString()}열 표시`;

interface ContentProps {
  target: ExcelPreviewTarget;
  onClose: () => void;
}

const ExcelPreviewModalContent = ({ target, onClose }: ContentProps) => {
  const { data, isPending, isError, error } = useExcelPreview(target.fileId);
  const [activeIdx, setActiveIdx] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownload = () => {
    setDownloading(true);
    setDownloadError(null);
    documentExtractorService
      .downloadGeneratedFile(target.fileId, target.filename)
      .catch(() => {
        // 미리보기 중 TTL 만료 등 — unhandled rejection 방지 + 사용자 안내 (G-01)
        setDownloadError('다운로드에 실패했습니다. 파일이 만료되었을 수 있습니다.');
      })
      .finally(() => setDownloading(false));
  };

  const failed = isError ? errorView(error) : null;
  const sheets = data?.sheets ?? [];
  const active = sheets[Math.min(activeIdx, Math.max(sheets.length - 1, 0))];
  const showDownload = !isError || failed?.canDownload;

  return (
    <Modal
      onClose={onClose}
      title={target.filename}
      subtitle="다운로드 전 미리보기 — 시트별 상위 일부만 표시됩니다"
      size="4xl"
      scroll="body"
      footer={
        <>
          {downloadError && (
            <span role="alert" className="mr-auto self-center text-[12.5px] text-rose-500">
              {downloadError}
            </span>
          )}
          {showDownload && (
            <LoadingButton
              isPending={downloading}
              pendingText="다운로드 중…"
              onClick={handleDownload}
              className="rounded-lg bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
            >
              다운로드
            </LoadingButton>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 transition-colors hover:bg-zinc-50"
          >
            닫기
          </button>
        </>
      }
    >
      {isPending && (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-zinc-400">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          미리보기를 불러오는 중…
        </div>
      )}

      {failed && (
        <div role="alert" className="py-16 text-center text-[13.5px] text-zinc-500">
          {failed.message}
        </div>
      )}

      {data && (
        <div className="flex min-h-0 flex-col gap-3">
          <div role="tablist" aria-label="시트" className="flex flex-wrap gap-1 border-b border-zinc-200 pb-2">
            {sheets.map((sheet, i) => (
              <button
                key={sheet.name + i}
                type="button"
                role="tab"
                aria-selected={i === activeIdx}
                onClick={() => setActiveIdx(i)}
                className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  i === activeIdx
                    ? 'bg-violet-100 text-violet-700'
                    : 'text-zinc-500 hover:bg-zinc-100'
                }`}
              >
                {sheet.name}
              </button>
            ))}
          </div>

          {active && active.truncated && (
            <p className="text-[12.5px] text-amber-600">⚠ {truncatedNotice(active)}</p>
          )}

          {active && active.columns.length === 0 ? (
            <div className="py-16 text-center text-[13.5px] text-zinc-400">데이터 없음</div>
          ) : (
            active && <ExcelPreviewGrid columns={active.columns} rows={active.rows} />
          )}
        </div>
      )}
    </Modal>
  );
};

/** target이 null이면 렌더하지 않는다. fileId 전환 시 key로 탭 상태를 초기화한다. */
const ExcelPreviewModal = () => {
  const target = useExcelPreviewStore((s) => s.target);
  const close = useExcelPreviewStore((s) => s.close);

  if (!target) return null;
  return <ExcelPreviewModalContent key={target.fileId} target={target} onClose={close} />;
};

export default ExcelPreviewModal;
