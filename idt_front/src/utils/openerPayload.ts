// Design Ref: agent-opener §5.1 — 저장 페이로드용 오프너 정리.
// 빈 행(입력 중 남은 행)은 422 대신 조용히 제거한다. 중복·개수·길이 검증은 서버 SoT.

/** strip 후 빈 항목을 제거한 배열 (순서 보존). */
export const buildOpenersForSave = (openers: string[]): string[] =>
  openers.map((text) => text.trim()).filter((text) => text.length > 0);
