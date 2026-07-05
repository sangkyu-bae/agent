# 완료 보고서: doc-extractor-preview-highlight (문서추출기 미리보기 하이라이트)

> **Summary**: 문서추출기 양식 등록 시 미리보기에서 추천 슬롯의 하이라이트가 표시되지 않고 HTML 크기가 깨지는 문제의 진단 및 해결. 원인은 MCP `pdf_to_html` text 모드의 출력 특성(절대좌표·그래픽 소실·텍스트 분절)을 앱이 감안하지 않은 것. 해결책은 A안 이원화(미리보기=layout 모드, skeleton=text 모드)와 DOM 정규화 매칭, iframe 스케일링으로 기존 산출물 파이프라인은 그대로 유지하고 미리보기 품질만 격상.
>
> **Author**: 배상규
> **Created**: 2026-07-03
> **Status**: Completed (96% Design Match, 0 iterations)

---

## Executive Summary

### 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **Feature** | doc-extractor-preview-highlight — 문서추출기 미리보기 하이라이트 + HTML 시각 충실도 복구 |
| **Duration** | 2026-07-03 (1일 단일 세션: Plan→Design→Do→Check) |
| **Match Rate** | 96% (D1~D9 100% + FR-01~06 100% 반영) |
| **Iteration** | 0회 (90% 기준 1회 통과, Act 진행 불필요) |
| **Technical Stack** | 백엔드: Python 3.11 + FastAPI + SQLAlchemy + PyMuPDF / 프론트: React 19 + TypeScript + DOMParser |
| **Scope** | Infrastructure(adapter options) + Application(use case 이원화) + Domain(정책 강화) + Frontend(유틸 재구현·패널) |

### 결과 요약

| 지표 | 실측 |
|------|------|
| **설계 결정 (D1~D9)** | 100% 구현·테스트 완료 |
| **요구사항 커버리지 (FR-01~07)** | 96% (FR-07 PoC 실측으로 범위 밖 발견 기록) |
| **아키텍처 준수** | 100% (infrastructure adapter options, application use case 이원화, domain 정책 강화) |
| **백엔드 테스트** | 117 passed (신규 11 케이스: `test_options_and_warnings` 5 + `test_preview_html` 5 + GB6 표식 1) |
| **프론트 테스트** | 161 passed (신규 15+ 케이스: 엔티티/분절/공백 매칭 + scale + D7 제외 + FR-06 안내 등) |
| **백엔드 변경 파일** | 7개 (adapter + use case + schemas + config + policies + main.py + .env.example) |
| **프론트 변경 파일** | 4개 (documentTemplate.ts 재구현 + types + Panel + 테스트) |
| **테스트 파일 갱신** | 3개 (adapter, use case, policies) |

### 1.3 Value Delivered (4관점)

| 관점 | 내용 |
|------|------|
| **Problem** | PDF/DOCX 양식 업로드 후 MCP 변환이 성공해 슬롯이 자동 추출되지만, **미리보기에 하이라이트가 전혀 표시되지 않고**, HTML이 원본과 달리 **크기/표/괘선이 깨져 보이는** 문제. 사용자가 "MCP 연결 문제인가?"라고 의심했으나 근본 원인은 다름. |
| **Solution** | **A안 이원화**: MCP `pdf_to_html` 호출을 2회(text 모드 + layout 모드)로 이원화해 분석/skeleton은 text(경량), 미리보기는 layout(시각 충실)으로 사용. 어댑터에 `options`/`warnings` 지원 추가(D2). 프론트는 DOM 기반 정규화 매칭(D4)으로 PyMuPDF 분절·엔티티·공백 문제 해결하고, mark 가시성 CSS(D5) + iframe 스케일링(D6)으로 미리보기 품질 격상. **기존 skeleton·산출물 경로는 무변경**(5MiB 상한, GB6 유지). |
| **Function/UX Effect** | 업로드 직후 미리보기가 **원본과 동일한 모습(표·괘선·배경 PNG)**으로 표시되고, **추천 슬롯 위치에 노란 하이라이트가 정확히 표시됨**. 하이라이트 실패 슬롯은 **확정 전에 안내**("문서에서 위치를 찾지 못한 슬롯 N개: …"). 실측(PoC): layout dpi 120 기본값 시 ~37KiB/page, PyMuPDF 엔티티 이스케이프 확증, html_to_docx 스타일 소실 확인. |
| **Core Value** | 휴먼인더룹의 핵심 근거인 **"미리보기 + 하이라이트"가 실제로 동작** → 사용자가 슬롯을 신뢰하고 확정 가능. 금융 양식 자동화의 **UX 신뢰성 회복**. 변경 반경 최소화(기존 산출물 무변경)로 **기술 리스크 최소** 유지. |

---

## PDCA Cycle Summary

### Plan (2026-07-03)

- **문서**: `docs/01-plan/features/doc-extractor-preview-highlight.plan.md`
- **진단 결론**: 
  - MCP 연결/호출은 정상(슬롯 추출 성공이 증거)
  - 근본 원인의 절반은 **MCP 도구의 "출력 특성"** — `pdf_to_html` text 모드 = PyMuPDF `get_text("html")` 절대좌표만, 표·괘선·배경 그래픽 소실, 텍스트 span 분절, HTML 엔티티 이스케이프
  - 절반은 **앱의 "감안 부족"** — 어댑터 options 미전달, 프론트 완전일치 매칭, 무스케일 iframe
- **목표**: G1~G5 (하이라이트 표시·시각 충실·실패 피드백·어댑터 강화·산출물 검증)
- **옵션 검토**: A(이원화) ✅, B(프론트만), C(서버 개선) — A 선택 이유: 시각 충실도+기존 파이프라인 무변경

### Design (2026-07-03)

- **문서**: `docs/02-design/features/doc-extractor-preview-highlight.design.md` (v0.2, PoC 실측 반영)
- **확정된 설계 결정 (§2 D1~D9)**:
  - **D1**: 이원화 — `html`(text, 분석용) + `preview_html`(layout, 미리보기 전용, PDF만)
  - **D2**: 어댑터 `options`/`warnings` 지원 추가 (MCP 실측 계약 기준)
  - **D3**: layout 실패 시 전체 extract 실패 아님, None 폴백(우아한 성능 저하)
  - **D4**: DOMParser 기반 정규화 매칭 — span 분절·엔티티·공백 해결
  - **D5**: mark 가시성 CSS 강제(`.pdf-page p mark {color:#111!important; background:#FFF3B0!important}`, 특이도 0,1,2)
  - **D6**: iframe 스케일 — pt 파싱 + `scale=min(1, containerWidth/px)` + `transform:scale(S)`
  - **D7**: sessionStorage previewHtml 제외(5MB 한계 회피)
  - **D8**: GB6 공란 표식 강화 — `[미기재]` 텍스트 병기(htmldocx 스타일 소실 폴백)
  - **D9**: config 2종 추가 (`document_extractor_preview_mode`, `document_extractor_preview_dpi=120`)
- **PoC 실측** (§6-3):
  - 문자열 완전일치 실패 확증: PyMuPDF가 모든 한글을 숫자 엔티티(`&#xae08;`) 출력
  - layout dpi 비교: 96→29KiB, **120→37KiB(채택)**, 144→46KiB
  - `html_to_docx` mark 스타일 소실 확증, 텍스트 표식 생존 확증
  - 실서버 `html_to_pdf`(WeasyPrint) 배경 `#FFF3B0` 보존 확증
  - 실서버 options 정상 수용, 평면 인자 계약 확증 (arguments 래퍼 거부)

### Do (2026-07-03)

- **구현 순서** (설계 §7 준수):
  - Phase 1: 백엔드 adapter options/warnings 테스트·구현
  - Phase 2: extract use case 이원화 + config DI + schemas (test→impl)
  - Phase 3: GB6 표식 강화
  - Phase 4: 프론트 유틸 buildTextIndex/findRange/findSlotRange 재구현 (test→impl)
  - Phase 5: buildPreviewHtml/tokenizeHtml 재구현 + 스케일 유틸
  - Phase 6: Panel 배선 + sessionStorage 제외 + FR-06 안내
  - Phase 7: 회귀 테스트
- **신규 백엔드 파일**: 0 (기존 infrastructure/application/domain 파일 내 구현)
- **변경 백엔드 파일** (7개):
  - `src/infrastructure/document_extractor/document_conversion_adapter.py` — `to_html(..., options)`, `_log_warnings`
  - `src/application/document_extractor/extract_use_case.py` — 이원화 로직, preview_mode/preview_dpi 주입
  - `src/application/document_extractor/schemas.py` — `ExtractResponse.preview_html: str | None`
  - `src/domain/document_extractor/policies.py` — `render_unfilled` 강화
  - `src/config.py` — 2개 키 추가
  - `src/api/main.py` — config DI
  - `.env.example` — 주석 추가
- **신규 프론트 파일**: 0 (기존 utils/types/components 내 재구현)
- **변경 프론트 파일** (4개):
  - `src/utils/documentTemplate.ts` — buildTextIndex/findRange 신규, buildPreviewHtml/tokenizeHtml 재구현, extractPageWidthPt 신규, saveDraftToSession 갱신
  - `src/types/documentExtractor.ts` — `preview_html` 필드 추가
  - `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` — previewHtml 우선, 스케일 계산, FR-06 안내
  - 테스트 3파일 신규·갱신

### Check (2026-07-03)

- **문서**: `docs/03-analysis/doc-extractor-preview-highlight.analysis.md`
- **Match Rate**: **96% ✅** (9개 D1~D9 100% + §3·4 상세 97%~100% + FR 96%)
- **Gap 목록**: 4건 모두 Low (명명/구조 표기 차이, 모두 조치 완료 또는 불요)
  - 함수명 `findSlotRange` vs `findRange`: Design §4-2 문서 갱신 완료 (v0.3)
  - tokenize 직렬화 fragment 분기: 개선 판정, 토큰 정합 계약 무영향
  - warnings 추출 별도 헬퍼: 관심사 분리 개선
  - D5 셀렉터 padding 추가: 의도 부합(폴백 미리보기 가시성)
- **테스트 커버리지**:
  - 백엔드: 신규 11 + 기존 106 = 117 passed (document_extractor 관련)
  - 프론트: 신규 15+ + 기존 146 = 161 passed (agent-builder 영역), tsc 통과
- **FR-07 잔여 확인 완료** (PoC 실측, 2026-07-03 실서버 :8003):
  - `html_to_pdf`(WeasyPrint) 정상 동작 — 로컬 GTK 이슈는 서버 환경과 무관
  - PDF에서 `<mark>` 배경 `#FFF3B0` 보존 ✅
  - DOCX에서 `[미기재]` 텍스트 표식 보존 ✅ (스타일만 소실, D8로 완화)
- **신규 발견** (범위 밖, 별도 후속):
  - **실서버 `html_to_pdf`(WeasyPrint)에서 한글 렌더링 실패** — ASCII는 정상, 한글 전부 동일 글리프 `"견견견…"` 출력
  - 원인: MCP 서버 환경 한글 폰트 부재
  - 영향: 문서추출기 런타임 PDF 산출물 전체 (한글 양식 판독 불가)
  - 권고: 별도 기능(`doc-convert-korean-font`) PDCA 착수, Docker 환경에 Noto Sans KR 설치 + font-family 폴백

---

## Results

### ✅ 완료 항목

#### 설계 결정
- ✅ **D1**: 이원화 구현 — `extract_use_case.py` `_maybe_preview_html` 메서드, schemas 이원화, Panel 폴백
- ✅ **D2**: 어댑터 options/warnings — `document_conversion_adapter.py` `to_html(..., options)`, `_build_payload`, `_log_warnings` 헬퍼
- ✅ **D3**: layout 실패 폴백 — `McpConversionError` catch, None 반환, 경고 로그
- ✅ **D4**: DOMParser 정규화 매칭 — `buildTextIndex`(CharRef 배열), `findRange` 순회, span 경계 허용, 엔티티 자동 해소
- ✅ **D5**: mark 가시성 CSS — `.pdf-page p mark` color:#111, background:#FFF3B0, 특이도 0,1,2 enforcing
- ✅ **D6**: iframe 스케일 — `extractPageWidthPt` pt 파싱, `ptToPx` 변환, Panel `useLayoutEffect` + resize 리스너, `transform: scale(S)`
- ✅ **D7**: sessionStorage previewHtml 제외 — `saveDraftToSession` 구조분해 제외
- ✅ **D8**: GB6 표식 강화 — `render_unfilled`에 `[미기재]` 병기, PoC 확증(htmldocx 스타일 소실·텍스트 생존)
- ✅ **D9**: config 2종 — `document_extractor_preview_mode` (layout|off), `document_extractor_preview_dpi` (120 기본값)

#### 요구사항 (FR-01~07)
- ✅ **FR-01** (High): 어댑터 options 전달 + warnings 로깅
- ✅ **FR-02** (High): 이원화 제공 — `html` + `preview_html` 분리
- ✅ **FR-03** (High): 정규화 매칭 강화 — 완전일치 → DOM 기반 텍스트 노드 정규화
- ✅ **FR-04** (High): mark 가시성 CSS 강제
- ✅ **FR-05** (High): iframe 스케일링 — pt 감지 → transform scale
- ✅ **FR-06** (Medium): 실패 슬롯 피드백 — 미확정 단계 안내 표시
- ⏳ **FR-07** (Medium): GB6 산출물 검증 — PoC 완료, 범위 밖 발견 기록 (별도 doc-convert-korean-font)

#### 테스트
- ✅ **백엔드**: `test_options_and_warnings` 5 + `test_preview_html` 5 + GB6 1 (신규 11) — document_extractor 117 all passed
- ✅ **프론트**: `buildTextIndex`/`findRange` (span/엔티티/공백), `buildPreviewHtml` (mark/토큰화/missingSlots), `tokenizeHtml` (분절 토큰화), `extractPageWidthPt`, `Panel` (previewHtml/안내) (신규 15+) — agent-builder 161 all passed, tsc 통과
- ✅ **TDD**: Red(test 작성) → Green(impl) 사이클 준수, 기존 테스트 회귀 없음

#### API 계약 동기화
- ✅ **백엔드**: `ExtractResponse.preview_html: str | None` 필드 추가 (하위호환)
- ✅ **프론트**: `ExtractDocumentResponse.preview_html: string | null` 타입 추가
- ✅ **문서**: Design §5 "API 계약 변경 요약" 정합

#### 아키텍처
- ✅ **domain 순수성**: policies에만 정책 추가, 외부 API/DB 미참조
- ✅ **infrastructure 책임**: adapter options 처리, MCP 계약 강화
- ✅ **application 제어**: use case에서 이원화 흐름(text+layout), config 주입
- ✅ **frontend 유틸**: DOM 기반 매칭, 프레젠테이션 로직 분리
- ✅ **컨벤션**: 함수 길이 40줄 이내, if 2단계 이내, 명시적 타입, logger 사용, print 0

### 🟡 미완료/범위 밖

- **FR-07 잔여 이슈** (범위 밖):
  - ✅ PDF: `html_to_pdf` mark 배경 보존 (WeasyPrint 정상)
  - ✅ DOCX: `[미기재]` 텍스트 표식 보존 (스타일 소실 폴백)
  - ⚠️ **신규 발견**: 실서버 `html_to_pdf`에서 한글 글리프 렌더링 전부 실패 — 별도 PDCA(`doc-convert-korean-font`) 권장
- **실양식 PDF 수동 QA**: 브라우저에서 다운로드 PDF를 열어 한글 렌더링·하이라이트 시각 확인 (별도 QA 담당자 협조)

---

## Lessons Learned

### ✅ 잘 된 점

1. **외부 의존 출력 계약은 PoC 실측이 설계를 확정한다**
   - Plan 단계에서 "MCP 옵션이 존재한다"는 추측만으로는 불충분
   - Design PoC(§6-3)에서 **실제 서버와 통신**해 `options` 수용성, `metadata.warnings` 형태, dpi별 크기, layout 모드 렌더링을 **직접 확증**
   - 결과: D2(options 전달), D6(dpi 120 기본값), D5(CSS 특이도) 등이 추측이 아닌 **측정값 기반 확정**
   - 이전 기능(`document-template-extractor`)에서 학습한 "실측 우선" 원칙을 **성공적으로 재적용**

2. **실측이 범위 밖 프로덕션 이슈를 조기 발견**
   - PoC 단계에서 `html_to_pdf` 한글 렌더링 실패 발견 (§5)
   - 본 기능 범위 밖이지만 **문서추출기 런타임 산출물 전체에 영향** → 즉시 기록 및 후속 과제화
   - 운영 전에 예측 불가능한 장애 조기 감지 → 리스크 완화

3. **라이브 서버가 `arguments` 래퍼를 거부 — 어댑터 폴백이 주 경로였음**
   - 설계(D2)에서 "평면 폴백 호출에도 options 유지"를 명시했으나, 실제로는 **MCP 서버가 arguments 래퍼 없이 평면 인자만 수용**
   - 단위 테스트(`test_flat_fallback_keeps_options`)로 폴백 경로의 options 보존을 고정
   - 덕분에 **프로덕션 배포 후에도 안정성 보장** (의도하지 않은 설계였으나 테스트로 검증됨)

### 🔄 개선할 점

1. **layout HTML 응답 크기 모니터링 필요**
   - dpi 120에서 ~37KiB/page로 처음엔 무시할만한 수준이지만, **다중 페이지 PDF나 그래픽 복잡도에 따라 확장 가능**
   - 모달 렌더 지연 주관적 판단보다는 **네트워크 워터폴, 브라우저 성능 도구로 정량화** 권장
   - config `document_extractor_preview_mode=off` 스위치로 언제든 비활성화 가능하도록 설계했으나, **운영 단계에서 모니터링 메트릭 정의 필요**

2. **DOM 정규화 매칭의 오탐 가능성**
   - 동일 텍스트가 다중 출현할 때 `findRange`는 **첫 출현만 매칭**
   - 의도는 기존 `replace` 의미 유지지만, 사용자 입장에선 **예상과 다른 위치에 하이라이트**될 수 있음
   - 완화책: FR-06 "실패 슬롯 안내"로 사용자 검수를 명시화했으나, **필요시 향후 슬롯별 로그/위치 지표** 추가 고려

3. **DOCX 산출물 `<mark>` 스타일 소실 → 텍스트 표식 병기**
   - D8에서 `htmldocx` 한계를 확인(스타일 미생성)하고 텍스트 표식으로 폴백
   - 그러나 **PDF는 배경 보존, DOCX는 텍스트만 생존** → 양식 산출물 외관 불일치
   - 향후: `html_to_docx` 엔진을 `pandoc` 대체나 `python-docx` 직접 사용으로 개선할 수 있으나 **이번 범위 밖**

### 🎯 다음 기능에 적용할 점

1. **MCP 도구 통합은 PoC 먼저**
   - 옵션/응답 형태/크기를 설계 단계에서 **실제 서버와 통신**해 확증
   - 로컬 mock이 아닌 **실 서버 환경에서 엣지 케이스 확인** (한글 폰트, 대용량 등)

2. **어댑터는 옵션 + warnings를 모두 노출**
   - 단순히 "성공/실패"가 아닌 **서버 경고/메타데이터도 상위 레이어에 전달**
   - 정책 결정(D3 우아한 성능 저하)이 전체 application 레벨에서 가능하도록

3. **프론트 렌더링은 DOM 기반 정규화 선호**
   - 텍스트 문자열 완전일치는 **인코딩·공백·엔티티 차이로 쉽게 깨짐**
   - `DOMParser` + 텍스트 노드 직렬화가 **브라우저 표준 해석 방식과 일치**하므로 이식성/안정성 높음

4. **설계 문서 갱신 형식화**
   - Design v0.1(초안) → v0.2(PoC 실측) → v0.3(구현 확정) 처럼 **버전 마킹** 명시
   - Gap Analysis에서 "함수명 상이" 같은 표기 차이도 기록해 **설계 신뢰도 추적**

---

## Next Steps

### 즉시 (우선순위: High)
1. [ ] 실양식 PDF 다운로드 + 브라우저 수동 열기 — 한글 렌더링 문제 시각 확인 (QA 담당자)
2. [ ] Production 배포 전 smoke test — document-extractor 엔드포인트 alive, 실제 문서 1~2종 테스트

### 단기 (우선순위: Medium)
1. [ ] **별도 PDCA 시작**: `doc-convert-korean-font` — MCP 서버 환경에 한글 폰트 설치 + composer 스타일시트에 font-family 폴백 추가
2. [ ] 운영 모니터링 메트릭 정의 — layout HTML 응답 크기 / 미리보기 모달 로드 시간 / 하이라이트 실패율

### 장기 (우선순위: Low)
1. [ ] DOCX 산출물 `<mark>` 스타일 보존 검토 — pandoc 엔진 또는 python-docx 직접 사용
2. [ ] 슬롯 위치 로깅/시각화 — 다중 출현 시 사용자가 정확한 위치 선택 가능하도록 (UI 개선)

---

## 변경 요약

### 백엔드 변경 (7파일)
| 파일 | 변경 내용 |
|------|---------|
| `src/infrastructure/document_extractor/document_conversion_adapter.py` | `to_html(..., options: dict \| None)` 시그니처 추가, `_build_payload` options 전달, `_log_warnings` 헬퍼 신규 |
| `src/application/document_extractor/extract_use_case.py` | `preview_mode`/`preview_dpi` 주입, `_maybe_preview_html` 메서드 신규(layout 변환 시도·폴백 처리) |
| `src/application/document_extractor/schemas.py` | `ExtractResponse.preview_html: str \| None` 필드 추가 |
| `src/domain/document_extractor/policies.py` | `render_unfilled` 출력에 `[미기재]` 텍스트 병기 |
| `src/config.py` | `document_extractor_preview_mode: str = "layout"`, `document_extractor_preview_dpi: int = 120` 추가 |
| `src/api/main.py` | extract_use_case 생성 시 preview config 전달 |
| `.env.example` | 2개 키 주석 추가 |

### 프론트 변경 (4파일)
| 파일 | 변경 내용 |
|------|---------|
| `src/utils/documentTemplate.ts` | `buildTextIndex`/`findRange`/`groupSpans` 신규(DOM 정규화 매칭), `buildPreviewHtml`/`tokenizeHtml` 재구현, `extractPageWidthPt`/`ptToPx`/`injectPreviewStyle` 신규, `saveDraftToSession` previewHtml 제외 |
| `src/types/documentExtractor.ts` | `ExtractDocumentResponse.preview_html: string \| null`, `DocumentExtractorDraft.previewHtml?: string` 필드 추가 |
| `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` | `previewHtml ?? html` 우선 사용, wrapper ref + resize 리스너로 스케일 계산, FR-06 실패 슬롯 안내 표시 |
| 테스트 3파일 | adapter/extract_use_case/policies 테스트 신규/갱신 (5+5+1 = 11 케이스) |

### 테스트 추가 (신규 26 케이스)
| 대상 | 신규 케이스 | 비고 |
|------|-----------|------|
| 백엔드 adapter | 5 | options 미지정/지정/폴백, warnings 로깅 |
| 백엔드 extract | 5 | PDF 이원화, DOCX null, layout 실패, preview_mode off |
| 백엔드 policies | 1 | render_unfilled 표식 |
| 프론트 유틸 | 15+ | buildTextIndex, findRange(span/엔티티/공백), extractPageWidthPt, buildPreviewHtml, tokenizeHtml, saveDraftToSession, Panel missingSlots |

---

## 참고 문서

- **Plan**: `docs/01-plan/features/doc-extractor-preview-highlight.plan.md`
- **Design**: `docs/02-design/features/doc-extractor-preview-highlight.design.md` (v0.2 PoC 반영, v0.3 구현 정합)
- **Analysis**: `docs/03-analysis/doc-extractor-preview-highlight.analysis.md` (96% match, 0 gaps critical)
- **원 기능 PDCA**: `docs/archive/2026-07/document-template-extractor/` (이번 PoC 기법 재적용)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-03 | 초안 작성 (Plan+Design+Do+Check 통합) | 배상규 |
| 1.1 | 2026-07-03 | FR-07 PoC 실측 완료, 한글 폰트 이슈 추가 | 배상규 |
