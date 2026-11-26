import { describe, expect, it } from 'vitest';
import { ApiError } from '@/services/api/ApiError';
import {
  formatRate,
  marketAnalysisErrorMessage,
  settingFieldErrors,
  translateSkipReason,
  withinPeriod,
} from './marketAnalysis';

describe('translateSkipReason', () => {
  it('판단 사유는 그대로, 게이트 코드는 한글로 푼다', () => {
    expect(
      translateSkipReason('거래량 부족 · GATE: DECISION_SKIP, RR_BELOW_MIN(1.60<2.00), NO_SLOT'),
    ).toEqual([
      '거래량 부족',
      '판단 에이전트가 보류',
      '손익비 부족 (1.60<2.00)',
      '남은 슬롯 없음',
    ]);
  });

  it('점수 사유의 괄호 값(쉼표 포함)을 유지한다', () => {
    expect(translateSkipReason('GATE: SCORE_BELOW_MIN(6<7, bear)')).toEqual([
      '점수가 체제별 최소 점수보다 낮음 (6<7, bear)',
    ]);
  });

  it('단일 코드·콜론 꼬리·모르는 코드', () => {
    expect(translateSkipReason('PARSE_FAILED')).toEqual(['판단 결과를 읽지 못함']);
    expect(translateSkipReason('JUDGE_FAILED: RUN_FAILED: x')).toEqual([
      '판단 에이전트 실행 실패 (RUN_FAILED: x)',
    ]);
    expect(translateSkipReason('NEW_CODE')).toEqual(['NEW_CODE']);
    expect(translateSkipReason(null)).toEqual([]);
  });
});

describe('formatters', () => {
  it('수익률에 부호를 붙인다', () => {
    expect(formatRate(5.5)).toBe('+5.50%');
    expect(formatRate(-2)).toBe('-2.00%');
    expect(formatRate(null)).toBe('-');
  });

  it('기간 필터는 서울 날짜 기준', () => {
    const now = new Date('2026-11-26T06:00:00+00:00'); // 서울 15:00
    expect(withinPeriod('2026-11-25T16:00:00+00:00', 'today', now)).toBe(true); // 서울 26일 01:00
    expect(withinPeriod('2026-11-25T14:00:00+00:00', 'today', now)).toBe(false); // 서울 25일 23:00
    expect(withinPeriod('2026-11-20T06:00:00+00:00', '7d', now)).toBe(true);
    expect(withinPeriod('2026-10-20T06:00:00+00:00', '30d', now)).toBe(false);
  });
});

describe('errors', () => {
  it('코드별 문구와 필드 사유', () => {
    const err = new ApiError('설정 값을 확인하세요.', 422, 'MA_INVALID_SETTING', {
      code: 'MA_INVALID_SETTING',
      errors: { max_per_round: '1~200 사이여야 합니다' },
    });
    expect(marketAnalysisErrorMessage(err, 'x')).toBe('설정 값을 확인하세요.');
    expect(settingFieldErrors(err)).toEqual({ max_per_round: '1~200 사이여야 합니다' });
    expect(marketAnalysisErrorMessage(new Error('?'), '기본')).toBe('기본');
  });
});
