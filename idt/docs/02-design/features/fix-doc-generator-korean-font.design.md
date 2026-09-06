# fix-doc-generator-korean-font Design Document

> **Summary**: `DocumentConversionAdapter.to_document()` 한 지점에서 HTML에 Pretendard 서브셋 폰트를 `@font-face` data URI로 임베드해, 외부 MCP 변환 서버의 한글 폰트 부재로 인한 .notdef 깨짐을 제거한다.
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-04
> **Status**: Draft
> **Planning Doc**: [fix-doc-generator-korean-font.plan.md](../../01-plan/features/fix-doc-generator-korean-font.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 (Schema) | — | N/A (DB 변경 없음) |
| Phase 2 (Convention) | Plan §8.2 항목 | ❌ 미정의 (본 설계 §10.4에서 확정) |
| Phase 3 (Mockup) | — | N/A |
| Phase 4 (API Spec) | — | N/A (공개 API 변경 없음) |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 외부 변환 서버에 한글 폰트가 없어 생성 PDF의 한글이 100% .notdef로 깨진다 (실측: 코드 172개 중 149개, 302중 265, 75중 58이 GID 0). |
| **WHO** | P2 KB 운영자 / 에이전트 소유자 — 문서 생성·양식 채우기 기능으로 PDF 산출물을 받는 모든 사용자. |
| **RISK** | 폰트 base64 임베드로 MCP 요청 페이로드가 커져 변환 실패·타임아웃이 날 수 있다. → 문서에 실제 등장하는 글자만 서브셋. |
| **SUCCESS** | 생성 PDF의 한글 .notdef 비율 0%, 임베드 폰트 BaseFont에 한글 폰트명 존재, 변환 페이로드 증가분 ≤ 200KB. |
| **SCOPE** | Phase 1 공통 폰트 임베드 유틸 + document_generator / Phase 2 document_extractor·pdf_export 적용 / Phase 3 스모크 테스트 / pptx→pdf는 진단·경고만. |

---

## 1. Overview

### 1.1 Design Goals

1. **단일 주입 지점** — html→doc 변환 경로가 반드시 지나는 한 곳에서 폰트를 보장한다. 새 호출자가 생겨도 자동으로 커버된다.
2. **Self-contained 산출물** — 변환 서버의 폰트 설치 상태·네트워크 접근성에 의존하지 않는다.
3. **페이로드 통제** — 문서에 실제 등장하는 글자만 서브셋해 요청 증가분을 수십 KB로 유지한다.
4. **실패 격리** — 폰트 처리 실패가 문서 생성 자체를 실패시키지 않는다.
5. **회귀 감지 가능** — .notdef 비율을 기계적으로 측정해 같은 사고를 다시 놓치지 않는다.

### 1.2 Design Principles

- **Thin DDD 준수**: 도메인에는 순수 규칙(문자 집합 추출)만, 파일 IO·서브셋팅·base64는 infrastructure.
- **기존 계약 불변**: MCP 페이로드 형태(`{"arguments": {"source": …}}`), 어댑터 시그니처의 하위 호환을 깨지 않는다.
- **정책은 프롬프트가 아니라 코드가 책임진다**: LLM 프롬프트의 `style` 금지 규칙(policies.py:120-121)은 그대로 두고, 문서 셸은 코드가 씌운다.
- **끄고 켤 수 있게**: 문제가 생기면 설정 한 줄로 임베드를 비활성화해 즉시 기존 동작으로 되돌린다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: 호출자별 주입 | Option B: 도메인 인터페이스 + DI | Option C: 어댑터 일괄 주입 |
|----------|:-:|:-:|:-:|
| **Approach** | generator/composer가 각각 헬퍼 호출 | domain 인터페이스 + infra 구현 + DI 주입 | `to_document()` 내부에서 일괄 적용 |
| **New Files** | 1 | 5~6 | 3 |
| **Modified Files** | 3 | 6+ | 4 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **누락 위험** | 높음 (새 호출자마다 반복) | 낮음 | 가장 낮음 |
| **Recommendation** | 핫픽스용 | 장기 프로젝트 | **선택됨** |

**Selected**: **Option C — 어댑터 일괄 주입**

**Rationale**: 이번 버그의 근본 구조적 원인이 "폰트 지정 지점이 어디에도 없고, 변환 경로가 여러 호출자로 흩어져 있다"는 것이다. Option A는 그 구조를 그대로 재생산한다. Option B는 정석이지만 폰트 임베드 하나에 도메인 인터페이스+DI 배선까지 만드는 건 `idt/CLAUDE.md` §6이 금지한 "과도한 추상화"에 가깝다. `to_document()`는 html→doc 전용 단일 관문이라 여기서 셸을 씌우면 현재의 generator·composer는 물론 미래 호출자까지 자동 커버된다. 어댑터가 콘텐츠를 살짝 변형하는 비용은, 그 어댑터의 책임이 "변환 요청을 올바르게 구성하는 것"이라는 점에서 응집도 내에 있다.

### 2.1 Component Diagram

```
 [DocumentGenerator]        [DocumentComposer]        (미래 호출자)
        │                          │                       │
        └──────────────┬───────────┴───────────────────────┘
                       ▼
        ┌──────────────────────────────────────────┐
        │  DocumentConversionAdapter.to_document()  │  ← 단일 주입 지점
        │   1) embedder.wrap(html)                  │
        │   2) base64 → MCP 호출                     │
        └──────────────┬───────────────────────────┘
                       ▼
        ┌──────────────────────────────────────────┐
        │  HtmlFontEmbedder (infrastructure)        │
        │   ├─ DocumentCharsetPolicy (domain)       │  사용 문자 추출
        │   ├─ FontSubsetter (fontTools)            │  글리프 서브셋
        │   └─ 문서 셸/@font-face CSS 생성            │
        └──────────────┬───────────────────────────┘
                       ▼
                [Pretendard TTF 자산]
```

### 2.2 Data Flow

```
LLM HTML 조각
  → HtmlSanitizePolicy.clean()            (기존, 변경 없음)
  → to_document(html, ...)
      → DocumentCharsetPolicy.extract(html)      # 태그 제외 텍스트의 문자 집합
      → FontSubsetter.subset(font, chars)        # Regular/Bold 각각
      → HtmlFontEmbedder.wrap(html, subsets)     # <html><head><style>@font-face…
      → base64 encode → MCP html_to_pdf
  → PDF bytes (한글 글리프 포함)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `DocumentConversionAdapter` | `HtmlFontEmbedder` (선택 주입) | 변환 직전 폰트 셸 적용 |
| `HtmlFontEmbedder` | `DocumentCharsetPolicy`, `FontSubsetter`, `LoggerInterface` | 셸 조립 |
| `FontSubsetter` | `fontTools.subset`, 폰트 자산 파일 | 글리프 서브셋 · 글리프 존재 검사 |
| `DocumentCharsetPolicy` | 없음 (순수) | HTML → 사용 문자 집합 |
| `WeasyprintConverter` | reportlab `pdfmetrics`, 폰트 자산 | xhtml2pdf 경로 한글 등록 (FR-07) |

---

## 3. Data Model

DB 스키마 변경 없음. 프로세스 내부 값 객체만 정의한다.

### 3.1 Entity Definition

```python
@dataclass(frozen=True)
class EmbeddedFont:
    """서브셋된 폰트 1종 (weight 단위)."""
    family: str          # "Pretendard"
    weight: int          # 400 | 700
    data_uri: str        # "data:font/ttf;base64,AAEAAA..."
    byte_size: int       # 서브셋 결과 크기 (로깅/NFR 검증용)
    missing_chars: tuple[str, ...]   # 원본 폰트에 글리프가 없던 문자


@dataclass(frozen=True)
class FontEmbedResult:
    """wrap() 결과 — 성공/폴백 여부를 호출자가 로깅할 수 있게 함께 반환."""
    html: str
    fonts: tuple[EmbeddedFont, ...]
    applied: bool        # False면 원본 HTML 그대로 (FR-09 폴백)
    reason: str          # applied=False일 때의 사유
```

### 3.2 Entity Relationships

```
FontEmbedResult 1 ──── N EmbeddedFont
EmbeddedFont    1 ──── N missing_chars (경고 로그 대상)
```

### 3.3 Database Schema

해당 없음 — DDL 변경 없음.

---

## 4. API Specification

공개 HTTP API 변경 없음. 내부 인터페이스 계약만 정의한다.

### 4.1 내부 인터페이스

| 대상 | 시그니처 | 비고 |
|------|----------|------|
| `DocumentConversionAdapter.__init__` | `(..., font_embedder=None)` | 기본 `None` → 미주입 시 기존 동작 유지 (하위 호환) |
| `DocumentConversionAdapter.to_document` | `(html, output_format, mcp_tool_id, request_id)` | **시그니처 불변** |
| `HtmlFontEmbedder.wrap` | `(html: str, request_id: str) -> FontEmbedResult` | 순수 변환 + 실패 시 폴백 |
| `DocumentCharsetPolicy.extract_chars` | `(html: str) -> frozenset[str]` | 태그·주석·엔티티 제외한 텍스트의 문자 |
| `FontSubsetter.subset` | `(weight: int, chars: frozenset[str]) -> EmbeddedFont` | 글리프 없는 문자는 `missing_chars`로 반환 |

### 4.2 Detailed Specification

#### `HtmlFontEmbedder.wrap(html, request_id)`

**동작 순서**

1. `enabled=False`거나 폰트 자산이 없으면 → `FontEmbedResult(html=원본, applied=False, reason=...)` + `logger.warning` (FR-09)
2. `DocumentCharsetPolicy.extract_chars(html)` → 사용 문자 집합
3. weight별(`400`, `700`) `FontSubsetter.subset()` 호출
4. `@font-face` CSS + `body { font-family: 'Pretendard', sans-serif }` 조립
5. HTML 형태에 따라 주입 (아래 표)
6. 총 바이트·서브셋 문자 수·missing 문자를 구조화 로그로 기록

**입력 HTML 형태별 주입 규칙 (FR-06)**

| 입력 형태 | 처리 |
|-----------|------|
| 조각 HTML (`<h1>…`) | 전체를 `<html><head>…</head><body>` 셸로 감싼다 |
| `<head>` 있는 완결 HTML | `<head>` 끝에 `<style>`만 삽입 |
| `<html>` 있고 `<head>` 없음 | `<html>` 직후에 `<head><style>…</style></head>` 삽입 |
| 빈 문자열/공백 | 폴백 — 원본 반환, `applied=False` |

**생성되는 CSS (요지)**

```css
@font-face {
  font-family: 'Pretendard';
  font-weight: 400;
  font-style: normal;
  src: url(data:font/ttf;base64,<subset>) format('truetype');
}
@font-face { font-family: 'Pretendard'; font-weight: 700; /* … */ }
html, body, table, th, td, li, p, h1, h2, h3 {
  font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
}
```

> **왜 woff2가 아니라 ttf인가**: woff2 서브셋 출력은 `brotli` 추가 의존을 요구하고, 서브셋 이후에는 압축 이득이 크지 않다. 의존성을 하나 줄이고 WeasyPrint·reportlab 양쪽에서 동일 자산을 재사용하기 위해 TTF로 통일한다.

---

## 5. UI/UX Design

해당 없음 — 백엔드 전용 변경. 사용자에게는 "받은 PDF의 한글이 정상적으로 보인다"로만 드러난다.

---

## 6. Error Handling

### 6.1 Error Code Definition

신규 예외 타입을 만들지 않는다. 폰트 처리 실패는 **예외가 아니라 폴백 + 경고**로 다룬다(FR-09, 사용자 선택: "경고 로그 후 진행").

| 상황 | 처리 | 로그 레벨 | 메시지 키 |
|------|------|-----------|-----------|
| 폰트 자산 파일 없음 | 원본 HTML로 변환 진행 | WARNING | `font asset missing` |
| fontTools 서브셋 실패 | 원본 HTML로 변환 진행 | WARNING | `font subset failed` |
| 일부 문자 글리프 없음 | 나머지는 정상 임베드, 진행 | WARNING | `font glyph missing` (+ 문자 목록) |
| 서브셋 결과가 임계 초과 | 임베드는 하되 경고 | WARNING | `font payload exceeded` |
| `DOCUMENT_FONT_EMBED_ENABLED=false` | 원본 HTML로 변환 진행 | INFO | `font embed disabled` |
| MCP 변환 실패 | 기존 `McpConversionError` 그대로 | ERROR | (기존) |

### 6.2 Error Response Format

기존 `McpConversionError` 경로 불변 — 폰트 처리는 사용자 노출 에러를 새로 만들지 않는다.

---

## 7. Security Considerations

| 항목 | 판단 |
|------|------|
| 신규 외부 통신 | 없음 — 폰트는 저장소 내 자산, data URI로 인라인 (외부 fetch 없음) |
| 사용자 입력이 CSS에 삽입되는가 | 아니오 — 주입되는 CSS는 전부 코드가 만든 상수 + base64 폰트 |
| HTML 인젝션 | 기존 `HtmlSanitizePolicy.clean()` 유지. 셸은 sanitize **이후** 단계에서 씌우므로 정제 우회 없음 |
| 라이선스 | Pretendard = SIL OFL 1.1 → 임베드·재배포 허용. `OFL.txt` 동봉 필수 |
| 페이로드 팽창을 통한 DoS | 서브셋 + 크기 로깅·경고로 완화. 입력 HTML 자체는 기존 `llm_input_max_chars`로 이미 제한됨 |

---

## 8. Test Plan

### 8.1 Test Scope

TDD 필수(`idt/CLAUDE.md` §1). 모든 항목은 테스트 선작성 → 실패 확인 → 구현 순서로 진행한다.

| 레벨 | 범위 | 비고 |
|------|------|------|
| L1 (unit) | 정책 · 서브셋 · 임베더 · 어댑터 연동 | 본 기능의 주 검증 축 |
| L2 (integration) | pdf_export 라우터 경유 PDF 생성 → 글리프 검사 | MCP 없이 검증 가능한 유일한 실경로 |
| L3 (E2E) | 실제 MCP 도구를 태운 문서 생성 | 수동/PoC — MCP 등록 환경에서만 |

### 8.2 L1: Unit Test Scenarios

| ID | 대상 | 시나리오 | 기대 |
|----|------|----------|------|
| U-01 | `DocumentCharsetPolicy` | `<h1>위기</h1><p>보고서</p>` | `{'위','기','보','고','서'}` — 태그명 문자 미포함 |
| U-02 | `DocumentCharsetPolicy` | HTML 엔티티(`&amp;`)·주석 포함 | 엔티티 원문 문자·주석 내용 제외 |
| U-03 | `FontSubsetter` | 한글 10자 서브셋 | `byte_size` > 0, `missing_chars` 비어 있음 |
| U-04 | `FontSubsetter` | 폰트에 없는 희귀 한자 포함 | 예외 없이 `missing_chars`에 해당 문자 |
| U-05 | `HtmlFontEmbedder` | 조각 HTML 입력 | `<html>`·`@font-face`·`data:font/ttf;base64,` 포함, `applied=True` |
| U-06 | `HtmlFontEmbedder` | `<head>` 있는 완결 HTML | 셸 중복 없이 `<style>`만 삽입 (FR-06) |
| U-07 | `HtmlFontEmbedder` | 폰트 자산 경로가 없음 | 원본 HTML 반환, `applied=False`, WARNING 1회 |
| U-08 | `HtmlFontEmbedder` | 서브셋 중 예외 발생(주입) | 원본 HTML 반환, 예외 전파 없음 (FR-09) |
| U-09 | `HtmlFontEmbedder` | 오버헤드 계측 | 일반 문서 기준 ≤ 300ms (NFR) |
| U-10 | `DocumentConversionAdapter` | embedder 주입 시 `to_document` | MCP에 전달된 base64를 디코드하면 `@font-face` 포함 |
| U-11 | `DocumentConversionAdapter` | embedder 미주입(`None`) | 기존 동작 그대로 (하위 호환) |
| U-12 | `DocumentConversionAdapter` | `to_html` / `to_pdf_from_pptx` | 폰트 임베드가 적용되지 **않음** (역방향·PPTX 무관) |
| U-13 | 페이로드 | 한글 2000자 문서 | 증가분 ≤ 200KB (NFR) |

### 8.3 L2: Integration Test Scenarios

| ID | 시나리오 | 기대 |
|----|----------|------|
| I-01 | `WeasyprintConverter.convert()`에 한글 HTML 투입 | 결과 PDF의 한글 .notdef 비율 0% (FR-07) |
| I-02 | I-01 결과 PDF의 `/BaseFont` | 한글 폰트명 포함 (DejaVu/Vera 단독 아님) |

### 8.4 L3: Manual / PoC Scenarios

| ID | 시나리오 | 기대 |
|----|----------|------|
| E-01 | 실제 MCP `html_to_pdf` 도구에 임베드 HTML 투입 | .notdef 0% — **Plan §5 최대 리스크(WeasyPrint의 data URI 수용 여부) 선검증** |
| E-02 | `to_pdf_from_pptx` 산출물 진단 | 깨짐 여부 기록 (FR-10, 수정은 범위 밖) |

### 8.5 검증 유틸 — PDF 글리프 검사기

`tests/support/pdf_glyph_check.py` (신규):

```python
def notdef_ratio(pdf_bytes: bytes) -> float:
    """PDF의 Encoding CMap(code→CID)에서 CID 0(.notdef) 비율을 계산한다.

    2026-09-04 test.pdf 진단에 사용한 방법을 자동화한 것.
    - stream 을 zlib 해제 → `begincidchar` 블록 파싱 → CID 0 개수 / 전체
    """
```

이 유틸은 U/I/E 시나리오 전반의 판정 기준이며, FR-08·FR-10을 동시에 충족한다.

### 8.6 Seed Data Requirements

- 한글 픽스처 HTML 1종 (제목·본문·표·굵은 글씨 포함) → `tests/fixtures/`
- 폰트 자산은 저장소 반입분을 그대로 사용 (테스트용 별도 폰트 없음)

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/document_font/
  policies.py            DocumentCharsetPolicy — HTML → 사용 문자 집합 (순수)
  schemas.py             EmbeddedFont, FontEmbedResult (dataclass)

infrastructure/document_font/
  font_subsetter.py      FontSubsetter — fontTools 서브셋 + 글리프 검사 + 파일 IO
  html_font_embedder.py  HtmlFontEmbedder — 셸/CSS 조립, 폴백, 로깅

infrastructure/document_extractor/
  document_conversion_adapter.py   (수정) to_document 내부에서 embedder 호출

infrastructure/pdf_export/
  weasyprint_converter.py          (수정) reportlab 폰트 등록 + CSS 주입

resources/fonts/
  Pretendard-Regular.ttf, Pretendard-Bold.ttf, OFL.txt
```

### 9.2 Dependency Rules

- `domain/document_font` → 외부 의존 **0** (fontTools·파일시스템 접근 금지)
- `infrastructure/document_font` → domain 참조 허용
- `application/` 변경 없음 — UseCase 흐름은 그대로
- `interfaces/` 변경 없음

### 9.3 File Import Rules

| From | To | 허용 |
|------|----|:----:|
| `infrastructure/document_font` | `domain/document_font` | ✅ |
| `domain/document_font` | `fontTools`, `pathlib` | ❌ |
| `infrastructure/document_extractor` | `infrastructure/document_font` | ✅ |
| `domain/*` | `infrastructure/*` | ❌ (CLAUDE.md §6) |

### 9.4 This Feature's Layer Assignment

| 책임 | 레이어 | 근거 |
|------|--------|------|
| 사용 문자 추출 규칙 | domain | 외부 의존 없는 순수 규칙 |
| 값 객체 정의 | domain | 레이어 간 전달 계약 |
| 폰트 파일 읽기·서브셋 | infrastructure | 외부 라이브러리·IO |
| CSS/셸 문자열 조립 | infrastructure | 렌더러(WeasyPrint) 특성에 종속 |
| 변환 시점 주입 | infrastructure (adapter) | 외부 시스템 호출 경계 |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

- 모듈·함수: `snake_case`, 클래스: `PascalCase` (기존 관례 유지)
- 정책 클래스는 `~Policy`, 어댑터는 `~Adapter`, 순수 변환기는 `~er`(`FontSubsetter`, `HtmlFontEmbedder`)

### 10.2 Import Order

표준 라이브러리 → 서드파티(`fontTools`) → `src.domain` → `src.infrastructure` (기존 파일 관례 준수)

### 10.3 Environment Variables

| Variable | 기본값 | 의미 |
|----------|--------|------|
| `DOCUMENT_FONT_EMBED_ENABLED` | `true` | 폰트 임베드 온/오프 (사고 시 즉시 차단용) |
| `DOCUMENT_FONT_FAMILY` | `Pretendard` | 임베드 폰트 패밀리명 |
| `DOCUMENT_FONT_DIR` | `resources/fonts` | 폰트 자산 디렉토리 |
| `DOCUMENT_FONT_MAX_EMBED_KB` | `200` | 초과 시 경고 로그(차단 아님) |

`src/config.py`에 위 4개를 추가한다. 하드코딩 금지 규칙(CLAUDE.md §3) 준수.

### 10.4 This Feature's Conventions (Plan §8.2 확정)

| 항목 | 확정 내용 |
|------|-----------|
| 폰트 자산 위치 | `resources/fonts/` (저장소 루트 기준), 패키징 시 포함 |
| 라이선스 표기 | 동일 디렉토리에 `OFL.txt` 원문 동봉 |
| 페이로드 로깅 필드 | `font_bytes`, `subset_chars`, `missing_chars`, `payload_bytes` |
| PDF 검증 유틸 위치 | `tests/support/pdf_glyph_check.py` (테스트 전용, 프로덕션 코드 아님) |
| 로깅 | `LoggerInterface` 경유 구조화 로그, `print()` 금지 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
신규
  src/domain/document_font/__init__.py
  src/domain/document_font/policies.py
  src/domain/document_font/schemas.py
  src/infrastructure/document_font/__init__.py
  src/infrastructure/document_font/font_subsetter.py
  src/infrastructure/document_font/html_font_embedder.py
  resources/fonts/Pretendard-Regular.ttf
  resources/fonts/Pretendard-Bold.ttf
  resources/fonts/OFL.txt
  tests/support/pdf_glyph_check.py
  tests/domain/document_font/test_policies.py
  tests/infrastructure/document_font/test_font_subsetter.py
  tests/infrastructure/document_font/test_html_font_embedder.py
  tests/infrastructure/pdf_export/test_korean_glyph.py
  tests/fixtures/korean_document.html

수정
  src/infrastructure/document_extractor/document_conversion_adapter.py   # to_document 주입
  src/infrastructure/pdf_export/weasyprint_converter.py                  # FR-07
  src/api/main.py                                                        # DI 2곳 (L882, L2719)
  src/config.py                                                          # 설정 4개
  pyproject.toml                                                         # fonttools
  tests/infrastructure/document_extractor/…                              # 어댑터 테스트 보강
```

### 11.2 Implementation Order

1. [ ] `pyproject.toml`에 `fonttools` 추가, Pretendard 자산 + `OFL.txt` 반입
2. [ ] `tests/support/pdf_glyph_check.py` 작성 — **먼저 만들어 현재 test.pdf로 검증기 자체를 검증** (실측 149/172가 재현되어야 함)
3. [ ] U-01·U-02 테스트 → `DocumentCharsetPolicy` 구현
4. [ ] U-03·U-04 테스트 → `FontSubsetter` 구현
5. [ ] U-05~U-09 테스트 → `HtmlFontEmbedder` 구현
6. [ ] U-10~U-13 테스트 → `to_document` 주입 + DI 배선 2곳
7. [ ] I-01·I-02 테스트 → `WeasyprintConverter` 폰트 등록 (FR-07)
8. [ ] E-01 PoC 수동 실행 — MCP 실경로 확인
9. [ ] E-02 pptx→pdf 진단 결과 기록 (FR-10)
10. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 실행

> **주의**: 단계 8(E-01)이 실패하면 — 즉 MCP의 WeasyPrint가 data URI `@font-face`를 거부하면 — 클라이언트 측 해법이 전부 무의미해진다. Plan §5의 최고 리스크이므로, 여유가 있다면 **단계 1~2 직후 최소 HTML로 E-01을 먼저 때려보는 것**을 권한다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 자산·검증기 | `module-1` | fonttools 의존성, Pretendard+OFL 반입, `pdf_glyph_check` (구현순서 1~2) | 10-15 |
| 폰트 임베드 코어 | `module-2` | 정책·서브셋·임베더 (구현순서 3~5) | 30-40 |
| 변환 경로 적용 | `module-3` | 어댑터 주입·DI 배선·pdf_export (구현순서 6~7) | 25-35 |
| 실경로 검증 | `module-4` | E-01 PoC, E-02 진단, verify 스킬 (구현순서 8~10) | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 40-55 |
| Session 3 | Do | `--scope module-3,module-4` | 40-55 |
| Session 4 | Check + Report | 전체 | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-04 | 최초 작성 — Option C(어댑터 일괄 주입) 선택, Pretendard 확정, 글리프 누락 시 경고 후 진행 정책 확정 | 배상규 |
