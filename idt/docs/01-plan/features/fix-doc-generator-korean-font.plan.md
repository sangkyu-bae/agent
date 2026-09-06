# fix-doc-generator-korean-font Planning Document

> **Summary**: MCP html→pdf 변환 결과에서 한글이 전부 .notdef(□)로 깨지는 문제를, 변환 요청 HTML에 한글 웹폰트를 자체 임베드해 해결한다.
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-04
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 문서 생성 모듈이 만든 PDF에서 한글이 전부 빈 네모(□)로 나온다. 변환을 담당하는 외부 MCP 서버(WeasyPrint 69)에 한글 폰트가 없어 DejaVu Serif로 폴백하고, 한글 코드가 전부 GID 0(.notdef)로 매핑되기 때문이다. |
| **Solution** | 우리 백엔드가 MCP로 보내는 HTML에 **한글 폰트를 `@font-face` + base64 data URI로 임베드**한 문서 셸을 씌운다. 서버 환경에 의존하지 않는 self-contained 변환을 만든다. |
| **Function/UX Effect** | 사용자가 받는 생성 문서·양식 문서 PDF에서 한글이 정상 렌더링된다. 다운로드/미리보기 첨부가 실제로 읽을 수 있는 산출물이 된다. |
| **Core Value** | "문서를 만들어 준다"는 기능이 실제로 쓸 수 있는 결과물을 내놓는다 — 현재는 사실상 전 산출물이 사용 불가 상태다. |

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

### 1.1 Purpose

문서 생성(document_generator)·양식 채우기(document_extractor)가 만든 PDF에서 한글이 렌더링되지 않는 문제를 해결한다. 외부 MCP 변환 서버를 수정할 수 없다는 제약 아래, **클라이언트(우리 백엔드) 쪽에서만** 완결되는 해법을 채택한다.

### 1.2 Background

`samples/test.pdf`(2026-09-04 생성)를 바이너리 분석한 결과:

| 관측 항목 | 실측값 |
|---|---|
| `/Producer` | WeasyPrint 69.0 (우리 `pdf_export`의 xhtml2pdf 아님 → MCP 변환 서버 산출물) |
| 임베드 폰트 | `KTGASA+DejaVu-Serif-Bold`, `BAWKYD+DejaVu-Serif`, `RJOZZM+DejaVu-Serif-Oblique` |
| Encoding CMap (코드→GID) | 172중 149 / 302중 265 / 75중 58 이 **GID 0(.notdef)** |
| ToUnicode CMap | 한글 정상 (`<0db2> <c704>` = '위' 등) |

즉 **텍스트 레이어는 멀쩡하고 글리프만 없다.** DejaVu Serif에 한글 글리프가 없어서 생긴 전형적 tofu 증상이며, 영문·숫자는 정상 출력된다.

폰트가 지정되지 않는 원인은 코드 경로 전체에 폰트 지정 지점이 하나도 없기 때문이다:

1. `src/domain/document_generator/policies.py:120-121` — 프롬프트 규칙 5가 `style` 태그를 금지 → 생성 HTML에 `font-family` 없음.
2. `src/domain/document_extractor/policies.py:186` `HtmlSanitizePolicy.clean()` — 위험 태그 제거만, 문서 셸(`<head><style>`)을 씌우지 않음.
3. `src/infrastructure/document_extractor/document_conversion_adapter.py:71` `to_document()` — `to_html()`과 달리 `options` 파라미터조차 없이 base64 HTML만 전송.
4. 서버 측 — font-family가 없으니 기본 serif 폴백 → 컨테이너에 CJK 폰트 미설치 → DejaVu Serif.

참고로 `src/config.py:183`의 `blueprint_default_font="NanumGothic"`과 `src/infrastructure/blueprint/fonts.py`의 한글 폰트 매핑은 **blueprint(PPTX) 전용**이며 이 경로는 타지 않는다.

### 1.3 Related Documents

- 원인 분석: 본 문서 §1.2 (2026-09-04 세션 실측)
- 관련 아카이브: `docs/archive/2026-08/doc-generator/`
- 규칙: `idt/CLAUDE.md`, `idt/docs/rules/testing.md`, `idt/docs/rules/logging.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 한글 폰트 자산(OFL 라이선스) 도입 + 저장소 반입 및 라이선스 표기
- [ ] 문서 셸(`<html><head><meta charset><style>@font-face…`) 생성 유틸 신설 — 변환 직전 HTML을 감싸는 공통 지점
- [ ] 사용 문자 기반 **폰트 서브셋팅**(문서에 실제 등장하는 글자만) — 페이로드 최소화
- [ ] `document_generator` 적용 (`generator.py`가 `to_document()` 호출하기 직전)
- [ ] `document_extractor` / `composer` 적용 (동일 어댑터 경로 공유)
- [ ] `pdf_export`(xhtml2pdf) 경로 점검 및 한글 폰트 등록 — 별도 렌더러이므로 별도 조치 필요
- [ ] 회귀 방지 스모크 테스트 — 생성 PDF의 .notdef 비율 검사
- [ ] `blueprint pptx→pdf` 경로 **진단** — 실제 깨짐 여부 확인 및 결과 기록

### 2.2 Out of Scope

- MCP 변환 서버(Doc Convert) 컨테이너/이미지 수정, 폰트 설치 — 통제권 없음(사용자 확인)
- WeasyPrint → 다른 변환 엔진으로의 교체
- `blueprint pptx→pdf`의 **수정** — PPTX 바이너리에 폰트를 임베드하는 것은 python-pptx로 표준 지원되지 않으므로 이번 사이클에서는 진단·경고까지만 (§5 리스크 참조)
- 문서 디자인/타이포그래피 개선(줄간격, 표 스타일 등) — 폰트 렌더링 정상화만 목표
- LLM 프롬프트에 style 태그 허용 — 규칙 5는 그대로 유지하고 셸은 코드가 책임진다

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 한글 웹폰트(OFL) 자산을 저장소에 포함하고 라이선스 파일을 함께 둔다 | High | Pending |
| FR-02 | HTML 문자열을 받아 `@font-face`(base64 data URI) + `font-family` 지정 문서 셸로 감싸는 공통 유틸을 제공한다 | High | Pending |
| FR-03 | 임베드 폰트는 입력 HTML에 실제 등장하는 문자만 포함하도록 런타임 서브셋팅한다 | High | Pending |
| FR-04 | `document_generator.generate()`가 `to_document()` 호출 전 FR-02 셸을 적용한다 | High | Pending |
| FR-05 | `document_extractor`/`composer`의 html→doc 변환에도 동일 셸을 적용한다 | High | Pending |
| FR-06 | 이미 완결 HTML(`<html>`/`<head>` 포함)이 들어와도 셸이 중복되지 않고 style이 주입된다 | Medium | Pending |
| FR-07 | `pdf_export`(xhtml2pdf) 경로에 한글 폰트를 등록해 동일 증상이 없도록 한다 | Medium | Pending |
| FR-08 | 생성된 PDF의 .notdef(GID 0) 매핑 비율을 검사하는 검증 유틸 + 테스트를 제공한다 | Medium | Pending |
| FR-09 | 폰트 자산 누락·서브셋 실패 시 변환을 중단하지 않고 경고 로그를 남기고 원본 HTML로 진행한다 | Medium | Pending |
| FR-10 | `blueprint pptx→pdf` 산출물의 한글 깨짐 여부를 FR-08 유틸로 진단하고 결과를 기록한다 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Payload | 서브셋 폰트 base64 포함 시 요청 증가분 ≤ 200KB (일반 문서 기준) | 변환 요청 바이트 수 로깅 |
| Performance | 셸 생성 + 서브셋팅 오버헤드 ≤ 300ms | 유닛 테스트 내 계측 |
| Reliability | 폰트 처리 실패가 문서 생성 전체 실패로 번지지 않음 (FR-09) | 예외 주입 테스트 |
| License | 재배포 가능한 오픈 라이선스(SIL OFL) 폰트만 사용, 라이선스 원문 동봉 | 저장소 파일 확인 |
| Architecture | domain 레이어에 폰트 파일/IO 의존 없음 (Thin DDD 준수) | `/verify-architecture` |
| Logging | 폰트 임베드 성공/실패·서브셋 글자수를 구조화 로그로 남김 (print 금지) | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-09 구현 완료 (FR-10은 진단 결과 기록으로 충족)
- [ ] 한글이 포함된 문서를 생성했을 때 결과 PDF의 한글 .notdef 비율 **0%**
- [ ] 결과 PDF의 `/BaseFont`에 한글 폰트명이 등장 (DejaVu 단독 아님)
- [ ] TDD 준수 — 각 기능에 대해 테스트 선작성 후 구현
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 폰트 라이선스 표기 완료

### 4.2 Quality Criteria

- [ ] 신규 모듈 유닛 테스트 통과, 기존 document_generator/extractor 테스트 무회귀
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수
- [ ] 변환 페이로드 증가분 측정치가 NFR 기준 이내임을 테스트로 확인

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| base64 폰트로 페이로드가 커져 MCP 변환이 실패/타임아웃 | High | Medium | 사용 문자 기반 서브셋팅(FR-03)으로 수십 KB 수준 유지, 요청 크기 로깅 후 임계 초과 시 경고 |
| MCP 서버의 WeasyPrint가 data URI `@font-face`를 차단(리소스 정책) | High | Low | PoC로 먼저 검증(§9 Next Steps 2) — 실패 시 남는 선택지는 서버 폰트 설치뿐이므로 즉시 에스컬레이션 |
| 서브셋팅 라이브러리(fonttools) 신규 의존성 추가 필요 | Medium | High | `fonttools[woff]`를 pyproject에 명시, 서브셋 실패 시 전체 폰트 임베드로 폴백 |
| `blueprint pptx→pdf`는 클라이언트 CSS 주입이 불가능해 동일 방식으로 못 고침 | Medium | High | 이번 범위는 진단·경고까지(§2.2). 실제 깨짐이 확인되면 별도 feature로 분리 |
| 서브셋 폰트가 특정 한자/기호를 놓쳐 일부 문자만 깨짐 | Medium | Medium | 서브셋 문자 집합을 입력 HTML 전체 문자에서 추출 + 스모크 테스트로 .notdef 0% 검증 |
| xhtml2pdf 경로는 렌더러가 달라 동일 해법이 그대로 적용되지 않음 | Low | High | FR-07을 별도 항목으로 분리, reportlab 폰트 등록 방식으로 처리 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 신규 폰트 임베드 유틸 (위치는 Design에서 확정) | Module | HTML 문서 셸 생성 + 폰트 서브셋 + base64 임베드 |
| `src/infrastructure/document_generator/generator.py` | Module | `to_document()` 호출 전 셸 적용 |
| `src/infrastructure/document_extractor/composer.py` | Module | 동일 셸 적용 |
| `src/infrastructure/pdf_export/weasyprint_converter.py` | Module | 한글 폰트 등록(xhtml2pdf/reportlab) |
| 폰트 자산 + 라이선스 파일 | Asset | 신규 반입 |
| `pyproject.toml` | Config | `fonttools` 의존성 추가 |
| `src/config.py` | Config | 폰트 패밀리·임베드 스위치 설정값 추가 (§8.3) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `DocumentConversionAdapter.to_document` | CONVERT | `document_generator/generator.py:80` (문서 생성) | 개선 — 셸 적용 대상 |
| `DocumentConversionAdapter.to_document` | CONVERT | `document_extractor/composer.py` (양식 슬롯 채우기) | 개선 — 셸 적용 대상 |
| `DocumentConversionAdapter.to_pdf_from_pptx` | CONVERT | blueprint 골든샘플 경로 | 진단만 — 변경 없음 |
| `DocumentConversionAdapter.to_html` | CONVERT | `document_extractor` 추출 경로 | 영향 없음(역방향) |
| `WeasyprintConverter.convert` | CONVERT | `src/api/main.py:4735` (`/pdf-export` 라우터) | FR-07 대상 |
| 첨부 저장 (`attachment_store.save`) | CREATE | generator/composer 산출물 | 영향 없음(바이트만 달라짐) |

### 6.3 Verification

- [ ] generator/composer 기존 테스트가 셸 적용 후에도 통과
- [ ] 어댑터 페이로드 계약(`{"arguments": {"source": …}}`) 불변 확인
- [ ] 첨부 파일 크기 증가가 저장소/응답 제한을 넘지 않음 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 웹앱 MVP | ☐ |
| **Enterprise** | 레이어 분리, DI | 본 프로젝트(Thin DDD) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 폰트 공급 위치 | 서버 설치 / 클라이언트 임베드 | **클라이언트 임베드** | MCP 서버 통제 불가(사용자 확인) |
| 임베드 방식 | 링크 URL / base64 data URI | **base64 data URI** | 변환 서버가 외부 네트워크를 못 탈 수 있음, self-contained 보장 |
| 폰트 범위 | 전체 폰트 / 사용 문자 서브셋 | **사용 문자 서브셋** | 페이로드 리스크 완화(§5), NFR 200KB 충족 |
| 셸 주입 지점 | LLM 프롬프트 / sanitize 정책 / 변환 직전 | **변환 직전(infrastructure)** | 프롬프트 규칙 5(style 금지) 유지, 도메인 정책 오염 방지 |
| 적용 계층 | 어댑터 내부 일괄 / 호출자별 | Design 단계에서 확정 | 어댑터 일괄이면 중복 제거, 호출자별이면 제어 유연 — 3안 비교 대상 |
| 폰트 선택 | Noto Sans KR / 나눔고딕 | Design 단계에서 확정 | 둘 다 OFL, 파일 크기·가독성 비교 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

domain/          폰트 정책(글자 집합 추출 규칙, 기본 패밀리명) — 순수 로직만
application/     변경 없음 (UseCase 흐름 유지)
infrastructure/  폰트 파일 IO · 서브셋팅 · base64 · HTML 셸 생성 · 어댑터 연동
interfaces/      변경 없음
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`에 코딩 규칙 존재 (idt/CLAUDE.md)
- [x] `docs/rules/testing.md`, `docs/rules/logging.md` 존재
- [x] TDD 필수 규칙 명시 (테스트 선작성)
- [ ] 바이너리 자산(폰트) 반입 규칙 — 정의 필요

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 폰트 자산 위치 | missing | 표준 경로(예: `resources/fonts/`)와 패키징 포함 규칙 | High |
| 라이선스 표기 | missing | OFL 원문 동봉 위치 및 NOTICE 표기 | High |
| 변환 페이로드 로깅 | 부분 존재 | 요청 바이트 수·서브셋 글자수 로그 필드 | Medium |
| PDF 검증 유틸 위치 | missing | `tests/` 헬퍼 vs 프로덕션 유틸 구분 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `DOCUMENT_FONT_FAMILY` | 임베드할 한글 폰트 패밀리명(기본값 존재) | Server | ☐ |
| `DOCUMENT_FONT_EMBED_ENABLED` | 임베드 온/오프 스위치(문제 시 즉시 비활성화) | Server | ☐ |
| `DOCUMENT_GENERATOR_HTML_TO_DOC_TOOL_ID` | 기존 변환 도구 지정 | Server | ☑ (기존) |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 (Schema) | N/A | — | DB 스키마 변경 없음 |
| Phase 2 (Convention) | ☐ | §8.2 항목 확정 필요 | — |

---

## 9. Next Steps

1. [ ] `/pdca design fix-doc-generator-korean-font` — 3가지 아키텍처 안 비교(어댑터 일괄 주입 vs 호출자별 주입 vs 정책+어댑터 분리)
2. [ ] PoC: 서브셋 폰트를 `@font-face` data URI로 임베드한 HTML을 실제 MCP 도구에 태워 .notdef 0% 확인 (§5 최대 리스크 선검증)
3. [ ] Design 승인 후 `/pdca do` 로 구현 착수 (TDD)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-04 | 최초 작성 — test.pdf 바이너리 실측 기반 원인 규명 및 클라이언트 임베드 방침 확정 | 배상규 |
