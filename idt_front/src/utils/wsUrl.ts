import { WS_BASE_URL } from '@/constants/api';

export function wsUrl(path: string, params?: Record<string, string>): string {
  const base = `${WS_BASE_URL}${path}`;
  if (!params || Object.keys(params).length === 0) return base;
  const qs = new URLSearchParams(params).toString();
  return `${base}?${qs}`;
}
