// document-template-extractor D2 + doc-extractor-preview-highlight D4~D7.
// MCP pdf_to_html 출력(한글 숫자 엔티티·span 분절·white-space:pre 공백 보존 — PoC
// 실측)은 문자열 완전일치가 항상 실패하므로, DOMParser로 엔티티를 해소한 뒤
// 텍스트 노드 연결 문자열을 정규화(공백 축약)해 매칭한다.
// 백엔드 TemplateTokenPolicy가 저장 직전 토큰 정합을 재검증한다.
import type {
  DocumentExtractorDraft,
  DocumentTemplateRequest,
  TemplateSlot,
} from '@/types/documentExtractor';

export interface TokenizeResult {
  htmlSkeleton: string;
  usedSlots: TemplateSlot[];
  // sample_value가 비었거나 본문에서 찾지 못해 제외된 슬롯 (사용자 안내용)
  missingSlots: TemplateSlot[];
}

export interface PreviewBuildResult {
  html: string;
  // 하이라이트 위치를 찾지 못한 슬롯 key (FR-06 — 확정 전 사용자 안내)
  missingSlotKeys: string[];
}

export interface PreviewOptions {
  // 컨테이너 폭 대비 축소 배율 (< 1일 때만 transform 주입, D6)
  scale?: number;
  // 스케일 시 body 자연 폭(px) — 고정 pt 페이지 기준
  pageWidthPx?: number;
}

const MARK_STYLE = 'background:#FFF3B0;border-radius:3px;padding:0 2px';

// ── DOM 텍스트 인덱스: 정규화 문자 ↔ (텍스트 노드, 원본 오프셋) 매핑 ──
interface CharRef {
  node: Text;
  offset: number;
}

interface TextIndex {
  normText: string;
  chars: CharRef[];
}

interface NodeSpan {
  node: Text;
  start: number;
  end: number; // exclusive
}

const isFullDocument = (html: string): boolean => /<html[\s>]/i.test(html);

const parseDoc = (html: string): Document =>
  new DOMParser().parseFromString(html, 'text/html');

const serializeDoc = (doc: Document, fullDoc: boolean): string =>
  fullDoc
    ? `<!DOCTYPE html>\n${doc.documentElement.outerHTML}`
    : doc.body.innerHTML;

const buildTextIndex = (doc: Document): TextIndex => {
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  let normText = '';
  const chars: CharRef[] = [];
  let lastWasSpace = true;
  let node = walker.nextNode();
  while (node) {
    const text = node as Text;
    const data = text.data;
    for (let i = 0; i < data.length; i += 1) {
      if (/\s/.test(data[i])) {
        if (!lastWasSpace) {
          normText += ' ';
          chars.push({ node: text, offset: i });
          lastWasSpace = true;
        }
      } else {
        normText += data[i];
        chars.push({ node: text, offset: i });
        lastWasSpace = false;
      }
    }
    node = walker.nextNode();
  }
  return { normText, chars };
};

const findRange = (index: TextIndex, target: string): CharRef[] | null => {
  const normalized = target.normalize('NFC').replace(/\s+/g, ' ').trim();
  if (!normalized) return null;
  const at = index.normText.indexOf(normalized);
  if (at === -1) return null;
  return index.chars.slice(at, at + normalized.length);
};

// 매칭 문자들을 노드별 연속 구간으로 그룹화
const groupSpans = (refs: CharRef[]): NodeSpan[] => {
  const spans: NodeSpan[] = [];
  for (const ref of refs) {
    const last = spans[spans.length - 1];
    if (last && last.node === ref.node && ref.offset >= last.end - 1) {
      last.end = ref.offset + 1;
    } else {
      spans.push({ node: ref.node, start: ref.offset, end: ref.offset + 1 });
    }
  }
  return spans;
};

const wrapSpanWithMark = (
  doc: Document,
  span: NodeSpan,
  slotKey: string,
): HTMLElement => {
  const middle = span.node.splitText(span.start);
  middle.splitText(span.end - span.start);
  const mark = doc.createElement('mark');
  mark.setAttribute('data-slot', slotKey);
  mark.setAttribute('style', MARK_STYLE);
  middle.parentNode?.replaceChild(mark, middle);
  mark.appendChild(middle);
  return mark;
};

// 뒤 구간부터 처리해야 같은 노드 내 앞 구간 오프셋이 안 흔들린다.
const highlightSpans = (
  doc: Document,
  spans: NodeSpan[],
  slotKey: string,
): void => {
  for (const span of [...spans].reverse()) {
    wrapSpanWithMark(doc, span, slotKey);
  }
};

const replaceSpansWithText = (spans: NodeSpan[], text: string): void => {
  const [first, ...rest] = spans;
  for (const span of [...rest].reverse()) {
    const d = span.node.data;
    span.node.data = d.slice(0, span.start) + d.slice(span.end);
  }
  const d = first.node.data;
  first.node.data = d.slice(0, first.start) + text + d.slice(first.end);
};

/** 확정 시점 토큰화: sample_value 첫 출현(정규화 매칭)을 {{key}}로 치환. */
export const tokenizeHtml = (
  html: string,
  slots: TemplateSlot[],
): TokenizeResult => {
  const fullDoc = isFullDocument(html);
  const doc = parseDoc(html);
  const usedSlots: TemplateSlot[] = [];
  const missingSlots: TemplateSlot[] = [];

  for (const slot of slots) {
    // 매 슬롯 재인덱싱: 직전 치환으로 노드/오프셋이 변하기 때문 (슬롯 ≤ 30)
    const refs = slot.sample_value
      ? findRange(buildTextIndex(doc), slot.sample_value)
      : null;
    if (!refs) {
      missingSlots.push(slot);
      continue;
    }
    replaceSpansWithText(groupSpans(refs), `{{${slot.key}}}`);
    usedSlots.push(slot);
  }
  return {
    htmlSkeleton: usedSlots.length > 0 ? serializeDoc(doc, fullDoc) : html,
    usedSlots,
    missingSlots,
  };
};

// D5(mark 가시성) + D6(스케일) 스타일 주입.
// layout 모드의 `.pdf-page span{color:transparent!important}`(0,1,1)보다
// 높은 특이도(0,1,2) 셀렉터로 mark 텍스트를 복원한다.
const injectPreviewStyle = (doc: Document, options: PreviewOptions): void => {
  let css =
    '.pdf-page p mark, div[id^="page"] p mark, mark[data-slot] {\n' +
    '  color: #111 !important; background: #FFF3B0 !important;\n' +
    '  border-radius: 3px; padding: 0 2px;\n' +
    '}';
  if (options.scale !== undefined && options.scale < 1) {
    const width =
      options.pageWidthPx !== undefined
        ? ` width: ${options.pageWidthPx}px;`
        : '';
    css +=
      `\nbody { transform: scale(${options.scale});` +
      ` transform-origin: top left;${width} }`;
  }
  const style = doc.createElement('style');
  style.textContent = css;
  doc.head.appendChild(style);
};

/** 미리보기용: 슬롯 지점 하이라이트 + 가시성/스케일 CSS 주입 (sandbox iframe srcDoc). */
export const buildPreviewHtml = (
  html: string,
  slots: TemplateSlot[],
  options: PreviewOptions = {},
): PreviewBuildResult => {
  const doc = parseDoc(html);
  const missingSlotKeys: string[] = [];

  for (const slot of slots) {
    const index = buildTextIndex(doc);
    // 확정 skeleton 경로: {{key}} 토큰 → 라벨 mark
    const tokenRefs = findRange(index, `{{${slot.key}}}`);
    if (tokenRefs) {
      const spans = groupSpans(tokenRefs);
      const mark = wrapSpanWithMark(doc, spans[0], slot.key);
      mark.textContent = slot.label;
      for (const span of spans.slice(1).reverse()) {
        const d = span.node.data;
        span.node.data = d.slice(0, span.start) + d.slice(span.end);
      }
      continue;
    }
    // 미확정 경로: sample_value 위치 하이라이트 (원문 유지)
    const refs = slot.sample_value
      ? findRange(index, slot.sample_value)
      : null;
    if (!refs) {
      missingSlotKeys.push(slot.key);
      continue;
    }
    highlightSpans(doc, groupSpans(refs), slot.key);
  }
  injectPreviewStyle(doc, options);
  // srcDoc 전용이므로 주입 스타일(head) 포함 전체 문서로 직렬화
  return { html: serializeDoc(doc, true), missingSlotKeys };
};

/** PyMuPDF 페이지 div의 고정 pt 폭 파싱 (D6 스케일 계산용). */
export const extractPageWidthPt = (html: string): number | null => {
  const match = /width\s*:\s*(\d+(?:\.\d+)?)pt/.exec(html);
  return match ? Number(match[1]) : null;
};

// pt → px (CSS 기준 1pt = 96/72px)
export const ptToPx = (pt: number): number => (pt * 96) / 72;

// 백엔드 SLOT_KEY_PATTERN(^[a-z][a-z0-9_]{0,49}$)에 맞는 수동 슬롯 key 생성.
export const generateSlotKey = (existingKeys: string[]): string => {
  const used = new Set(existingKeys);
  for (let i = 1; i <= 999; i += 1) {
    const key = `custom_${i}`;
    if (!used.has(key)) return key;
  }
  return `custom_${existingKeys.length + 1}`;
};

// ── R4: 추출 드래프트 sessionStorage 보존 (새로고침/이탈 유실 방어) ──
export const DRAFT_STORAGE_KEY = 'agent-builder:doc-extractor-draft';

export const saveDraftToSession = (
  draft: DocumentExtractorDraft | null,
): void => {
  try {
    if (draft) {
      // D7: layout previewHtml(페이지당 base64 PNG)은 5MB 한계 초과 위험 — 제외
      const { previewHtml: _previewHtml, ...persistable } = draft;
      sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(persistable));
    } else {
      sessionStorage.removeItem(DRAFT_STORAGE_KEY);
    }
  } catch {
    // sessionStorage 비활성(프라이빗 모드 등) — 드래프트 보존만 생략, 기능 지속.
  }
};

export const loadDraftFromSession = (): DocumentExtractorDraft | null => {
  try {
    const raw = sessionStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as DocumentExtractorDraft) : null;
  } catch {
    return null;
  }
};

/** 확정 드래프트 → 생성/수정 payload (미확정이면 undefined). */
export const buildDocumentTemplateRequest = (
  draft: DocumentExtractorDraft | null | undefined,
  fallbackName: string,
): DocumentTemplateRequest | undefined => {
  if (!draft || !draft.confirmed || draft.slots.length === 0) return undefined;
  return {
    name: draft.templateName || fallbackName,
    html_skeleton: draft.htmlSkeleton,
    slots: draft.slots,
    source_file_id: draft.sourceFileId,
    source_format: draft.sourceFormat,
    mcp_pdf_to_html_tool_id: draft.mcpPdfToHtmlToolId,
    mcp_html_to_doc_tool_id: draft.mcpHtmlToDocToolId,
  };
};
