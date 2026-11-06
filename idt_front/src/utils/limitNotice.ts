// Design Ref: agent-token-limit §5.2 D11 — 한도 도달 사유별 채팅 안내 문구.
// ANSWER_COMPLETED 의 limit_reason("iteration" | "token")을 그대로 받는다. 사유가 없고
// limit_reached 만 true 인 구 서버 응답은 일반 문구로 폴백한다 (excludedToolsNotice 패턴).
import type { LimitReason } from '@/types/websocket';

const NOTICES: Record<LimitReason, string> = {
  token:
    '토큰 예산 한도에 도달해 지금까지 수집한 정보로 답변했습니다. 설정 탭에서 토큰 예산을 올릴 수 있습니다.',
  iteration: '반복 실행 한도에 도달해 지금까지 수집한 정보로 답변했습니다.',
};

const GENERIC = '실행 한도에 도달해 지금까지 수집한 정보로 답변했습니다.';

export const limitReachedNotice = (
  reason: LimitReason | null | undefined,
  reached: boolean | undefined,
): string | null => {
  if (reason && reason in NOTICES) return NOTICES[reason];
  return reached ? GENERIC : null;
};
