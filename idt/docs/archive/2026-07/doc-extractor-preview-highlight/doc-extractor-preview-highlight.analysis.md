# Gap Analysis: doc-extractor-preview-highlight

> **Phase**: Check
> **Date**: 2026-07-03
> **Analyzer**: gap-detector (bkit)
> **Design**: `docs/02-design/features/doc-extractor-preview-highlight.design.md`
> **Plan**: `docs/01-plan/features/doc-extractor-preview-highlight.plan.md`

---

## Match Rate: 96% ✅

9개 확정 결정(D1~D9) 전부 구현·테스트 완료, FR-01~06 전부 커버. Gap은 전부 Low(명명/내부구조 표기 차이) 수준이며 기능 결손·스코프 초과 없음. FR-07 잔여 확인은 **본 Check 단계에서 실측으로 종결**(§4).

| Category | Score | Status |
|----------|:-----:|:------:|
| Design 결정(D1~D9) 일치 | 100% | ✅ |
| §3 백엔드 상세 일치 | 97% | ✅ |
| §4 프론트 상세 일치 | 93% → 100% (문서 정합 갱신 완료) | ✅ |
| §6 테스트 전략 커버 | 100% | ✅ |
| Plan FR 커버리지 | 96% | ✅ |
| **Overall** | **96%** | ✅ |

---

## 1. 결정별 판정 (D1~D9)

| # | 결정 | 판정 | 근거 |
|---|------|:----:|------|
| D1 | 이원화(html+preview_html, PDF만, DOCX null 폴백) | Full | `extract_use_case.py` `_maybe_preview_html`; `schemas.py` preview_html; 패널 `previewHtml ?? html` |
| D2 | adapter options 전달 + metadata.warnings 로깅 | Full | `document_conversion_adapter.py` `to_html(...,options)`, `_build_payload`, `_log_warnings` |
| D3 | layout 실패 시 None 폴백(전체 실패 안 함) | Full | `McpConversionError` catch → None + warning 로그 |
| D4 | DOMParser 정규화 매칭 | Full | `documentTemplate.ts` buildTextIndex/findRange/groupSpans |
| D5 | mark 가시성 style 주입(특이도 0,1,2) | Full | `injectPreviewStyle` — `.pdf-page p mark …` color:#111!important |
| D6 | iframe 스케일(pt 파싱→min(1,…)→transform) | Full | `extractPageWidthPt`/`ptToPx` + 패널 useLayoutEffect/resize |
| D7 | sessionStorage previewHtml 제외 | Full | `saveDraftToSession` 구조분해 제외 |
| D8 | render_unfilled `[미기재]` 병기 | Full | `policies.py` + PoC(htmldocx 스타일 소실·텍스트 생존) |
| D9 | config preview_mode/preview_dpi | Full | `config.py`, `.env.example`, `main.py` DI |

## 2. Gap 목록 (전부 Low — 조치 완료/불요)

| 항목 | 설계 | 구현 | 조치 |
|------|------|------|------|
| 함수명 `findSlotRange` → `findRange`, TextIndex 내부 구조 | §4-2 초안 표기 | 동작 동일, 명명 상이 | **Design §4-2를 구현 확정 형태로 갱신 완료** (v0.3) |
| tokenize 직렬화 | DOCTYPE+outerHTML 고정 | fragment는 body.innerHTML 조건 분기 | 개선으로 판정 — 기존 skeleton 계약(토큰 정합) 무영향 |
| warnings 추출 위치 | `_normalize_html` 내부 | 별도 헬퍼 `_log_warnings` | 관심사 분리 개선 — 유지 |
| D5 셀렉터 `mark[data-slot]`·padding 추가 | 미명시 | 폴백 미리보기 가시성 보강 | 의도 부합 — 유지 |

## 3. 테스트 커버리지

- 백엔드: `TestOptionsAndWarnings` 5, `TestPreviewHtml` 5, GB6 표식 1 (신규 11) — document_extractor 관련 117건 그린
- 프론트: 엔티티/분절/공백 매칭, 스케일, D7 제외, FR-06 안내 등 신규 15건+ — agent-builder 영역 161건 그린, `tsc --noEmit` 통과

## 4. FR-07 잔여 확인 — 실측 종결 (2026-07-03, 실서버 :8003)

| 확인 항목 | 결과 |
|-----------|------|
| `html_to_pdf`(WeasyPrint) 서버 동작 | ✅ 정상 (로컬 GTK 이슈는 서버 환경과 무관) |
| PDF에서 `<mark>` 하이라이트 배경 보존 | ✅ **보존** — 페이지 드로잉에 fill `#FFF3B0`(1.0, 0.953, 0.690) 실측 |
| DOCX에서 `[미기재]` 텍스트 표식 보존 | ✅ 보존 (스타일은 소실 — D8로 완화) |

## 5. ⚠️ 신규 발견 (본 기능 범위 밖 — 별도 후속 필요)

**Doc Convert MCP `html_to_pdf`(WeasyPrint)가 한글을 렌더링하지 못함.**

- 실측: `"한글확인 [미기재] 심사의견"` → PDF 텍스트가 전부 동일 글리프 `"견견견견 [견견견] 견견견견"`으로 출력 (ASCII는 정상, 하이라이트 배경은 정상).
- 원인 추정: MCP 서버 실행 환경에 한글 폰트 부재 → WeasyPrint 폰트 폴백 실패.
- 영향: **문서추출기 런타임 PDF 산출물 전체** — 한글 양식 문서는 사실상 판독 불가. 이번 미리보기 수정과 무관한 기존 이슈(이번 PoC로 최초 발견).
- 권고: `mcp-doc-convert-server` 실행 환경(Docker 포함)에 한글 폰트(예: Noto Sans KR) 설치 + composer HTML에 `font-family` 폴백 선언. **별도 기능(`doc-convert-korean-font`)으로 분리 권장.**

## 6. 결론

- Match Rate **96% ≥ 90%** → Act(iterate) 불필요, Report 진행 가능.
- 다음 단계: `/pdca report doc-extractor-preview-highlight`
- 후속 과제: §5 한글 폰트 이슈 별도 PDCA 착수 권장.
