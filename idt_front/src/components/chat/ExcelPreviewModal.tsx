// excel-preview Design §5 — 산출 .xlsx 프리뷰 모달.
// 상태는 excelPreviewStore가 소유(§5.3 확정), ChatPage에 1회 마운트.
// 다운로드는 documentExtractorService.downloadGeneratedFile 재사용 (FR-13).
// Design Ref: ui-redesign-chat §5.4 — Button·Tabs 키트와 토큰. 로직 변경 없음.
import { useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

import Modal from '@/components/common/Modal';
import Button from '@/components/ui/Button';
import Tabs from '@/components/ui/Tabs';
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
  const safeIdx = Math.min(activeIdx, Math.max(sheets.length - 1, 0));
  const active = sheets[safeIdx];
  const showDownload = !isError || failed?.canDownload;
  const tabItems = sheets.map((sheet, i) => ({ key: `${sheet.name}-${i}`, label: sheet.name }));

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
            <span role="alert" className="mr-auto self-center text-xs text-danger">
              {downloadError}
            </span>
          )}
          {showDownload && (
            <Button size="sm" isPending={downloading} pendingText="다운로드 중…" onClick={handleDownload}>
              다운로드
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onClose}>
            닫기
          </Button>
        </>
      }
    >
      {isPending && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-fg-subtle">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden="true" />
          미리보기를 불러오는 중…
        </div>
      )}

      {failed && (
        <div role="alert" className="py-16 text-center text-sm text-fg-muted">
          {failed.message}
        </div>
      )}

      {data && (
        <div className="flex min-h-0 flex-col gap-3">
          <Tabs
            aria-label="시트"
            items={tabItems}
            value={tabItems[safeIdx]?.key ?? ''}
            onChange={(key) => setActiveIdx(Math.max(0, tabItems.findIndex((t) => t.key === key)))}
          />

          {active && active.truncated && (
            <p className="flex items-center gap-1.5 text-xs text-warning">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={2} aria-hidden="true" />
              {truncatedNotice(active)}
            </p>
          )}

          {active && active.columns.length === 0 ? (
            <div className="py-16 text-center text-sm text-fg-subtle">데이터 없음</div>
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
