// Design Ref: agent-edit-entry §3.3 — 편집 진입 URL 생성과 복귀 경로 검증을 한 곳에 둔다.
// 워크스페이스·채팅 헤더·빌더가 같은 규칙을 공유한다.

export const AGENT_EDIT_PARAM = 'edit';
export const RETURN_TO_PARAM = 'returnTo';

/** 빌더 편집 진입 URL. returnTo 생략 시 파라미터도 생략 */
export const buildAgentEditPath = (agentId: string, returnTo?: string): string => {
  const params = new URLSearchParams({ [AGENT_EDIT_PARAM]: agentId });
  if (returnTo) params.set(RETURN_TO_PARAM, returnTo);
  return `/agent-builder?${params.toString()}`;
};

/** 앱 내부 경로만 통과. 외부 URL·프로토콜 상대 경로는 오픈 리다이렉트 방지를 위해 null */
export const parseSafeReturnTo = (raw: string | null): string | null => {
  if (!raw) return null;
  if (!raw.startsWith('/')) return null;
  if (raw.startsWith('//') || raw.startsWith('/\\')) return null;
  return raw;
};
