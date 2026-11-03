// agent-run-source-citations Design §7 — 외부 링크는 http/https 만 연다.
const SAFE_PROTOCOLS = new Set(['http:', 'https:']);

export const isSafeHttpUrl = (url: string | null | undefined): url is string => {
  if (!url) return false;
  try {
    return SAFE_PROTOCOLS.has(new URL(url).protocol);
  } catch {
    // 상대 경로·스킴 없는 문자열은 URL 생성자가 거부한다.
    return false;
  }
};
