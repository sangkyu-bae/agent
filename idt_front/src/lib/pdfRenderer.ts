// Design Ref: source-passage-viewer §5.3 — pdf.js 호출은 이 모듈 한 곳에만 둔다(docxRenderer 선례).
// jsdom 에서 렌더할 수 없으므로 컴포넌트 테스트는 이 모듈을 vi.mock 한다.
// pdfjs-dist·워커·텍스트 레이어 CSS 는 loadPdf 를 처음 부를 때 지연 로드된다.

export interface PdfDocument {
  numPages: number;
  /** 쪽 하나를 width(px)에 맞춰 container 끝에 그리고 텍스트 레이어 요소를 돌려준다. */
  renderPage: (pageNo: number, container: HTMLElement, width: number) => Promise<HTMLElement>;
  destroy: () => void;
}

const loadLibrary = async () => {
  const [pdfjs, worker] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
    import('./pdfTextLayer.css'),
  ]);
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  return pdfjs;
};

export const loadPdf = async (blob: Blob): Promise<PdfDocument> => {
  const pdfjs = await loadLibrary();
  const data = new Uint8Array(await blob.arrayBuffer());
  // 문서 안 스크립트(XFA·JS)는 실행하지 않는다 (Design §7)
  const task = pdfjs.getDocument({ data, enableXfa: false });
  const doc = await task.promise;

  const renderPage = async (pageNo: number, container: HTMLElement, width: number) => {
    const page = await doc.getPage(pageNo);
    const scale = width / page.getViewport({ scale: 1 }).width;
    const viewport = page.getViewport({ scale });
    const dpr = window.devicePixelRatio || 1;

    const wrapper = document.createElement('div');
    wrapper.className = 'spv-pdf-page';
    wrapper.dataset.page = String(pageNo);
    wrapper.setAttribute('aria-label', `${pageNo}쪽`);
    // 텍스트 레이어 크기 계산이 이 변수를 쓴다 (pdf.js setLayerDimensions)
    wrapper.style.setProperty('--total-scale-factor', String(scale));
    wrapper.style.width = `${viewport.width}px`;
    wrapper.style.height = `${viewport.height}px`;

    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(viewport.width * dpr);
    canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    const layer = document.createElement('div');
    layer.className = 'textLayer';
    wrapper.append(canvas, layer);
    container.appendChild(wrapper);

    const canvasContext = canvas.getContext('2d');
    if (!canvasContext) throw new Error('canvas 2d context unavailable');
    await page.render({
      canvas,
      canvasContext,
      viewport,
      transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0],
    }).promise;
    const textLayer = new pdfjs.TextLayer({
      textContentSource: page.streamTextContent(),
      container: layer,
      viewport,
    });
    await textLayer.render();
    return layer;
  };

  // pdf.js 6: 문서·워커 정리는 loading task 가 맡는다
  return { numPages: doc.numPages, renderPage, destroy: () => void task.destroy() };
};
