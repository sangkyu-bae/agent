# Design: doc-extractor-preview-highlight

> **Summary**: 문서추출기 미리보기 하이라이트 복구 + HTML 시각 충실도/스케일링 상세 설계 (Plan A안 확정)
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-03
> **Status**: Draft
> **Plan**: `docs/01-plan/features/doc-extractor-preview-highlight.plan.md`

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 미리보기 하이라이트가 `sample_value` 완전일치 실패로 전혀 표시되지 않고, MCP `pdf_to_html` text 모드 출력(그래픽 소실·고정 pt 크기)이 무스케일 iframe에서 깨져 보인다. |
| **Solution** | **A안(이원화)**: extract가 분석/skeleton용 text HTML + 미리보기 전용 layout HTML을 함께 반환. 어댑터에 `options`/`warnings` 지원을 추가하고, 프론트는 DOM 기반 정규화 매칭으로 하이라이트를 삽입하며 페이지 pt 크기를 감지해 iframe을 스케일한다. |
| **Function/UX Effect** | 업로드 직후 원본과 동일한 모습의 미리보기(배경 PNG) 위에 슬롯 하이라이트가 정확한 위치에 표시되고, 매칭 실패 슬롯은 확정 전에 안내된다. |
| **Core Value** | 기존 산출물 파이프라인(text skeleton, 5MiB 상한, GB6)을 그대로 유지하면서 미리보기 품질만 격상 — 변경 반경 최소화 + 신뢰성 회복. |

---

## 1. 아키텍처 개요

```
[빌드타임 extract — 변경]
업로드(PDF/DOCX)
  → MCP {fmt}_to_html (text/기본)  ──→ html          … LLM 슬롯 추출·토큰화·skeleton (기존 유지)
  → MCP pdf_to_html (options: layout) → preview_html … 미리보기 전용 (PDF만, 실패 시 None 폴백)
  → ExtractResponse { html, preview_html, suggested_slots, … }

[프론트 미리보기 — 변경]
previewHtml(없으면 html)
  → DOMParser 정규화 매칭으로 <mark data-slot="key"> 삽입
  → <style> 주입(mark 가시성 + 스케일 transform)
  → sandbox iframe srcDoc

[런타임 합성 — 소폭 변경(GB6 표식)]
skeleton(text) 치환 → html_to_{fmt} → 산출물 (기존 유지, 공란 표식만 강화)
```

레이어 배치: 변환 옵션은 infrastructure(adapter), 이원화 흐름은 application(use case), 매칭/스케일은 프론트 utils — 아키텍처 규칙(도메인 순수성) 변경 없음.

---

## 2. 확정 설계 결정 (D1~D9)

| # | 결정 | 근거 |
|---|------|------|
| **D1** | **이원화**: `html`(text, 분석·토큰화·skeleton용)은 기존 유지, `preview_html`(layout, 미리보기 전용)을 **PDF 원본에만** 추가. DOCX는 soffice 변환이 이미 충실 → `preview_html = null`, 프론트는 `html` 폴백 | 5MiB skeleton 상한·기존 산출물 경로 무변경. layout HTML은 저장/토큰화에 사용하지 않음 |
| **D2** | 어댑터 `to_html(..., options: dict \| None)` 추가 — payload `arguments.options`로 전달(평면 폴백 호출에도 포함). 응답 `metadata.warnings`를 `logger.warning`으로 기록 | MCP 실측 계약: `PdfToHtmlOptions{mode:"text"\|"layout", dpi:72~300}` / `ConvertResult.metadata.warnings` (`mcp-doc-convert-server/schemas/{options,io}.py`) |
| **D3** | layout 변환 실패는 **전체 extract를 실패시키지 않음** — `preview_html=None` + 경고 로그(우아한 성능 저하) | 미리보기 품질 문제로 핵심 기능(추출·확정)을 차단하지 않기 위함 |
| **D4** | 하이라이트/토큰화 매칭 = **DOMParser 기반 정규화 매칭**: 텍스트 노드 연결 문자열(공백 축약·엔티티는 DOM이 해소)에서 정규화된 `sample_value` 첫 출현을 찾아 노드 범위를 역산 → 미리보기는 `<mark>` 래핑, 토큰화는 범위 텍스트를 `{{key}}`로 치환 | PyMuPDF 출력의 span 분절·엔티티·공백 보존 문제를 근본 해결. 완전일치 `includes/replace` 제거 |
| **D5** | 미리보기 `<style>` 주입: `.pdf-page p mark, div[id^="page"] p mark { color:#111 !important; background:#FFF3B0 !important; border-radius:3px; }` | layout 모드 `.pdf-page span{color:transparent!important}`(specificity 0,1,1)를 이기는 0,1,2 셀렉터로 mark 텍스트 가시성 보장 |
| **D6** | iframe 스케일: HTML에서 첫 페이지 폭(`width:(\d+(\.\d+)?)pt`) 파싱 → px=pt×96/72 → `scale=min(1, containerWidth/px)` → 주입 CSS `body{transform:scale(S);transform-origin:top left;width:{px}px}`. 컨테이너 폭은 wrapper ref + `useLayoutEffect` + `window.resize` 리스너 | `sandbox=""`라 iframe 내부 JS 불가 → srcDoc 주입 CSS로 해결. ResizeObserver 회피(jsdom 테스트 폴리필 이슈 — CC 메모리 `reactflow-jsdom-test-gotchas`) |
| **D7** | sessionStorage 드래프트(R4)에서 `previewHtml` **제외** 저장 — 복원 시 `html` 폴백 미리보기 | layout HTML(페이지당 base64 PNG)이 sessionStorage 5MB 한계 초과 가능 |
| **D8** | GB6 공란 표식 강화: `render_unfilled` → `<mark data-unfilled="{key}" style="background:#FFF3B0">[미기재] {label}</mark>` — **텍스트 표식 `[미기재]` 병기** | `html_to_docx` 기본 엔진 htmldocx가 `<mark>` 스타일을 소실해도 텍스트 표식은 생존(FR-07 폴백). PDF(WeasyPrint)는 스타일 보존 |
| **D9** | config 추가: `document_extractor_preview_mode: str = "layout"`(`"off"`면 preview 변환 생략), `document_extractor_preview_dpi: int = 120` | 운영에서 크기/성능 조절 가능. 하드코딩 금지 규칙 준수 |

---

## 3. 백엔드 상세 설계 (idt)

### 3-1. `DocumentConversionAdapter` (infrastructure/document_extractor/document_conversion_adapter.py)

```python
async def to_html(self, file_bytes, source_format, mcp_tool_id, request_id,
                  options: dict | None = None) -> str:
```

- `_build_payload(b64, filename, options=None)`: `options`가 truthy면 `arguments["options"] = options`. 평면 폴백 재호출 시에도 유지.
- `_normalize_html` 경로에서 payload dict일 때 `metadata.warnings`(list[str])를 추출해 반환 값과 별도로 로깅:
  - 신규 내부 헬퍼 `_log_warnings(payload, mcp_tool_id, request_id)` — `self._logger.warning("MCP conversion warning", …, warning=w)` per item.
- 기존 시그니처 호출부(`composer.to_document`, 기존 `to_html` 호출)는 무변경 (기본값 None).

### 3-2. `ExtractDocumentUseCase` (application/document_extractor/extract_use_case.py)

```python
# 생성자 추가 인자
preview_mode: str = "layout"   # config.document_extractor_preview_mode
preview_dpi: int = 120         # config.document_extractor_preview_dpi
```

실행 흐름 (기존 흐름에 삽입):
1. (기존) text 변환 → `html` → sanitize → 슬롯 추출
2. (신규) `source_format == "pdf" and preview_mode == "layout"`이면:
   ```python
   try:
       raw_preview = await self._adapter.to_html(
           file_bytes, source_format, p2h, request_id,
           options={"mode": "layout", "dpi": self._preview_dpi},
       )
       preview_html = HtmlSanitizePolicy.clean(raw_preview)
   except McpConversionError as e:
       self._logger.warning("preview conversion failed, fallback to text html", …)
       preview_html = None
   ```
3. `ExtractResponse(preview_html=preview_html, …)`

주의: layout HTML의 `background-image:url(data:image/png;base64,…)`은 `HtmlSanitizePolicy` 위험 패턴(script/iframe/on*/javascript:)에 걸리지 않음 — 테스트로 고정.

### 3-3. 스키마 (application/document_extractor/schemas.py)

```python
class ExtractResponse(BaseModel):
    …
    # 미리보기 전용 layout HTML (PDF만, 실패/비활성 시 None) — 저장·토큰화에 사용 금지
    preview_html: str | None = None
```

라우터(`document_extractor_router.py`)는 응답 모델 그대로 통과 — 변경 없음(스키마 필드 추가만 반영).

### 3-4. config (src/config.py)

```python
document_extractor_preview_mode: str = "layout"   # layout | off
document_extractor_preview_dpi: int = 120
```

`main.py` DI 배선에서 use case 생성자에 전달. `.env.example`에 두 키 추가.

### 3-5. GB6 표식 (domain/document_extractor/policies.py)

```python
@staticmethod
def render_unfilled(slot: TemplateSlot) -> str:
    return (
        f'<mark data-unfilled="{slot.key}" '
        f'style="background:#FFF3B0">[미기재] {slot.label}</mark>'
    )
```

- `composer._replace_tokens`/`ComposeResult` 계약 무변경 (unfilled_labels 그대로).
- 기존 render_unfilled 테스트 기대값 갱신.

---

## 4. 프론트엔드 상세 설계 (idt_front)

### 4-1. 타입 (src/types/documentExtractor.ts)

```ts
export interface ExtractDocumentResponse {
  …
  preview_html: string | null;   // 백엔드 ExtractResponse.preview_html과 1:1
}
export interface DocumentExtractorDraft {
  …
  previewHtml?: string;          // 세션 복원 시 없을 수 있음 (D7)
}
```

### 4-2. 매칭/미리보기 유틸 (src/utils/documentTemplate.ts — 핵심 재설계)

신규 내부 모듈(같은 파일 내 함수군):

```ts
// ── DOM 텍스트 인덱스 (구현 확정 형태 — Check 단계 정합 갱신) ──
interface CharRef { node: Text; offset: number }   // 정규화 문자 ↔ (노드, 원본 오프셋)
interface TextIndex {
  normText: string;   // 텍스트 노드 연결 + 공백 축약 문자열
  chars: CharRef[];   // normText[i]에 대응하는 원본 위치
}
buildTextIndex(doc: Document): TextIndex

// ── 범위 탐색 ──
findRange(index: TextIndex, target: string): CharRef[] | null
// normalize(target)를 normText에서 indexOf → 매칭 문자들의 CharRef 배열 반환.
// groupSpans()로 노드별 연속 구간(NodeSpan)으로 그룹화해 래핑/치환에 사용.
```

**buildPreviewHtml(html, slots) → { html: string; missingSlotKeys: string[] }** (시그니처 변경)
1. `{{key}}` 토큰이 있으면(확정 skeleton) 토큰 텍스트 노드를 `<mark data-slot>라벨</mark>`로 치환 (기존 동작 유지, DOM 기반으로 통일)
2. 아니면 `findSlotRange`로 범위 탐색 → 걸친 각 텍스트 노드 구간을 `Range.surroundContents` 대신 **노드 분할 + `<mark data-slot="key">` 래핑**(여러 노드에 걸치면 노드별 mark — 시각적으로 연속)
3. `<head>`에 D5 스타일 + D6 스케일 스타일 삽입 (스케일 값은 파라미터 `scale`/`pageWidthPx`)
4. 매칭 실패 슬롯 key 목록 반환 → 패널이 안내 표시(FR-06)

**tokenizeHtml(html, slots) → TokenizeResult** (동작 재구현, 반환 타입 유지)
- 동일한 `findSlotRange` 사용. 매칭 성공 시: 첫 노드의 매칭 구간을 `{{key}}` 텍스트로 치환, 나머지 걸친 구간 텍스트 삭제 → `usedSlots`. 실패 → `missingSlots` (기존 계약 유지).
- 직렬화: `'<!DOCTYPE html>' + doc.documentElement.outerHTML`. 백엔드 `TemplateTokenPolicy`는 토큰 존재/미정의만 검증하므로 직렬화 차이는 무해. 단 **treatment 대상 html은 text 모드 HTML만**(previewHtml 아님).

**신규: extractPageWidthPt(html): number | null**
- `/(?:width\s*:\s*)(\d+(?:\.\d+)?)pt/` 첫 매치. 없으면 null(스케일 생략).

### 4-3. 패널 (src/components/agent-builder/DocumentExtractorConfigPanel.tsx)

- extract onSuccess: `previewHtml: response.preview_html ?? undefined` 저장.
- 미리보기 소스: `draft.confirmed ? draft.htmlSkeleton : (draft.previewHtml ?? draft.html)`.
- wrapper `div` ref로 컨테이너 폭 측정(`useLayoutEffect` + `resize` 리스너) → `scale` 계산 → `buildPreviewHtml` 호출에 전달 → `srcDoc` 갱신.
- `buildPreviewHtml`의 `missingSlotKeys`가 있으면 미확정 단계에도 안내: `"문서에서 위치를 찾지 못한 슬롯 N개: 라벨, …"` (amber notice 재사용).
- iframe `sandbox=""` 유지 (R7 2선 방어 불변).

### 4-4. 드래프트 저장 (src/utils/documentTemplate.ts `saveDraftToSession`)

```ts
const { previewHtml, ...persistable } = draft;   // D7: preview 제외
sessionStorage.setItem(KEY, JSON.stringify(persistable));
```

`LeftConfigPanel`의 복원 경로(R4)는 무변경 — previewHtml 부재 시 `html` 폴백이 자연 동작.

### 4-5. 서비스/훅

`documentExtractorService.ts`·`useDocumentExtractor.ts`는 타입만 전파(응답 필드 추가) — 로직 변경 없음. `/api-contract-sync` 체크리스트로 검증.

---

## 5. API 계약 변경 요약 (api-contract-sync 대상)

| 백엔드 | 프론트 | 변경 |
|--------|--------|------|
| `ExtractResponse.preview_html: str \| None` | `ExtractDocumentResponse.preview_html: string \| null` | 필드 추가 (하위호환 — 기존 클라이언트 무해) |
| (없음) | `DocumentExtractorDraft.previewHtml?: string` | 프론트 내부 상태 |

refine 계약 무변경 (text `html` 기준 유지).

---

## 6. 테스트 전략 (TDD — 테스트 먼저)

### 6-1. 백엔드 (pytest, Windows 격리 실행 주의 — CC 메모리 `backend-test-eventloop-flakiness`)

| 대상 | 케이스 |
|------|--------|
| adapter `_build_payload` | options 미지정 시 기존 payload 동일 / options 지정 시 `arguments.options` 포함 / 평면 폴백에도 options 유지 |
| adapter warnings | `metadata.warnings` 존재 시 logger.warning 호출 (mock logger) |
| extract use case | PDF: text+layout 2회 변환·`preview_html` 채움 / DOCX: layout 미호출·`preview_html=None` / layout 실패: `McpConversionError` 삼킴+None+경고 로그 / `preview_mode="off"`: 미호출 |
| sanitize | layout 샘플(base64 PNG data URL) 통과, script 제거는 기존과 동일 |
| GB6 표식 | `render_unfilled`가 `[미기재] {label}` 포함 (기존 테스트 갱신) |

### 6-2. 프론트 (vitest `--pool=threads` — CC 메모리 `frontend-vitest-forks-timeout`)

| 대상 | 케이스 |
|------|--------|
| `buildTextIndex`/`findSlotRange` | span 분절("500," + "000,000원") 매칭 / `&amp;` 등 엔티티 / `white-space:pre` 다중 공백 / 미존재 → null |
| `buildPreviewHtml` | mark 삽입(단일/다중 노드 걸침) / `{{key}}` 토큰 경로 / missingSlotKeys 반환 / D5 스타일·스케일 CSS 주입 |
| `tokenizeHtml` | 분절 샘플 토큰화 성공(기존 완전일치 실패 케이스가 통과로 전환) / usedSlots·missingSlots 계약 유지 |
| `extractPageWidthPt` | `width:612pt` 파싱 / 미존재 null |
| `saveDraftToSession` | previewHtml 제외 저장/복원 |
| Panel | preview_html 우선 사용 / 실패 슬롯 안내 노출 (노드 클릭 회피 — 콜백 단위 테스트) |

픽스처: PyMuPDF text 모드·layout 모드 축소 샘플 HTML을 `__tests__/fixtures`로 고정.

### 6-3. 실측 PoC — 완료 (2026-07-03, Do 단계)

| 항목 | 결과 |
|------|------|
| 문자열 완전일치 실패 원인 | **확증**: PyMuPDF가 모든 한글을 숫자 엔티티로 출력(`&#xae08;`=금). 단순 연속 값("금 500,000,000원")조차 원문/태그 제거/공백 축약 어떤 방식으로도 문자열 매칭 불가 → DOM 파싱(엔티티 해소) 필수 (D4 확정) |
| layout 모드 크기 | dpi 96: ~29KiB/page, **dpi 120: ~37KiB/page(기본값 채택)**, dpi 144: ~46KiB/page (단순 벡터 양식 기준) |
| `html_to_docx` mark 보존 | **하이라이트 스타일 소실**(htmldocx가 w:highlight/w:shd 미생성), **텍스트 `[미기재]`는 생존** → D8 텍스트 표식 병기 유효 |
| `html_to_pdf` (WeasyPrint) | 로컬 직접 임포트 환경에선 GTK 라이브러리 부재로 실행 불가 — **실서버(:8003) 실행 환경에서 별도 확인 필요** (잔여 확인 항목) |
| 라이브 서버(:8003) options 계약 | **layout 옵션 정상 수용** — `options={"mode":"layout","dpi":96}` 전달 시 engine이 `pymupdf-text`→`pymupdf-layout` 전환. 응답 HTML에 `.pdf-page span{color:transparent!important}` 실존 (D5 필요성 확증) |
| 라이브 서버 호출 형태 | **실서버는 `arguments` 래퍼를 거부**(pydantic `source Field required`)하고 평면 인자를 요구 → 어댑터의 평면 폴백이 프로덕션 주 경로. options가 폴백에서도 보존됨을 테스트로 고정(`test_flat_fallback_keeps_options`) |
| 응답 content 형태 | `output_mode="base64"`인데 content가 평문 HTML인 경우 실존 → 어댑터 `_maybe_b64_to_text` 관용 처리 유효 |

---

## 7. 구현 순서

1. **PoC** (§6-3 1·2) — layout 크기/mark 보존 실측 → dpi 기본값 확정
2. **백엔드**: adapter options/warnings (test→impl) → use case 이원화+config → 스키마/DI → GB6 표식
3. **`/api-contract-sync`**: 프론트 타입/서비스/훅 동기화
4. **프론트 유틸**: buildTextIndex/findSlotRange → buildPreviewHtml/tokenizeHtml 재구현 → 스케일 유틸 (test→impl)
5. **패널 배선**: previewHtml 사용·스케일·실패 슬롯 안내·세션 제외
6. **회귀**: 백엔드 pytest(격리) + 프론트 vitest(threads) + `/verify-architecture`

---

## 8. 영향 범위 / 리스크

| 항목 | 영향 | 대응 |
|------|------|------|
| `tokenizeHtml` 재구현 → skeleton 직렬화 차이 | 기존 저장 템플릿과 신규 skeleton 문자열 상이 가능 | 백엔드 검증은 토큰 정합만 보므로 무해. 기존 저장 템플릿은 불변(재확정 시에만 재생성) |
| layout HTML 응답 크기(수 MB) | 모달 로딩 지연 | dpi 기본 120 + PoC로 확정, `preview_mode=off` 운영 스위치 |
| DOM 정규화 매칭 오탐(동일 값 다중 출현) | 잘못된 위치 하이라이트 | 첫 출현 우선(기존 replace 의미 유지) + missing 안내로 사용자 검수 |
| `render_unfilled` 출력 변경 | 산출물 문구 변화(`[미기재]` 추가) | GB6 의도(사람이 채울 지점 명시)에 부합 — 테스트 기대값 갱신으로 명시화 |
| composer 등 기존 to_html 호출부 | 없음 (options 기본값 None) | 시그니처 하위호환 테스트 |

---

## 9. Next Steps

1. [ ] PoC 실측 (§6-3) — dpi/mark 보존 확정값 Design에 반영
2. [ ] `/pdca do doc-extractor-preview-highlight` — 구현 착수 (TDD)
3. [ ] 구현 완료 후 `/pdca analyze doc-extractor-preview-highlight`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-03 | Plan A안 기준 상세 설계 초안 (D1~D9 확정) | 배상규 |
| 0.2 | 2026-07-03 | Do 단계 PoC 실측 결과 반영 (§6-3) — dpi 120 확정, 평면 인자 계약, D4/D5/D8 확증 | 배상규 |
