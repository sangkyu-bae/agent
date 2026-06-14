import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the constants module so we can control WS_BASE_URL deterministically.
vi.mock('@/constants/api', () => ({
  WS_BASE_URL: 'ws://example.test:8000',
}));

beforeEach(() => {
  vi.resetModules();
});

describe('wsUrl', () => {
  it('returns base + path when no params', async () => {
    const { wsUrl } = await import('./wsUrl');
    expect(wsUrl('/ws/echo')).toBe('ws://example.test:8000/ws/echo');
  });

  it('appends single param as query string', async () => {
    const { wsUrl } = await import('./wsUrl');
    expect(wsUrl('/ws/echo', { token: 'abc' })).toBe(
      'ws://example.test:8000/ws/echo?token=abc',
    );
  });

  it('appends multiple params', async () => {
    const { wsUrl } = await import('./wsUrl');
    const out = wsUrl('/ws/agent/r-1', { token: 'abc', foo: 'bar' });
    // URLSearchParams ordering is insertion-order
    expect(out).toBe('ws://example.test:8000/ws/agent/r-1?token=abc&foo=bar');
  });

  it('escapes special characters in params', async () => {
    const { wsUrl } = await import('./wsUrl');
    const out = wsUrl('/ws/echo', { token: 'a b&c=d' });
    expect(out).toBe('ws://example.test:8000/ws/echo?token=a+b%26c%3Dd');
  });

  it('omits ? when params is empty object', async () => {
    const { wsUrl } = await import('./wsUrl');
    expect(wsUrl('/ws/echo', {})).toBe('ws://example.test:8000/ws/echo');
  });
});
