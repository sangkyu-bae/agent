import { describe, expect, it } from 'vitest';

import { buildAgentEditPath, parseSafeReturnTo } from '@/utils/agentEditLink';

describe('buildAgentEditPath (agent-edit-entry)', () => {
  it('U1: agentId와 returnTo를 인코딩해 빌더 편집 경로를 만든다', () => {
    expect(buildAgentEditPath('agent-1', '/chatpage')).toBe(
      '/agent-builder?edit=agent-1&returnTo=%2Fchatpage',
    );
  });

  it('U2: returnTo를 생략하면 파라미터도 생략한다', () => {
    expect(buildAgentEditPath('agent-1')).toBe('/agent-builder?edit=agent-1');
  });
});

describe('parseSafeReturnTo (agent-edit-entry)', () => {
  it.each(['/chatpage', '/agents/a-1/workspace'])('U3: 앱 내부 경로 %s 는 그대로 통과한다', (path) => {
    expect(parseSafeReturnTo(path)).toBe(path);
  });

  it.each([
    null,
    '',
    'chatpage',
    'https://evil.com',
    '//evil.com',
    '/\\evil.com',
    'javascript:alert(1)',
  ])('U4: 내부 경로가 아닌 %s 는 null', (raw) => {
    expect(parseSafeReturnTo(raw)).toBeNull();
  });
});
