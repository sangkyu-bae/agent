// answer-citation-verification Design §4.2 — 백엔드 계약: idt/src/interfaces/schemas/grounding_judge.py

/** 실제 적용 모델의 출처 — 관리자 설정 / env GROUNDING_JUDGE_MODEL / 기본 모델 */
export const JUDGE_MODEL_SOURCE = {
  ADMIN: 'admin',
  ENV: 'env',
  DEFAULT: 'default',
} as const;

export type JudgeModelSource = (typeof JUDGE_MODEL_SOURCE)[keyof typeof JUDGE_MODEL_SOURCE];

export const JUDGE_MODEL_SOURCE_LABEL: Record<JudgeModelSource, string> = {
  admin: '관리자 설정',
  env: '서버 환경 설정',
  default: '시스템 기본 모델',
};

export interface EffectiveJudgeModel {
  model_id: string;
  model_name: string;
  display_name: string;
  source: JudgeModelSource;
}

export interface GroundingJudgeSettingResponse {
  judge_llm_model_id: string | null;
  effective: EffectiveJudgeModel | null;
}

export interface GroundingJudgeSettingRequest {
  /** null 이면 관리자 설정을 비우고 서버 환경 설정 모델을 쓴다 */
  judge_llm_model_id: string | null;
}
