// Design Ref: document-file-preview §5.3 renderDocx — 옵션·shadow root 배치·링크 후처리 (§8.2 #15)
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { renderAsync } = vi.hoisted(() => ({ renderAsync: vi.fn() }));
vi.mock('docx-preview', () => ({ renderAsync }));

import { renderDocx } from './docxRenderer';

const makeRoot = () => document.createElement('div').attachShadow({ mode: 'open' });

beforeEach(() => {
  renderAsync.mockReset();
});

describe('renderDocx', () => {
  it('본문·스타일 컨테이너를 shadow root 안에 두고 안전한 옵션으로 렌더한다', async () => {
    renderAsync.mockResolvedValue(undefined);
    const root = makeRoot();
    const blob = new Blob(['x']);

    await renderDocx(blob, root);

    expect(renderAsync).toHaveBeenCalledTimes(1);
    const [data, body, styles, options] = renderAsync.mock.calls[0];
    expect(data).toBe(blob);
    expect(root.contains(body)).toBe(true);
    expect(root.contains(styles)).toBe(true);
    expect(options).toMatchObject({
      inWrapper: true,
      useBase64URL: true,
      renderAltChunks: false,
      renderComments: false,
      renderChanges: false,
      experimental: false,
    });
  });

  it('문서 내 링크를 스킴별로 정리한다 (Plan FR-09)', async () => {
    renderAsync.mockImplementation(async (_data, body: HTMLElement) => {
      body.innerHTML = [
        '<a id="web" href="https://example.com">web</a>',
        '<a id="mail" href="mailto:a@b.c">mail</a>',
        '<a id="anchor" href="#toc">toc</a>',
        '<a id="js" href="javascript:alert(1)">js</a>',
        '<a id="file" href="file:///c:/x">file</a>',
      ].join('');
    });
    const root = makeRoot();

    await renderDocx(new Blob(['x']), root);

    const get = (id: string) => root.getElementById(id) as HTMLAnchorElement;
    expect(get('web')).toHaveAttribute('target', '_blank');
    expect(get('web')).toHaveAttribute('rel', 'noopener noreferrer');
    expect(get('mail')).toHaveAttribute('target', '_blank');
    expect(get('anchor')).toHaveAttribute('href', '#toc');
    expect(get('anchor')).not.toHaveAttribute('target');
    expect(get('js')).not.toHaveAttribute('href');
    expect(get('file')).not.toHaveAttribute('href');
  });

  it('렌더 실패는 그대로 전파한다', async () => {
    renderAsync.mockRejectedValue(new Error('bad zip'));
    await expect(renderDocx(new Blob(['x']), makeRoot())).rejects.toThrow('bad zip');
  });

  // analysis G-01: shadow DOM은 규칙은 막지만 상속 속성(글꼴·줄 간격·색)은 넘어온다
  it('shadow root 첫 요소로 :host 상속 초기화 스타일을 넣는다', async () => {
    renderAsync.mockResolvedValue(undefined);
    const root = makeRoot();
    await renderDocx(new Blob(['x']), root);

    const first = root.firstElementChild as HTMLStyleElement;
    expect(first.tagName).toBe('STYLE');
    expect(first.textContent).toContain(':host');
    expect(first.textContent).toContain('all: initial');
    expect(first.textContent).toContain('Malgun Gothic');
  });

  // analysis G-02: 책갈피 id는 shadow root 안에 있어 문서 단위 해시 이동이 닿지 않는다
  it('#책갈피 클릭은 shadow root 안 대상으로 스크롤하고 URL 해시를 바꾸지 않는다', async () => {
    renderAsync.mockImplementation(async (_data, body: HTMLElement) => {
      body.innerHTML = '<a id="toc-link" href="#_Toc1">목차</a><span id="_Toc1">본문</span>';
    });
    const root = makeRoot();
    await renderDocx(new Blob(['x']), root);
    const target = root.getElementById('_Toc1') as HTMLElement;
    target.scrollIntoView = vi.fn();

    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    root.getElementById('toc-link')!.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(target.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  // analysis G-04: StrictMode 첫 effect처럼 취소된 렌더는 root를 건드리지 않는다
  it('취소되면 렌더하지 않고 root를 비워두지 않는다', async () => {
    const root = makeRoot();
    root.innerHTML = '<p id="prev">이전 렌더</p>';
    await renderDocx(new Blob(['x']), root, () => true);
    expect(renderAsync).not.toHaveBeenCalled();
    expect(root.getElementById('prev')).not.toBeNull();
  });

  it('렌더 도중 취소되면 링크 후처리를 건너뛴다', async () => {
    let cancelled = false;
    renderAsync.mockImplementation(async (_data, body: HTMLElement) => {
      body.innerHTML = '<a id="js" href="javascript:alert(1)">js</a>';
      cancelled = true;
    });
    const root = makeRoot();
    await renderDocx(new Blob(['x']), root, () => cancelled);
    // 후처리를 건너뛰었다는 증거 — 이 root는 곧 다음 렌더가 replaceChildren으로 덮는다
    expect(root.getElementById('js')).toHaveAttribute('href', 'javascript:alert(1)');
  });
});
