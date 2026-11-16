// Design Ref: document-file-preview §5.3 — docx-preview 호출은 이 모듈 한 곳에만 둔다.
// jsdom에서 렌더할 수 없으므로 컴포넌트 테스트는 이 모듈을 vi.mock 한다 (§1.2).

/** 렌더 후 남겨둘 링크 스킴. 그 외(javascript:, file: 등)는 href를 제거한다. */
const SAFE_LINK = /^(https?:|mailto:)/i;

/**
 * shadow DOM은 CSS 규칙은 막지만 상속 속성(글꼴·줄 간격·색)은 호스트에서 넘어온다.
 * 호스트를 초기화하고, 글꼴을 지정하지 않은 문서는 Word 한글 기본과 가까운 맑은 고딕으로 그린다.
 * (analysis G-01 — 헤드리스 측정에서 문단이 앱의 Pretendard·line-height 24px를 상속함)
 * 호스트의 Tailwind 클래스(높이·스크롤·테두리)는 바깥 규칙이 :host보다 우선해 그대로 적용된다.
 */
const HOST_RESET_CSS = `:host {
  all: initial;
  display: block;
  font-family: 'Malgun Gothic', '맑은 고딕', 'Apple SD Gothic Neo', sans-serif;
  color: #000;
}`;

/**
 * shadow root 안에 스타일·본문 컨테이너를 만들고 docx를 렌더한다.
 * shadow DOM이라 docx-preview가 넣는 <style>이 앱 화면과 섞이지 않는다 (Plan FR-08).
 *
 * @param isCancelled StrictMode 이중 effect 등으로 이 렌더가 무효가 됐는지 (analysis G-04).
 *   true면 root를 건드리지 않고 멈춘다 — 다음 렌더가 root를 다시 채운다.
 */
export const renderDocx = async (
  blob: Blob,
  root: ShadowRoot,
  isCancelled: () => boolean = () => false,
): Promise<void> => {
  // Plan FR-04: 별도 청크로 지연 로드 (docx-preview + jszip)
  const { renderAsync } = await import('docx-preview');
  if (isCancelled()) return;

  const reset = document.createElement('style');
  reset.textContent = HOST_RESET_CSS;
  const styles = document.createElement('div');
  const body = document.createElement('div');
  root.replaceChildren(reset, styles, body);

  await renderAsync(blob, body, styles, {
    inWrapper: true,
    breakPages: true,
    ignoreLastRenderedPageBreak: true,
    renderHeaders: true,
    renderFooters: true,
    renderFootnotes: true,
    renderEndnotes: true,
    // 내장 이미지는 data URL로 — blob URL 누수 방지 (Design §7)
    useBase64URL: true,
    // 보안·노출 최소화: 외부 HTML 조각·주석·변경 추적은 그리지 않는다
    renderAltChunks: false,
    renderComments: false,
    renderChanges: false,
    experimental: false,
  });
  if (isCancelled()) return;

  // Plan FR-09: 문서 안 링크는 새 창 + opener 차단, 위험한 스킴은 제거
  body.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href') ?? '';
    if (href.startsWith('#')) return; // 문서 내부 책갈피 — 아래 클릭 처리
    if (!SAFE_LINK.test(href)) {
      a.removeAttribute('href');
      return;
    }
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
  });

  // analysis G-02: 책갈피 대상 id는 shadow root 안에 있어 브라우저 해시 이동이 닿지 않는다.
  // 직접 스크롤하고 채팅 URL에 해시가 붙지 않게 막는다.
  body.addEventListener('click', (event) => {
    const anchor = (event.target as Element | null)?.closest?.('a[href^="#"]');
    if (!anchor) return;
    event.preventDefault();
    const id = decodeURIComponent((anchor.getAttribute('href') ?? '').slice(1));
    if (id) root.getElementById(id)?.scrollIntoView({ block: 'start' });
  });
};
