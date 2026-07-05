import { describe, it, expect } from 'vitest';
import {
  buildCronExpr,
  parseCronExpr,
  validateCronExpr,
  describeSpec,
  generateScheduleName,
  DEFAULT_CRON_FORM,
} from './scheduleCron';

describe('buildCronExpr', () => {
  it('폼 값을 5필드 표현식으로 결합한다', () => {
    expect(buildCronExpr(DEFAULT_CRON_FORM)).toBe('0 9 * * *');
    expect(
      buildCronExpr({ minute: '30', hour: '18', dayOfMonth: '1', month: '*', dayOfWeek: '*' }),
    ).toBe('30 18 1 * *');
  });
});

describe('parseCronExpr', () => {
  it('단순 표현식은 폼 값으로 왕복된다', () => {
    const form = parseCronExpr('0 9 * * *');
    expect(form).toEqual({ minute: '0', hour: '9', dayOfMonth: '*', month: '*', dayOfWeek: '*' });
    expect(buildCronExpr(form!)).toBe('0 9 * * *');
  });

  it('복합 표현식은 null을 반환한다 (표현식 모드 폴백)', () => {
    expect(parseCronExpr('*/10 * * * *')).toBeNull();
    expect(parseCronExpr('0,30 9 * * *')).toBeNull();
    expect(parseCronExpr('0 9-18 * * *')).toBeNull();
  });

  it('분이 *이거나 필드 수가 다르면 null', () => {
    expect(parseCronExpr('* 9 * * *')).toBeNull();
    expect(parseCronExpr('0 9 * *')).toBeNull();
    expect(parseCronExpr('0 24 * * *')).toBeNull(); // 시 범위 초과
  });
});

describe('validateCronExpr', () => {
  it('유효한 표현식을 통과시킨다', () => {
    expect(validateCronExpr('0 9 * * *').valid).toBe(true);
    expect(validateCronExpr('*/10 * * * *').valid).toBe(true);
    expect(validateCronExpr('0,30 9 * * 1').valid).toBe(true);
  });

  it('5필드가 아니면 거부한다', () => {
    expect(validateCronExpr('0 9 * *').valid).toBe(false);
    expect(validateCronExpr('0 9 * * * *').valid).toBe(false);
  });

  it('허용되지 않는 문자를 거부한다', () => {
    const r = validateCronExpr('0 9 * * MON');
    expect(r.valid).toBe(false);
    expect(r.error).toContain('요일');
  });

  it('단일 정수 범위를 검사한다', () => {
    expect(validateCronExpr('60 9 * * *').valid).toBe(false);
    expect(validateCronExpr('0 24 * * *').valid).toBe(false);
    expect(validateCronExpr('0 9 32 * *').valid).toBe(false);
  });

  it('10분 미만 간격을 거부한다 (분 필드 휴리스틱)', () => {
    expect(validateCronExpr('* * * * *').valid).toBe(false);
    expect(validateCronExpr('*/5 * * * *').valid).toBe(false);
    expect(validateCronExpr('0,5 * * * *').valid).toBe(false);
    expect(validateCronExpr('0-30 * * * *').valid).toBe(false);
    // 순환 간격: 55,0은 5분 간격
    expect(validateCronExpr('0,55 * * * *').valid).toBe(false);
  });
});

describe('describeSpec', () => {
  it('once 요약', () => {
    expect(
      describeSpec({ schedule_type: 'once', run_date: '2026-07-10', time_of_day: '09:00' }),
    ).toBe('1회 2026-07-10 09:00');
  });

  it('daily/weekly 요약 (백엔드 직접 생성분, days_of_week 0=월)', () => {
    expect(describeSpec({ schedule_type: 'daily', time_of_day: '09:00' })).toBe('매일 09:00 실행');
    expect(
      describeSpec({ schedule_type: 'weekly', time_of_day: '10:00', days_of_week: [0, 4] }),
    ).toBe('매주 월,금 10:00 실행');
  });

  it('cron 요약 — 매일/매주(0=일)/매월/매시', () => {
    expect(describeSpec({ schedule_type: 'cron', cron_expr: '0 9 * * *' })).toBe('매일 09:00 실행');
    expect(describeSpec({ schedule_type: 'cron', cron_expr: '30 18 * * 1' })).toBe(
      '매주 월 18:30 실행',
    );
    expect(describeSpec({ schedule_type: 'cron', cron_expr: '0 9 15 * *' })).toBe(
      '매월 15일 09:00 실행',
    );
    expect(describeSpec({ schedule_type: 'cron', cron_expr: '30 * * * *' })).toBe('매시 30분 실행');
  });

  it('복합 cron은 원문 표기로 폴백', () => {
    expect(describeSpec({ schedule_type: 'cron', cron_expr: '*/30 * * * *' })).toBe(
      '크론 */30 * * * *',
    );
  });
});

describe('generateScheduleName', () => {
  it('describeSpec 결과를 200자로 절단한다', () => {
    const name = generateScheduleName({ schedule_type: 'cron', cron_expr: '0 9 * * *' });
    expect(name).toBe('매일 09:00 실행');
    expect(name.length).toBeLessThanOrEqual(200);
  });
});
