export const AGENT_STATUS_LABEL = {
  idle: '대기 중',
  thinking: '생각 중...',
  tool_calling: '도구 실행 중...',
  responding: '응답 생성 중...',
  error: '오류 발생',
} as const;

export const AGENT_STEP_TYPE_LABEL = {
  thought: '추론',
  tool_call: '도구 호출',
  tool_result: '도구 결과',
  final_answer: '최종 답변',
} as const;

export const MAX_AGENT_STEPS = 20;
