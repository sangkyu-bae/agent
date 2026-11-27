// stock-analysis-agents §9 — 시장 분석 화면 표시용 순수 함수.
import { ApiError } from '@/services/api/ApiError';
import {
  SKIP_REASON_LABELS,
  type MarketAnalysisSettings,
  type MarketAnalysisSettingsUpdate,
} from '@/types/marketAnalysis';

const CODE = /^([A-Z][A-Z_]+)(?:\((.*)\))?(?::\s*(.*))?$/;

const translateCode = (raw: string): string => {
  const m = CODE.exec(raw.trim());
  if (!m) return raw.trim();
  const label = SKIP_REASON_LABELS[m[1]];
  if (!label) return raw.trim();
  const extra = m[2] ?? m[3];
  return extra ? `${label} (${extra})` : label;
};

/**
 * 보류·게이트 사유를 한글로 — 서버 형식은 `판단 사유 · GATE: 코드(값), 코드` 또는 코드 하나
 * (Design §7.3). 판단 에이전트가 쓴 사유 문장은 그대로 둔다.
 */
export const translateSkipReason = (reason: string | null | undefined): string[] => {
  if (!reason) return [];
  const out: string[] = [];
  for (const part of reason.split(' · ')) {
    const text = part.trim();
    if (!text) continue;
    if (text.startsWith('GATE:')) {
      text
        .slice(5)
        .split(/,\s*(?=[A-Z])/)
        .forEach((code) => code.trim() && out.push(translateCode(code)));
    } else {
      out.push(translateCode(text));
    }
  }
  return out;
};

const KRW = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });

export const formatPrice = (value: number | null | undefined): string =>
  value === null || value === undefined ? '-' : KRW.format(value);

/** 수익률은 부호와 % 를 붙인다 — 색만으로 의미를 전하지 않는다 */
export const formatRate = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined) return '-';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
};

export const rateTone = (value: number | null | undefined): string => {
  if (value === null || value === undefined || value === 0) return 'text-fg-secondary';
  return value > 0 ? 'text-danger' : 'text-info';
};

export const formatUsd = (value: number | null | undefined): string =>
  value === null || value === undefined ? '-' : `$${value.toFixed(value < 1 ? 4 : 2)}`;

/** 서버 시각(UTC +00:00)을 서울 시각 문자열로 */
export const formatKst = (iso: string | null | undefined): string => {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export const formatKstTime = (iso: string | null | undefined): string => {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleTimeString('ko-KR', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
};

/** 지금 수동 실행하면 서버가 정할 회차 종류 — 서울 15:30 이후 장 마감, 그 전 장중
 * (백엔드 RoundSchedulePolicy.kind_for 와 같은 규칙). 확인창 문구에만 쓴다. */
export const roundKindAt = (now: Date): 'intraday' | 'close' => {
  const hhmm = now.toLocaleTimeString('en-GB', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return hhmm >= '15:30' ? 'close' : 'intraday';
};

const ERROR_MESSAGES: Record<string, string> = {
  MA_FORBIDDEN: '시장 분석 권한이 없습니다.',
  MA_NOT_FOUND: '대상을 찾을 수 없습니다.',
  MA_ROUND_RUNNING: '실행 중인 회차가 있습니다. 끝난 뒤 다시 시도하세요.',
  MA_INVALID_SETTING: '설정 값을 확인하세요.',
  MA_ROLE_AGENT_INVALID: '에이전트가 없거나 삭제되었습니다.',
  MA_UNAVAILABLE: '시장 분석 실행기를 준비하지 못했습니다. 서버 로그를 확인하세요.',
};

export const marketAnalysisErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof ApiError) {
    return (err.code && ERROR_MESSAGES[err.code]) || err.message || fallback;
  }
  return fallback;
};

/** 422 MA_INVALID_SETTING 의 필드별 사유 */
export const settingFieldErrors = (err: unknown): Record<string, string> => {
  if (err instanceof ApiError && err.detail && typeof err.detail === 'object') {
    const errors = (err.detail as { errors?: unknown }).errors;
    if (errors && typeof errors === 'object') return errors as Record<string, string>;
  }
  return {};
};

/** 관심종목 기간 필터 — created_at(UTC) 이 서울 기준 기간 안인지 */
export const withinPeriod = (
  iso: string | null,
  period: 'today' | '7d' | '30d',
  now: Date = new Date(),
): boolean => {
  if (!iso) return false;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return false;
  if (period === 'today') {
    const day = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' });
    return day(at) === day(now);
  }
  const days = period === '7d' ? 7 : 30;
  return now.getTime() - at.getTime() <= days * 24 * 60 * 60 * 1000;
};

/** 표의 행 전체를 버튼처럼 — 키보드로도 열 수 있게 */
export const rowProps = (onOpen: () => void, label: string) => ({
  role: 'button' as const,
  tabIndex: 0,
  'aria-label': label,
  onClick: onOpen,
  onKeyDown: (e: { key: string; preventDefault: () => void }) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen();
    }
  },
  className: 'cursor-pointer hover:bg-surface-muted',
});

/** 설정 저장 본문 — 스위치(enabled)는 빼고 보낸다. 스위치는 PUT /settings/enabled 만 (G9). */
export const withoutSwitch = (settings: MarketAnalysisSettings): MarketAnalysisSettingsUpdate => {
  const body: Partial<MarketAnalysisSettings> = { ...settings };
  delete body.enabled;
  return body as MarketAnalysisSettingsUpdate;
};

const DIRECTION_ARROWS: Record<string, string> = { up: '↑', down: '↓' };

/** 신호 한 건의 값 — scan_signals 가 준 값을 그대로("키 값"), 숫자는 천 단위 구분 (G3). */
export const formatSignalValues = (values: Record<string, unknown> | undefined): string =>
  Object.entries(values ?? {})
    .map(([key, value]) => `${key} ${typeof value === 'number' ? value.toLocaleString('ko-KR') : String(value)}`)
    .join(', ');

export const signalArrow = (direction: string | undefined): string =>
  (direction && DIRECTION_ARROWS[direction]) || '';
