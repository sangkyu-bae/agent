// Design Ref: ui-redesign-chat §10.4 — className 합성 헬퍼. falsy 값만 걸러낸다(외부 라이브러리 없음).
type ClassValue = string | number | false | null | undefined;

export const cn = (...parts: ClassValue[]): string =>
  parts.filter((p): p is string | number => p !== false && p != null && p !== '').join(' ');
