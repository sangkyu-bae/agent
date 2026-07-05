import type { ScheduleSpecPayload } from '@/types/agentSchedule';

// agent-schedule: cron 표현식 조합/역파싱/검증 + 스케줄 이름 자동 생성
// cron 요일 기수는 표준(0=일요일). spec.days_of_week(weekly, 0=월요일)와 다름에 주의.

export interface CronFormValue {
  /** '0'~'59' — '*' 불허 (최소 간격 10분 규칙) */
  minute: string;
  /** '*'(매시) | '0'~'23' */
  hour: string;
  /** '*'(매일) | '1'~'31' */
  dayOfMonth: string;
  /** '*'(매월) | '1'~'12' */
  month: string;
  /** '*'(매일) | '0'~'6' (0=일요일) */
  dayOfWeek: string;
}

export const DEFAULT_CRON_FORM: CronFormValue = {
  minute: '0',
  hour: '9',
  dayOfMonth: '*',
  month: '*',
  dayOfWeek: '*',
};

/** cron 요일 라벨 (0=일요일) */
export const CRON_DOW_LABELS = ['일', '월', '화', '수', '목', '금', '토'] as const;
/** spec.days_of_week 요일 라벨 (0=월요일) */
const WEEKLY_DOW_LABELS = ['월', '화', '수', '목', '금', '토', '일'] as const;

const isPlainInt = (v: string) => /^\d+$/.test(v);

const inRange = (v: string, lo: number, hi: number) =>
  isPlainInt(v) && Number(v) >= lo && Number(v) <= hi;

export const buildCronExpr = (form: CronFormValue): string =>
  [form.minute, form.hour, form.dayOfMonth, form.month, form.dayOfWeek].join(' ');

/**
 * 폼으로 표현 가능한 단순 표현식만 역파싱.
 * 각 필드가 '*' 또는 범위 내 단일 정수(분은 정수 필수)일 때만 성공,
 * 복합식('*\/5', '1,3', '1-5' 등)은 null → 표현식 모드 폴백.
 */
export const parseCronExpr = (expr: string): CronFormValue | null => {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) return null;
  const [minute, hour, dayOfMonth, month, dayOfWeek] = fields;
  if (!inRange(minute, 0, 59)) return null;
  const ok = (v: string, lo: number, hi: number) => v === '*' || inRange(v, lo, hi);
  if (!ok(hour, 0, 23) || !ok(dayOfMonth, 1, 31) || !ok(month, 1, 12) || !ok(dayOfWeek, 0, 6)) {
    return null;
  }
  return { minute, hour, dayOfMonth, month, dayOfWeek };
};

const FIELD_DEFS: Array<{ label: string; lo: number; hi: number }> = [
  { label: '분', lo: 0, hi: 59 },
  { label: '시', lo: 0, hi: 23 },
  { label: '일', lo: 1, hi: 31 },
  { label: '월', lo: 1, hi: 12 },
  { label: '요일', lo: 0, hi: 6 },
];

const MIN_INTERVAL_ERROR =
  '실행 간격은 최소 10분이어야 합니다. 분 필드를 확인해주세요.';

/**
 * 표현식 기본 검증 + 최소 간격 10분 휴리스틱(분 필드).
 * 클라 선검증(UX)용 — 최종 검증은 백엔드 400 응답을 그대로 표출한다.
 */
export const validateCronExpr = (
  expr: string,
): { valid: boolean; error?: string } => {
  const fields = expr.trim().split(/\s+/);
  if (fields.length !== 5) {
    return { valid: false, error: 'cron 표현식은 5개 필드(분 시 일 월 요일)여야 합니다.' };
  }
  for (let i = 0; i < 5; i++) {
    const f = fields[i];
    const { label, lo, hi } = FIELD_DEFS[i];
    if (!/^[\d*,/-]+$/.test(f)) {
      return { valid: false, error: `${label} 필드에 허용되지 않는 문자가 있습니다.` };
    }
    if (isPlainInt(f) && !inRange(f, lo, hi)) {
      return { valid: false, error: `${label} 필드는 ${lo}~${hi} 범위여야 합니다.` };
    }
  }

  // 10분 휴리스틱 — 분 필드
  const minute = fields[0];
  if (minute === '*') return { valid: false, error: MIN_INTERVAL_ERROR };
  const step = minute.match(/^(?:\*|[\d-]+)\/(\d+)$/);
  if (step) {
    if (Number(step[1]) < 10) return { valid: false, error: MIN_INTERVAL_ERROR };
  } else if (/^\d+-\d+$/.test(minute)) {
    // 스텝 없는 범위는 매 분 실행과 동일
    return { valid: false, error: MIN_INTERVAL_ERROR };
  } else if (minute.includes(',')) {
    const nums = minute.split(',').map(Number);
    if (nums.some((n) => Number.isNaN(n) || n > 59)) {
      return { valid: false, error: '분 필드는 0~59 범위여야 합니다.' };
    }
    const sorted = [...nums].sort((a, b) => a - b);
    let minGap = 60 - sorted[sorted.length - 1] + sorted[0]; // 순환 간격
    for (let i = 1; i < sorted.length; i++) {
      minGap = Math.min(minGap, sorted[i] - sorted[i - 1]);
    }
    if (minGap < 10) return { valid: false, error: MIN_INTERVAL_ERROR };
  }
  return { valid: true };
};

const timeLabel = (hour: string, minute: string) =>
  `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;

/** 카드/이름용 사람이 읽는 요약 — API의 4개 유형 전부 커버 */
export const describeSpec = (spec: ScheduleSpecPayload): string => {
  switch (spec.schedule_type) {
    case 'once':
      return `1회 ${spec.run_date ?? ''} ${spec.time_of_day ?? ''}`.trim();
    case 'daily':
      return `매일 ${spec.time_of_day ?? ''} 실행`;
    case 'weekly': {
      const days = (spec.days_of_week ?? [])
        .map((d) => WEEKLY_DOW_LABELS[d] ?? String(d))
        .join(',');
      return `매주 ${days} ${spec.time_of_day ?? ''} 실행`;
    }
    case 'cron': {
      const expr = spec.cron_expr ?? '';
      const form = parseCronExpr(expr);
      if (!form) return `크론 ${expr}`;
      if (form.hour === '*') return `매시 ${Number(form.minute)}분 실행`;
      const time = timeLabel(form.hour, form.minute);
      if (form.dayOfWeek !== '*') {
        return `매주 ${CRON_DOW_LABELS[Number(form.dayOfWeek)]} ${time} 실행`;
      }
      if (form.dayOfMonth !== '*') {
        return `매월 ${Number(form.dayOfMonth)}일 ${time} 실행`;
      }
      if (form.month !== '*') return `크론 ${expr}`;
      return `매일 ${time} 실행`;
    }
  }
};

/** 스케줄 name 자동 생성 (API 제약 1~200자) */
export const generateScheduleName = (spec: ScheduleSpecPayload): string =>
  describeSpec(spec).slice(0, 200);
