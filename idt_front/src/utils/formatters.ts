export const formatDate = (iso: string): string => {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso));
};

export const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
};

export const truncate = (text: string, maxLength: number): string =>
  text.length <= maxLength ? text : `${text.slice(0, maxLength)}...`;

/**
 * approval-gate: 서버 UTC 시각(ISO, +00:00/Z 포함)을 사용자 로컬 시각으로 표시.
 * Check G12 — 서버가 'Z' 없이 보내면 new Date() 가 로컬로 오해석했다. 백엔드가
 * UTC 를 명시하도록 고쳤으므로 여기서는 브라우저 로캘로만 변환한다.
 */
export const formatLocalDateTime = (iso: string | null | undefined): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};
