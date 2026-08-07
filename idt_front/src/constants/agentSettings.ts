// agent-settings-tab D4: 반복 한도 상수 — 백엔드 IterationLimitPolicy
// (idt/src/domain/agent_builder/policies.py)의 프론트 미러.
// 백엔드에서 DEFAULT/MIN/MAX를 변경하면 반드시 이 파일도 함께 수정한다.
export const MAX_ITERATIONS = {
  DEFAULT: 25,
  MIN: 10,
  MAX: 1000,
} as const;
