# Plan: doc-extractor-preview-highlight

> **Summary**: 문서추출기 양식 등록 시 (1) 미리보기 하이라이트 미표시, (2) HTML 미리보기 크기 깨짐 문제의 원인 진단 및 수정 계획
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-03
> **Status**: Draft
> **Related**: `docs/archive/2026-07/document-template-extractor/` (원 기능 PDCA), CC 메모리 `mcp-session-terminated-means-404`

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 문서추출기(document_extractor)로 PDF 양식을 올리면 **슬롯 자동 추출은 성공**하지만, 미리보기에서 **하이라이트(자동화 슬롯 표시)가 나타나지 않고**, **HTML 미리보기의 크기/레이아웃이 깨져 보인다**. |
| **Solution** | 원인은 MCP 장애가 아니라 **MCP `pdf_to_html` 도구의 기본 `text` 모드 출력 특성(절대좌표·그래픽 소실·텍스트 분절)과, 이를 전제하지 않은 앱 코드(어댑터 options 미전달 + 프론트 완전일치 하이라이트 매칭 + 무스케일 iframe)의 불일치**. ① 어댑터에 변환 options/warnings 지원, ② 미리보기용 layout 모드(배경 PNG) 도입 + iframe 스케일링, ③ 하이라이트 매칭을 정규화(DOM 기반) 방식으로 강화한다. |
| **Function/UX Effect** | 업로드 직후 미리보기가 원본과 동일한 모습(표·괘선·배경 포함)으로 뜨고, 추천 슬롯 위치가 노란 하이라이트로 정확히 표시된다. 하이라이트에 실패한 슬롯은 확정 전에 사용자에게 안내된다. |
| **Core Value** | 휴먼인더룹 확정(GA3)의 핵심 근거인 "미리보기 + 하이라이트"가 실제로 동작해야 사용자가 슬롯을 신뢰하고 확정할 수 있다. 금융 양식 자동화의 UX 신뢰성 회복. |

---

## 0. 진단 결론 — "MCP 문제인가?"

**MCP 서버 장애/연결 문제는 아니다.** 추출(업로드→변환→슬롯 추천)이 성공하고 있다는 것 자체가 MCP 호출 경로(`Doc Convert MCP`, `localhost:8003/sse`, id `6dd5c675-…`)가 정상이라는 증거다.

다만 **근본 원인의 절반은 MCP 도구의 "출력 특성"에 있다**:

| 구분 | 판정 | 상세 |
|------|------|------|
| MCP 연결/호출 | ✅ 정상 | extract 성공, 도구 선택(`pdf_to_html`)·응답 정규화 모두 동작 |
| MCP 도구 출력 특성 | ⚠️ 원인 제공 | `pdf_to_html` 기본 `text` 모드 = PyMuPDF `get_text("html")` — 절대좌표 텍스트만 추출, **표·괘선·배경 그래픽 소실**, 페이지 pt 고정 크기. 서버 스스로 "시각 충실도가 필요하면 `options.mode='layout'`"이라고 **경고를 반환**하지만 idt는 이를 사용/표시하지 않음 |
| idt 백엔드 어댑터 | ❌ 결함 | `options` 미전달(모드 선택 불가) + 응답 `warnings` 폐기 (`document_conversion_adapter.py:124-131`) |
| idt_front 하이라이트 | ❌ 결함 | `sample_value` **문자열 완전일치** 전제 — PyMuPDF 분절 출력과 불일치 → 조용히 스킵 (`documentTemplate.ts:38-56`) |
| idt_front 미리보기 | ❌ 결함 | 고정 pt 페이지를 45vh iframe에 무스케일 주입 → 잘리고 겹쳐 보임 (`DocumentExtractorConfigPanel.tsx:257-265`) |

즉, **"MCP가 고장난 것"이 아니라 "MCP 도구가 내주는 HTML의 형태를 앱(백엔드 어댑터 + 프론트)이 감안하지 않은 것"**이 문제다. 수정 대상은 주로 idt/idt_front이며, MCP 서버는 이미 해법(`layout` 모드)을 제공하고 있어 옵션 전달만 하면 된다.

---

## 1. 배경 / 증상

### 1-1. 재현 흐름
1. 에이전트 빌더 → 문서추출기 → PDF 양식 업로드
2. MCP `pdf_to_html` 변환 → LLM 슬롯 추천 → **슬롯 목록은 정상 표시** (자동화 추출 OK)
3. **증상 A**: 미리보기 iframe에 하이라이트(`<mark>` 노란 배경)가 하나도 표시되지 않음
4. **증상 B**: 미리보기 HTML이 원본과 달리 크기가 깨져 보임 — 텍스트가 겹치거나 페이지가 잘리고, 표/괘선이 사라짐

### 1-2. 관련 시스템 구성 (실측)
- 변환 MCP: **Doc Convert MCP** (`mcp_server_registry` id `6dd5c675-dae8-454d-9cc0-7e8c71f46977`, `http://localhost:8003/sse`, 소스: `C:\sangplus\mcp\mcp-doc-convert-server`)
- 도구: `pdf_to_html`(PyMuPDF), `docx_to_html`(soffice), `html_to_pdf`(WeasyPrint), `html_to_docx`(htmldocx/pandoc)
- `.env`: `DOCUMENT_EXTRACTOR_PDF_TO_HTML_TOOL_ID` / `HTML_TO_DOC_TOOL_ID` 설정 완료 (G3 잔여 항목 해소됨)

---

## 2. 원인 분석 (증거 기반)

### 2-1. 증상 A — 하이라이트 미표시

**직접 원인: 프론트의 `sample_value` 문자열 완전일치 매칭 실패 (조용한 스킵).**

- `idt_front/src/utils/documentTemplate.ts:38-56` `buildPreviewHtml`:
  - 미확정 드래프트는 `{{key}}` 토큰이 없으므로 `preview.includes(slot.sample_value)` 분기로만 하이라이트.
  - 매칭 실패 시 **아무 표식 없이 스킵** — 사용자에게 피드백 없음.
- `idt_front/src/utils/documentTemplate.ts:17-35` `tokenizeHtml`(확정 토큰화)도 동일한 완전일치 `includes/replace` 전제 → 하이라이트가 안 되는 슬롯은 확정 시에도 `missingSlots`로 전부 탈락한다.

**매칭이 실패하는 이유: MCP `pdf_to_html`(text 모드) 출력 형태.**

- `mcp-doc-convert-server/converters/pdf_html.py:66` — `page.get_text("html")` 출력은:
  - 같은 줄 텍스트도 **폰트 런 단위 `<span>`으로 분절** (예: "여신금액 500,000,000원"이 여러 span으로 쪼개짐)
  - `&`, `<`, `>` 등 **HTML 엔티티 이스케이프** + `white-space: pre` 공백 보존 (`pdf_html.py:21`)
  - 반면 LLM(`slot_extractor.py`)이 돌려주는 `sample_value`는 태그를 제거하고 공백을 정규화한 **평문** → 원문 HTML에 문자 그대로 존재하지 않는 경우가 대부분
- 결과: `includes()` 항상 false → mark 미삽입 → **하이라이트 0개**.

### 2-2. 증상 B — HTML 크기 깨짐

**직접 원인: text 모드 출력(고정 pt·절대좌표·그래픽 소실)을 무스케일 iframe에 그대로 렌더.**

- `pdf_html.py:16-23` — text 모드는 `<div id="pageN" style="width:612pt;height:792pt">` + `position:absolute` `<p>`들. **표·괘선·배경·체크박스 등 그래픽은 전부 소실**되고 떠 있는 텍스트만 남는다.
- MCP 서버 자체 경고(`pdf_html.py:7-10`): *"PDF->HTML는 텍스트 추출 중심입니다. 복잡한 레이아웃·표·이미지는 손실될 수 있습니다. 시각 충실도가 필요하면 options.mode='layout'을 사용하세요."* — **이 경고가 idt에서 버려진다.**
- `idt/src/infrastructure/document_extractor/document_conversion_adapter.py:124-131` `_build_payload` — `source`/`output`만 보내고 **`options`를 전달하지 않음** → 항상 기본 text 모드. `_normalize_html`도 `warnings`/`metadata`를 폐기.
- `idt_front/.../DocumentExtractorConfigPanel.tsx:257-265` — `sandbox=""` iframe, `h-[45vh] w-full` 고정, **스케일링/viewport 처리 없음** → A4(612×792pt ≈ 816×1056px) 고정 페이지가 잘리고, 절대좌표 텍스트가 겹쳐 보임.
- 참고: **DOCX 원본은 `docx_to_html`(soffice) 경로라 충실도가 상대적으로 양호** — 증상은 주로 PDF 원본에서 발생.

### 2-3. 부수 발견 (런타임 GB6 하이라이트 소실 위험 — 이번 스코프에서 검증)

- 산출물 공란 하이라이트(`policies.py:147-152` `<mark data-unfilled …>`)는 `html_to_docx`의 기본 엔진 **htmldocx가 `<mark>`/배경 스타일을 사실상 무시**해 DOCX 산출물에서 소실될 수 있다 (`mcp-doc-convert-server/converters/html_docx.py:6-26`). PDF(WeasyPrint)는 인라인 배경을 보존.
- text 모드 skeleton(절대좌표 + `white-space:pre`)에 샘플보다 **긴 값을 치환하면 텍스트 겹침** 발생 가능 — 산출물 품질에도 동일 뿌리의 문제가 잠재.

### 2-4. layout 모드 도입 시 주의점 (설계 반영 필수)

- `pdf_html.py:27-33` layout 모드 CSS: `.pdf-page span { color: transparent !important }` — 텍스트 레이어가 투명(배경 PNG가 시각 담당). **하이라이트 `<mark>` 안 라벨 텍스트도 투명해지므로** 미리보기 CSS에서 mark 색상을 강제 복원해야 한다.
- layout 모드는 페이지당 배경 PNG(base64) 포함 → 출력이 커진다(서버 경고 `_LAYOUT_SIZE_WARNING`). `MAX_SKELETON_BYTES`(5MiB, `policies.py:29`) 초과 위험 → **layout HTML은 "미리보기 전용"으로 쓰고, 토큰화/skeleton 저장은 기존 text HTML 유지**하는 이원화가 필요(아래 FR-02).

---

## 3. 목표 / 비목표

### 3-1. 목표
- **G1.** 미리보기에서 추천 슬롯 하이라이트가 실제 문서 텍스트 위치에 표시된다 (PDF/DOCX 공통).
- **G2.** 미리보기가 원본에 가까운 시각 충실도(표·괘선·배경 포함)로, iframe 크기에 맞게 스케일되어 보인다.
- **G3.** 하이라이트에 실패한 슬롯은 확정 전 미리보기 단계에서 사용자에게 안내된다.
- **G4.** idt 어댑터가 MCP 변환 `options`를 전달하고 `warnings`를 로깅한다 (실측 계약 보강).
- **G5.** 산출물(GB6 공란 하이라이트)이 PDF/DOCX 양쪽에서 보존되는지 검증하고, 소실 시 보완책을 확정한다.

### 3-2. 비목표
- **N1.** MCP doc-convert 서버 자체의 전면 개편 (옵션 전달로 해결 가능한 범위만 사용; 단 G5 검증 결과에 따라 서버 측 소규모 보완은 후속 결정).
- **N2.** OCR/스캔 이미지 지원, 다중 템플릿, 템플릿 공유 (원 Plan 비목표 유지).
- **N3.** 하이라이트 편집(드래그로 슬롯 영역 지정) 등 신규 UX — 이번엔 표시 복구만.

---

## 4. 요구사항

### 4-1. 기능 요구사항

| ID | 요구사항 | 우선순위 | 대상 |
|----|----------|----------|------|
| FR-01 | `DocumentConversionAdapter._build_payload`에 `options` 전달 지원(`pdf_to_html`: `mode`/`dpi`) + 응답 `warnings` 로깅. 모드는 config(`document_extractor_pdf_to_html_mode`, 기본 `layout` 미리보기용)로 제어 | High | idt |
| FR-02 | extract 응답 이원화: **미리보기용 HTML(layout, 시각 충실)** + **토큰화/skeleton용 HTML(text, 경량)** 분리 제공. skeleton 5MiB 상한(`MAX_SKELETON_BYTES`) 준수 | High | idt + idt_front |
| FR-03 | 프론트 하이라이트 매칭 강화: 완전일치 → **DOMParser 기반 텍스트 노드 정규화 매칭**(엔티티 디코드·공백 축약·span 경계 허용). `buildPreviewHtml`·`tokenizeHtml` 공통 적용 | High | idt_front |
| FR-04 | layout 모드 미리보기에서 `<mark>` 가시성 CSS 강제(`color` 복원, z-index) — 투명 텍스트 레이어 대응 | High | idt_front |
| FR-05 | 미리보기 iframe 스케일링: 페이지 고정 크기(pt) 감지 → `transform: scale()` 또는 주입 CSS로 iframe 폭에 맞춤 | High | idt_front |
| FR-06 | 하이라이트 실패 슬롯 피드백: 미확정 단계에서도 "문서에서 위치를 찾지 못한 슬롯 N개: …" 안내 표시 | Medium | idt_front |
| FR-07 | GB6 산출물 하이라이트 보존 검증: `html_to_pdf`/`html_to_docx` 실변환 PoC로 `<mark>` 보존 확인. DOCX 소실 시 텍스트 표식 병기(예: `[미기재: 라벨]`) 폴백 | Medium | idt (+MCP PoC) |

### 4-2. 비기능 요구사항

| 항목 | 기준 | 측정 |
|------|------|------|
| 성능 | layout 모드 미리보기 HTML ≤ 수 MB(페이지당 PNG, dpi 조절) — 모달 렌더 지연 체감 없음 | dpi 96~144 실측 비교 |
| 보안 | 기존 `HtmlSanitizePolicy`(1선) + sandbox iframe(2선) 유지 — layout PNG data URL은 통과 확인 | 단위 테스트 |
| 호환 | DOCX 원본(soffice 경로) 기존 동작 회귀 없음 | 기존 테스트 그린 |

---

## 5. 해결 방안 옵션 (Design에서 확정)

| 옵션 | 내용 | 장점 | 단점 | 권장 |
|------|------|------|------|:----:|
| **A. 이원화(미리보기=layout, skeleton=text)** | extract 시 layout HTML을 추가 확보해 미리보기 전용으로 사용, 토큰화·저장·산출물은 기존 text HTML 유지 | 시각 충실도+하이라이트+기존 산출물 파이프라인 무변경 | MCP 변환 1회 추가(또는 서버에 dual 출력 옵션 추가), 응답 크기 증가 | ✅ |
| B. 프론트만 수정(스케일+정규화 매칭) | MCP 추가 호출 없이 text HTML 스케일링과 매칭 개선만 | 변경 범위 최소 | 표·괘선 소실은 그대로 — "크기 깨짐" 체감 절반만 해소 | |
| C. 서버 text 모드 개선 | PyMuPDF text 모드 출력을 서버에서 후처리(그래픽 벡터 포함) | 근본 해결 | MCP 서버 대규모 수정 — 비목표(N1)와 충돌 | |

※ A안에서도 FR-03(정규화 매칭)은 필수 — layout 모드도 텍스트 레이어는 동일하게 분절되어 있다.

---

## 6. 리스크

| 리스크 | 영향 | 가능성 | 완화 |
|--------|------|--------|------|
| layout HTML 대용량(base64 PNG)으로 응답/모달 지연 | Medium | Medium | dpi 기본 96~120, 페이지 수 상한, `output.mode=path` 검토 |
| 정규화 매칭의 오탐(동일 텍스트 다중 출현 시 엉뚱한 위치 하이라이트) | Medium | Medium | 첫 출현 우선 + 슬롯별 매칭 위치 로그, 실패 슬롯 안내(FR-06) |
| htmldocx `<mark>` 미지원 확정 시 DOCX 하이라이트 부재 | Medium | High | FR-07 폴백(텍스트 표식) 또는 MCP pandoc 엔진 옵션 사용 |
| 절대좌표 skeleton에 긴 값 치환 시 산출물 텍스트 겹침 | Medium | Medium | 이번 스코프에선 검증·기록만, 심하면 후속 Plan 분리 |

---

## 7. 성공 기준 (Definition of Done)

- [ ] PDF 양식 업로드 → 미리보기에 추천 슬롯 하이라이트가 원문 위치에 표시 (실문서 3종 실측)
- [ ] 미리보기가 iframe 폭에 맞게 스케일되어 표·괘선 포함 원본과 유사하게 보임
- [ ] 하이라이트 실패 슬롯이 미확정 단계에서 안내됨
- [ ] 어댑터 options/warnings 단위 테스트 + 기존 백엔드/프론트 테스트 그린 (TDD: 테스트 먼저)
- [ ] GB6 산출물 하이라이트 PDF/DOCX 실변환 PoC 결과 기록
- [ ] `/api-contract-sync`로 extract 응답 스키마 변경분 프론트 타입 동기화

---

## 8. Next Steps

1. [ ] `/pdca design doc-extractor-preview-highlight` — A안 기준 상세 설계 (extract 응답 스키마, 정규화 매칭 알고리즘, 스케일링 방식 확정)
2. [ ] MCP `pdf_to_html` layout 모드 실변환 PoC (dpi별 크기/렌더 확인)
3. [ ] 구현(Do) → Gap 분석(Check)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-03 | 원인 진단(코드+MCP 서버 소스+DB 실측) 및 초안 작성 | 배상규 |
