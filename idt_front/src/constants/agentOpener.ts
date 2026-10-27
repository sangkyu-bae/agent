// agent-opener Design §5.1: 오프너 상한 상수 — 백엔드 OpenerPolicy
// (idt/src/domain/agent_opener/policies.py)의 프론트 미러. UX 가드용이며
// 검증 SoT는 백엔드다. 백엔드 상수를 바꾸면 이 파일도 함께 수정한다.
export const OPENER_LIMITS = {
  MAX_COUNT: 12,
  MAX_LENGTH: 200,
} as const;
