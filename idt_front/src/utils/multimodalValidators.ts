// multimodal-extractor Design §5.4 — 설정 폼 숫자 범위 검증 (MULTIMODAL_LIMITS = 도메인 VO와 동일)
import { MULTIMODAL_LIMITS } from '@/types/multimodal';

export type MultimodalNumericKey = keyof typeof MULTIMODAL_LIMITS;

/** 필드별 검증 메시지 (유효하면 undefined) */
export const validateMultimodalNumeric = (
  key: MultimodalNumericKey,
  raw: string,
  integer: boolean
): string | undefined => {
  const { min, max } = MULTIMODAL_LIMITS[key];
  if (raw.trim() === '') return '필수 입력입니다.';
  const n = Number(raw);
  if (Number.isNaN(n)) return '숫자를 입력하세요.';
  if (integer && !Number.isInteger(n)) return '정수를 입력하세요.';
  if (n < min || n > max) return `${min}~${max} 범위여야 합니다.`;
  return undefined;
};
