import { describe, expect, it } from 'vitest';

import { isSafeHttpUrl } from './safeUrl';

describe('isSafeHttpUrl', () => {
  it.each(['https://a.example/x?q=1', 'http://a.example', 'HTTPS://A.EXAMPLE'])(
    '%s 는 허용한다',
    (url) => {
      expect(isSafeHttpUrl(url)).toBe(true);
    },
  );

  it.each([
    'javascript:alert(1)',
    ' javascript:alert(1)',
    'data:text/html,<script>1</script>',
    'vbscript:x',
    '//a.example',
    '/relative',
    'not a url',
    '',
    undefined,
    null,
  ])('%s 는 거부한다', (url) => {
    expect(isSafeHttpUrl(url)).toBe(false);
  });
});
