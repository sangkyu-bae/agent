# fix-doc-generator-korean-font Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot / idt (백엔드)
> **Analyst**: 배상규
> **Date**: 2026-09-05
> **Design Doc**: [fix-doc-generator-korean-font.design.md](../02-design/features/fix-doc-generator-korean-font.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 외부 변환 서버에 한글 폰트가 없어 생성 PDF의 한글이 100% .notdef로 깨진다 (실측: 549 코드 중 472). |
| **WHO** | P2 KB 운영자 / 에이전트 소유자 — 문서 생성·양식 채우기로 PDF를 받는 모든 사용자. |
| **RISK** | 폰트 base64 임베드로 MCP 요청 페이로드가 커져 변환 실패·타임아웃이 날 수 있다. |
| **SUCCESS** | 한글 .notdef 0%, BaseFont에 한글 폰트명, 페이로드 증가분 ≤ 200KB. |
| **SCOPE** | module-1 자산·검증기 / module-2 임베드 코어 / module-3 변환경로 적용 / module-4 실경로 검증. |

---

## Strategic Alignment Check

PRD는 작성되지 않았다(`/pdca pm` 미실행). Plan의 Executive Summary를 상위 의도로 사용한다.

| 상위 의도 | 기대 | 구현 상태 |
|-----------|------|:---------:|
| Core Problem (WHY) | 변환 서버 폰트 부재로 깨지는 한글을 클라이언트에서 해결 | ✅ 해결 — 단, 실경로(E-01) 미검증 |
| Target User (WHO) | 문서 생성·양식 채우기 사용자 | ✅ 두 경로 모두 커버 (공유 어댑터 1지점) |
| Value Proposition | "읽을 수 있는 문서 산출물" | ⚠️ 부분 — pdf_export 경로는 실증 완료, MCP 경로는 미실증 |

### Success Criteria Status

| # | Criteria (Plan §4.1) | 상태 | 근거 |
|---|---------------------|:----:|------|
| SC-1 | FR-01~FR-09 구현 완료 | ⚠️ | 전 항목 구현. FR-01은 배포 패키징 누락으로 부분 (§2.5 GAP-02) |
| SC-2 | 한글 .notdef 비율 **0%** | ⚠️ | pdf_export 실경로 **0/210 (0.0%)** 실증. MCP 경로는 미실행(GAP-01) |
| SC-3 | BaseFont에 한글 폰트명 존재 | ⚠️ | `AAAAAA+Pretendard-Regular`, `AAAAAA+Pretendard-Bold` 확인. MCP 경로 미확인 |
| SC-4 | TDD 준수 (테스트 선작성) | ✅ | 5개 모듈 전부 Red→Green. 신규 모듈 커버리지 **181 stmts 100%** |
| SC-5 | verify-architecture / logging / tdd 통과 | ✅ | domain→infra 임포트 0, `print()` 0, 함수 40줄 초과 0, 신규 모듈 전부 테스트 보유 |
| SC-6 | 폰트 라이선스 표기 | ✅ | `resources/fonts/OFL.txt` (SIL OFL 1.1, 4,419B) |
| SC-7 | 기존 테스트 무회귀 | ✅ | `tests/api` 실패 24개가 변경 전후 **동일**(사전 존재). 전체 8,882 passed |
| SC-8 | 페이로드 증가분 ≤ 200KB | ✅ | 일반 문서 9.3KB, 고유 500자 문서 108.5KB (적응형 폴백 작동) |
| SC-9 | 오버헤드 ≤ 300ms | ⚠️ | 평시 173ms(cold 239ms) 통과. `--cov` 계측 하에서는 실패 (GAP-06) |

**Success Rate**: 5/9 완전 충족, 4/9 부분 충족, 0/9 미충족

### Decision Record Verification

| Source | Decision | 준수? | 비고 |
|--------|----------|:-----:|------|
| [Plan] | 서버 수정 불가 → 클라이언트 임베드 | ✅ | data URI로 self-contained 구성 |
| [Design] | Option C — 어댑터 일괄 주입 | ✅ | `document_conversion_adapter.py:95` 단일 지점 |
| [Design] | Pretendard TTF (woff2 아님) | ✅ | `font_subsetter.py:22` `data:font/ttf;base64,` |
| [Design] | 글리프 누락 시 경고 후 진행 | ✅ | `html_font_embedder.py:56-63`, 신규 예외 타입 없음 |
| [Design] | 사용 문자 서브셋 | ✅ | `policies.py:28` → `font_subsetter.py:43-45` |
| [Design] | FR-07은 `@font-face url(로컬파일)` | ❌ | **의도적 변경** — Windows에서 xhtml2pdf 임시파일 복사 실패. reportlab 직접 등록으로 대체 (§2.6 DEV-01) |
| [승인] | 페이로드 초과 시 적응형 폴백 | ✅ | `html_font_embedder.py:79-101` — 설계 이후 사용자 승인으로 추가 |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 문서와 실제 구현의 격차를 측정하고, "한글이 실제로 렌더링된다"는 주장이 근거를 갖는지 확인한다.

### 1.2 Analysis Scope

- Design: `docs/02-design/features/fix-doc-generator-korean-font.design.md`
- 구현: `src/domain/document_font/`, `src/infrastructure/document_font/`, `document_conversion_adapter.py`, `weasyprint_converter.py`, `main.py`, `config.py`
- 분석일: 2026-09-05

> **주의**: `gap-detector` 에이전트를 2회 호출했으나 두 번 모두 본문 없이 종료되어(누적 ~215k 토큰, 산출물 0) 정적 분석은 직접 수행했다.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 파일 구조 (Design §11.1)

| Design 약속 | 구현 | 상태 |
|-------------|------|:----:|
| `src/domain/document_font/{__init__,policies,schemas}.py` | 존재 | ✅ |
| `src/infrastructure/document_font/{__init__,font_subsetter,html_font_embedder}.py` | 존재 | ✅ |
| `resources/fonts/{Pretendard-Regular.ttf,Pretendard-Bold.ttf,OFL.txt}` | 존재 (2.7MB/2.66MB/4.4KB) | ✅ |
| `tests/support/pdf_glyph_check.py` | 존재 | ✅ |
| `tests/domain/document_font/test_policies.py` | 존재 | ✅ |
| `tests/infrastructure/document_font/test_{font_subsetter,html_font_embedder}.py` | 존재 | ✅ |
| `tests/infrastructure/pdf_export/test_korean_glyph.py` | 존재 | ✅ |
| `tests/fixtures/korean_document.html` | **없음** — 테스트가 HTML을 인라인 | ⚠️ GAP-07 |

**설계에 없던 추가물** (모두 정당한 사유 있음):

| 파일 | 사유 |
|------|------|
| `src/infrastructure/document_font/factory.py` | DI 배선 2곳 중복 제거 |
| `tests/infrastructure/document_font/test_factory.py` | 위 모듈의 TDD 커버 |
| `tests/infrastructure/document_extractor/test_document_conversion_adapter_font.py` | Design §8.2 U-10~U-12 구현 |
| `scripts/verify_document_font_embed.py` | E-01을 나중에 실행할 수 있게 절차 코드화 |

**Structural Match: 93%** (14/15 + 추가물 정당)

### 2.2 기능 충족도 (Plan §3.1)

| FR | 요구 | 상태 | 근거 |
|----|------|:----:|------|
| FR-01 | 폰트 자산 + 라이선스 반입 | ⚠️ | 파일 존재. 단 **wheel 패키징 누락** → GAP-02 |
| FR-02 | @font-face 문서 셸 유틸 | ✅ | `html_font_embedder.py:47` `wrap()`, `:104` `_build_css()` |
| FR-03 | 사용 문자 런타임 서브셋 | ✅ | `font_subsetter.py:36` `subset()`, `:82` `_build_subset()` |
| FR-04 | generator 경로 적용 | ✅ | `main.py:2728` 앱스코프 어댑터 주입 (generator·composer 공유) |
| FR-05 | extractor/composer 적용 | ✅ | 동상. `main.py:890` 요청스코프에도 주입 |
| FR-06 | 완결 HTML 셸 중복 방지 | ✅ | `html_font_embedder.py:134-149` 4가지 형태 분기 |
| FR-07 | pdf_export 한글 등록 | ✅ | `weasyprint_converter.py:83-105` (방식 변경 → DEV-01) |
| FR-08 | .notdef 검사 유틸 | ✅ | `tests/support/pdf_glyph_check.py` — 골든 샘플로 472/549 재현 |
| FR-09 | 실패 시 경고 후 진행 | ✅ | `html_font_embedder.py:56-63`, `document_conversion_adapter.py:116-127` |
| FR-10 | pptx→pdf 진단 | ✅ | `golden_sample_report.pdf` BaseFont = Malgun Gothic 서브셋 2종 → **DejaVu 문제 징후 없음** |

**Functional Depth: 95%** (9.5/10 — FR-01 부분)

### 2.3 계약 일치 (Design §4)

| 계약 | 설계 | 구현 | 상태 |
|------|------|------|:----:|
| `DocumentConversionAdapter.__init__(..., font_embedder=None)` | 기본 None, 하위 호환 | `:39,:47` | ✅ |
| `to_document(html, output_format, mcp_tool_id, request_id)` | **시그니처 불변** | 불변 확인 | ✅ |
| `HtmlFontEmbedder.wrap(html, request_id) -> FontEmbedResult` | 순수 변환 + 폴백 | `:47` | ✅ |
| `DocumentCharsetPolicy.extract_chars(html) -> frozenset[str]` | 순수 | `policies.py:28` | ✅ |
| `FontSubsetter.subset(weight, chars) -> EmbeddedFont` | missing 반환 | `:36` | ✅ |
| §4.2 조각 HTML → 셸로 감쌈 | | `:145-149` | ✅ |
| §4.2 `<head>` 있음 → style만 삽입 | | `:136-137` | ✅ |
| §4.2 `<html>` 있고 `<head>` 없음 → head 삽입 | | `:139-143` | ✅ |
| §4.2 빈 문자열 → 폴백 | | `:71-77` `_skip_reason` | ✅ |
| §10.3 `DOCUMENT_FONT_EMBED_ENABLED/FAMILY/DIR/MAX_EMBED_KB` | 4개 | `config.py:184-187` | ✅ |
| §10.3 설정 문서화 | — | **`.env.example` 미기재** | ⚠️ GAP-05 |

**Contract Match: 90%**

### 2.4 런타임 검증

Design §8의 L1(단위)·L2(통합)를 실행했다. L3/E-01(실제 MCP)은 MySQL·MCP 미가동으로 실행하지 못했다.

| 레벨 | 실행 | 결과 |
|------|:----:|------|
| L1 단위 (U-01~U-13) | ✅ | 47 passed |
| L2 통합 (I-01·I-02) | ✅ | .notdef **0/210 (0.0%)**, BaseFont에 Pretendard 2종 |
| 회귀 감지 자체 검증 | ✅ | 폰트 제거 시 `verifiable=False`로 실패 → 감지기가 실제로 작동 |
| L3 / E-01 (실제 MCP) | ❌ | MySQL 연결 불가(`getaddrinfo failed`) |
| E-02 (pptx→pdf 진단) | ✅ | Malgun Gothic 서브셋 임베드 — 이상 없음 |

**Runtime: 80%** (핵심 경로가 미검증이라 감점)

### 2.5 발견된 Gap

| ID | 심각도 | 내용 | 근거 | 실패 시나리오 |
|----|:------:|------|------|---------------|
| **GAP-01** | **Critical** | E-01 미실행 — MCP의 WeasyPrint가 data URI `@font-face`를 수용하는지 **미검증**. 이 설계의 전제 자체다 | Plan §5 최고 리스크 | 서버가 data URI를 무시하면 생성 문서는 지금과 똑같이 깨지고, 이번 작업 전체가 무효가 된다 |
| **GAP-02** | **Critical** | `resources/`가 wheel에 포함되지 않음 | `pyproject.toml:97-98` `packages = ["src"]` | 휠로 배포하면 폰트 파일이 없어 `resolve_font_dir`가 빈 경로를 가리키고, FR-09 폴백이 조용히 원본 HTML을 보낸다 → **프로덕션에서 버그 그대로 재현, 경고 로그만 남음** |
| **GAP-03** | Important | extractor 경로가 요청마다 `FontSubsetter`를 새로 만들어 캐시가 항상 cold | `main.py:881-890` (`extract_factory`는 요청 스코프) | 변환 1건당 2.7MB 폰트를 4회 읽어 ~240ms. 앱스코프(`:2728`)는 warm ~100ms — 같은 기능이 경로에 따라 2배 느리다 |
| **GAP-04** | Important | `output_format`과 무관하게 폰트를 심는다 — `html_to_docx`에도 base64 폰트가 실린다 | `document_conversion_adapter.py:93-97` | Word 변환에 쓸모없는 수십~수백 KB가 매 요청 붙는다. 페이로드 리스크(Plan §5)를 이유 없이 키운다 |
| **GAP-05** | Minor | `.env.example`에 `DOCUMENT_FONT_*` 4개 미기재 (126줄짜리 파일 존재) | `.env.example` | 운영자가 차단 스위치의 존재를 모른다 |
| **GAP-06** | Minor | 300ms NFR 테스트가 `--cov` 계측 하에서 실패 | `test_html_font_embedder.py:191` | CI에 커버리지를 켜는 순간 깨진다 (계측 없이는 3/3 통과, 0.33~0.52s) |
| **GAP-07** | Minor | `tests/fixtures/korean_document.html` 미생성 (Design §8.6) | — | 테스트가 HTML을 인라인해 픽스처 재사용이 안 된다 |

### 2.6 설계 대비 의도적 변경 (승인·기록됨)

| ID | 변경 | 사유 |
|----|------|------|
| DEV-01 | FR-07 방식: `@font-face url(파일)` → reportlab `registerFont` + `DEFAULT_FONT` 매핑 | Windows에서 `Can't open file ...tmp.ttf` — xhtml2pdf의 임시파일 복사가 실패. 코드에 사유 주석 기재 |
| DEV-02 | 페이로드 예산 처리: 경고만 → **적응형 폴백**(초과 시 Bold 버리고 Regular 재서브셋) | 실측상 고유 500자에서 Regular+Bold=215KB로 NFR 초과. 사용자 승인 |
| DEV-03 | `pdf_glyph_check`에 `verifiable` 판정 추가 | 폰트 미임베드 PDF가 "정상"으로 통과하던 사각지대 — 안 고쳤으면 I-01이 가짜 초록이었다 |
| DEV-04 | `FontSubsetter`에 파일·cmap 캐시 추가 | 캐시 없이는 373ms로 300ms NFR 미달 |

---

## 3. Code Quality

### 3.1 Complexity

- 함수 40줄 초과: **0건** (신규·변경 6개 파일 전수 AST 검사)
- if 중첩 2단계 초과: 없음
- 신규 모듈 라인 수: 181 statements

### 3.2 Code Smells

| 항목 | 판정 |
|------|------|
| `print()` 사용 | 0건 |
| 스택 트레이스 없는 에러 처리 | `except Exception`이 2곳(`html_font_embedder.py:57`, `document_conversion_adapter.py:122) — 의도된 폴백이며 사유를 warning 로그에 남긴다 |
| 전역 상태 변경 | `weasyprint_converter.py:104` `DEFAULT_FONT[...]` — 프로세스 전역 딕셔너리 변경. 단일 패밀리만 쓰는 현재는 무해하나 다중 패밀리 시 마지막 등록이 이긴다 |
| `re.sub` 치환문 이스케이프 | `html_font_embedder.py:137` — 치환 문자열에 백슬래시가 들어가면 깨진다. base64 알파벳에는 없어 현재는 안전 |

### 3.3 Security

| 항목 | 판정 |
|------|------|
| 신규 외부 통신 | 없음 (data URI 인라인) |
| 사용자 입력의 CSS 삽입 | 없음 — 주입 CSS는 전부 코드 생성 상수 + base64 |
| sanitize 우회 | 없음 — 셸은 `HtmlSanitizePolicy.clean()` **이후** 단계에서 씌운다 |
| 라이선스 | SIL OFL 1.1, 원문 동봉 |

---

## 4. Performance

| 지표 | 측정 | 기준 | 판정 |
|------|------|------|:----:|
| 임베드 오버헤드 (warm) | 173ms | ≤300ms | ✅ |
| 임베드 오버헤드 (cold) | 239ms | ≤300ms | ✅ |
| 적응형 폴백 케이스 (서브셋 3회) | 275ms | ≤300ms | ✅ |
| 페이로드 (일반 문서) | 9.3KB | ≤200KB | ✅ |
| 페이로드 (고유 500자) | 108.5KB | ≤200KB | ✅ |
| extractor 경로 실효 오버헤드 | ~240ms (항상 cold) | — | ⚠️ GAP-03 |

---

## 5. Test Coverage

| 대상 | 커버리지 |
|------|:--------:|
| `src/domain/document_font/policies.py` | 100% (16 stmts) |
| `src/domain/document_font/schemas.py` | 100% (29) |
| `src/infrastructure/document_font/factory.py` | 100% (13) |
| `src/infrastructure/document_font/font_subsetter.py` | 100% (56) |
| `src/infrastructure/document_font/html_font_embedder.py` | 100% (67) |
| **합계** | **100% (181 stmts)** |

**미커버 영역**: `document_conversion_adapter._embed_fonts`는 별도 테스트 5건으로 커버되나 위 측정에는 미포함. `weasyprint_converter._register_fonts`는 통합 테스트로만 커버(단위 테스트 없음).

---

## 6. Clean Architecture Compliance

| 규칙 | 판정 | 근거 |
|------|:----:|------|
| domain → infrastructure 참조 금지 | ✅ | `src/domain/document_font` 내 infra/fontTools 임포트 0건 |
| domain 순수성 | ✅ | `policies.py`는 `html`,`re`만, `schemas.py`는 `dataclasses`만 |
| application 레이어 불변 | ✅ | UseCase 변경 없음 |
| interfaces 레이어 불변 | ✅ | 라우터/스키마 변경 없음 |
| 폰트 IO·서브셋은 infrastructure | ✅ | `font_subsetter.py` |

**Architecture Score: 100%**

---

## 7. Convention Compliance

| 항목 | 판정 |
|------|:----:|
| 네이밍 (`~Policy`, `~Adapter`, `~er`) | ✅ |
| 임포트 순서 (표준 → 서드파티 → domain → infrastructure) | ✅ |
| config 하드코딩 금지 | ✅ 4개 설정 분리 |
| 환경변수 문서화 | ⚠️ GAP-05 |
| 폰트 자산 위치 규칙 (Plan §8.2) | ⚠️ 위치는 확정, **패키징 규칙 미이행** (GAP-02) |
| 구조화 로깅 | ✅ `font_bytes`, `missing_chars`, `payload_bytes` 등 |

**Convention Score: 85%**

---

## 8. Overall Score

런타임을 실행했으므로 v2.3.0 가중 공식을 적용한다.

```
Overall = (Structural × 0.15) + (Functional × 0.25) + (Contract × 0.25) + (Runtime × 0.35)
        = (93 × 0.15) + (95 × 0.25) + (90 × 0.25) + (80 × 0.35)
        = 13.95 + 23.75 + 22.50 + 28.00
        = 88.2%
```

| 축 | 점수 |
|----|:----:|
| Structural Match | 93% |
| Functional Depth | 95% |
| Contract Match | 90% |
| Runtime | 80% |
| **Overall Match Rate** | **88.2%** |

목표 90% 미달. 감점의 대부분은 **GAP-01(핵심 경로 미검증)**과 **GAP-02(배포 시 자산 누락)**이며, 둘 다 "코드는 맞는데 실제로 동작한다는 증거가 없다"는 같은 성격의 문제다.

---

## 9. Recommended Actions

### 9.1 즉시 (24시간 내)

1. **GAP-02 수정** — `pyproject.toml`에 `resources/` 포함 (`[tool.hatch.build] artifacts` 또는 `force-include`). 배포 후에야 드러나는 종류의 결함이다.
2. **GAP-01 실행** — MySQL·MCP 기동 후 `python scripts/verify_document_font_embed.py <mcp_tool_id>`. **OK가 나오기 전까지 이 기능은 "고쳤다"고 말할 수 없다.**

### 9.2 단기 (1주 내)

3. **GAP-03** — `create_html_font_embedder`를 앱 스코프에서 1회 생성해 두 배선이 공유하도록 변경.
4. **GAP-04** — `to_document`에서 `output_format == "pdf"`일 때만 임베드.
5. **GAP-05** — `.env.example`에 `DOCUMENT_FONT_*` 4개 추가.

### 9.3 백로그

6. **GAP-06** — 타이밍 단언을 `--cov` 내성 있게(임계 상향 또는 마커 분리).
7. **GAP-07** — `tests/fixtures/korean_document.html` 추출.
8. `weasyprint_converter._register_fonts` 단위 테스트 추가.

---

## 10. Design Document Updates Needed

| 섹션 | 수정 내용 |
|------|-----------|
| §4.2 | FR-07 방식 변경(DEV-01) 반영 — `@font-face url` → reportlab 등록 |
| §4.2 | 적응형 폴백(DEV-02) 동작 명시 |
| §8.5 | `verifiable` 판정(DEV-03) 추가 |
| §11.1 | `factory.py`, `scripts/verify_document_font_embed.py` 추가 |
| §10.4 | 폰트 자산 **패키징 규칙**을 명시 (GAP-02 재발 방지) |

---

## 11. Next Steps

1. [x] GAP-02~GAP-07 수정 (§12)
2. [ ] **E-01 실행** — `python scripts/verify_document_font_embed.py <mcp_tool_id>` 후 결과를 §2.4에 기록
3. [ ] GAP-05 수동 반영 (`.env.example` — 도구 쓰기 차단 대상)
4. [ ] E-01 OK 확인 후 `/pdca report`

---

## 12. Iteration Record (Act, 2026-09-05)

사용자 결정: "코드로 고칠 수 있는 것 전부".

| GAP | 조치 | 검증 |
|-----|------|------|
| **GAP-02** | `pyproject.toml`에 `force-include = { "resources/fonts" = "resources/fonts" }` | 휠 빌드 후 zip 엔트리에 `resources/fonts/{OFL.txt,Pretendard-Bold.ttf,Pretendard-Regular.ttf}` 존재 확인 |
| **GAP-03** | `main.py` — `extract_factory` 밖에서 임베더 1회 생성 후 공유 | `tests/api` 781 passed (실패 24건은 사전 존재, 변경 전후 동일) |
| **GAP-04** | `_embed_fonts(html, output_format, request_id)` — `pdf`일 때만 임베드 | 신규 테스트 `test_docx_output_is_not_font_embedded` Red→Green |
| **GAP-05** | ❌ **미조치** — `.env.example`이 bkit 스코프 정책상 쓰기 차단. 우회하지 않음 | 스니펫을 사용자에게 전달 |
| **GAP-06** | 타이밍 단언을 예열 후 3회 측정 `min` 기준으로 변경 | 전체 스위트·`--cov` 양쪽에서 통과 |
| **GAP-07** | `tests/fixtures/korean_document.html` 생성, pdf_export 테스트가 참조 | 11 passed |
| **GAP-01** | ❌ **미조치** — MySQL·MCP 미가동. 코드로 해결 불가 | `scripts/verify_document_font_embed.py` 준비 완료 |

### 수정 후 재측정

| 축 | 이전 | 이후 | 사유 |
|----|:----:|:----:|------|
| Structural | 93% | **100%** | 픽스처 생성으로 §11.1 전량 충족 |
| Functional | 95% | **100%** | FR-01 패키징 해결 (휠 검증 완료) |
| Contract | 90% | **95%** | GAP-04 계약 정정. GAP-05 문서화는 미해결 |
| Runtime | 80% | **80%** | E-01 여전히 미실행 |

```
Overall = (100 × 0.15) + (100 × 0.25) + (95 × 0.25) + (80 × 0.35) = 91.8%
```

**Match Rate: 88.2% → 91.8%** (목표 90% 충족)

> **그러나 GAP-01은 여전히 열려 있다.** 수치가 90%를 넘었다는 것과 "이 버그가 고쳐졌다"는 것은 다른 말이다. MCP 실경로에서 `.notdef 0%`가 확인되기 전까지 이 기능은 완료로 보고하지 않는다.

**최종 테스트**: 기능 스위트 124 passed, 신규 모듈 커버리지 100% (181 stmts), `tests/api` 무회귀.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-05 | 최초 분석 — Match Rate 88.2%, Critical 2건(GAP-01·GAP-02) | 배상규 |
| 0.2 | 2026-09-05 | Act 반영 — GAP-02·03·04·06·07 수정, Match Rate 91.8%. GAP-01·GAP-05 미해결 | 배상규 |
