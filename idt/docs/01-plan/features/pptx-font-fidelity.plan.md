# pptx-font-fidelity Planning Document

> **Summary**: 블루프린트 기반 PPTX 생성 시 골든 샘플의 폰트·소제목·헤더 스타일이 깨지는 문제를 원인 4가지(폰트명 미정규화 / 한글 ea 폰트 미설정 / 소제목 계층 소실 / 헤더 타이틀 누락) 기준으로 복원한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt v0.x (blueprint 모듈)
> **Author**: 배상규
> **Date**: 2026-08-24
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 골든 샘플(PDF)에서 추출한 블루프린트로 PPTX를 생성하면 목차·헤더·소제목·본문의 폰트와 스타일이 원본과 다르게(깨져) 렌더된다. 폰트명이 PDF 서브패밀리명 그대로 들어가고, 한글 폰트 슬롯(`a:ea`)이 비어 있으며, 소제목 계층이 본문 bullets로 평탄화된다. |
| **Solution** | ① 폰트명 정규화(서브패밀리 접미사 제거 + 별칭 매핑 보강), ② 렌더러에서 `a:latin`+`a:ea`(+`a:cs`) 동시 설정, ③ SlotContent에 heading 필드를 추가해 소제목을 h3 스타일로 렌더, ④ 본문 슬라이드 타이틀 누락 방지 폴백. |
| **Function/UX Effect** | 생성된 PPTX가 PowerPoint에서 폰트 대체 없이 골든 샘플과 동일한 서체·크기·색·계층으로 열린다. 소제목("핵심 관찰" 류)이 원본처럼 강조 표시된다. |
| **Core Value** | 블루프린트 기능의 핵심 가치인 "원본 문서 스타일 재현"의 신뢰도 확보 — P2(에이전트 소유자)가 결과물을 그대로 보고용으로 쓸 수 있다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 생성 PPTX의 폰트·스타일이 골든 샘플과 달라 산출물을 실무 보고에 쓸 수 없음 |
| **WHO** | P2 (KB 운영자/에이전트 소유자) — 블루프린트로 보고서 PPTX를 생성하는 사용자 |
| **RISK** | python-pptx가 `a:ea` 설정 API를 제공하지 않아 lxml 직접 조작 필요 → 회귀 위험은 렌더러 단위 테스트로 통제 |
| **SUCCESS** | 골든 샘플 재생성 시 폰트명이 실존 패밀리명으로 기록되고(`a:latin`=`a:ea`), 소제목·헤더가 원본 계층대로 출력, 기존 테스트 전부 통과 |
| **SCOPE** | 렌더러(infrastructure) + FontCatalog + SlotContent 스키마(domain) + 슬롯 작성 프롬프트. 추출 파이프라인(크기·색 추출)은 변경 없음 |

---

## 1. Overview

### 1.1 Purpose

블루프린트 PPTX 생성 결과물의 텍스트 스타일(폰트·소제목·헤더)을 골든 샘플 원본과 시각적으로 일치시킨다.

### 1.2 Background

`samples/golden_sample_report.pdf`(원본)와 `samples/5ba85b0d5aac4e8fab99b96ca6ca2401.pptx`(생성본)를 비교 분석한 결과, 크기(34/24/16/13pt)·색(#1F3A5F 등)·좌표는 정확히 재현되지만 다음 4가지가 깨진다:

| # | 원인 | 근거 (조사 완료) |
|---|------|------|
| A | **폰트명 미정규화** — `"Malgun Gothic Regular"`, `"Malgun Gothic Bold"`는 pymupdf가 반환하는 PDF 서브패밀리명으로, 실존 폰트 패밀리명("맑은 고딕"/"Malgun Gothic")이 아님. PowerPoint가 폰트를 찾지 못해 대체 렌더 | 생성 PPTX XML `<a:latin typeface="Malgun Gothic Regular"/>`; `fonts.py::suggest()`는 `"bold"` 접미사만 제거하고 `"regular"`는 처리 안 함; `blueprint_font_dir` 기본값 `""` → installed 빈 튜플 → 매핑 전건 실패("kept as-is" 경고) |
| B | **한글 `a:ea` 폰트 미설정** — python-pptx `run.font.name`은 `<a:latin>`만 설정. 한글 글리프는 East Asian 슬롯을 따르므로 지정 폰트가 한글에 적용되지 않고 테마 기본값으로 폴백 | `pptx_renderer.py:290` (`_textbox`), `:319` (`_style_cell`); 생성 XML rPr에 `<a:ea>` 부재 확인 |
| C | **소제목 계층 소실** — 원본의 "핵심 관찰"(16pt bold #1F3A5F), "심사 기준 강화"(15pt bold) 같은 소제목이 생성본에서 13pt 일반 bullets로 평탄화 | `SlotKind`에 소제목 개념 없음; `SizeHierarchyPolicy`가 h3/subtitle 크기를 추출해도 목차(`_bullets` TOC 분기)에서만 사용 |
| D | **본문 헤더 타이틀 누락** — 생성본 3번 슬라이드는 24pt 섹션 헤더 없이 본문부터 시작, 8번 슬라이드는 푸터/로고만 있는 빈 슬라이드 | 셰이프 덤프로 확인; title 슬롯 내용이 없으면 `_render_slot`이 조용히 건너뜀 (`content is None` / `text is None`) |

### 1.3 Related Documents

- 선행 feature: `blueprint-style-fidelity` (docs/archive — 장식·z-order·푸터 재현), `golden-sample-blueprint` (추출 파이프라인)
- 비교 샘플: `samples/golden_sample_report.pdf`, `samples/5ba85b0d5aac4e8fab99b96ca6ca2401.pptx`
- 규칙: `idt/CLAUDE.md` (Thin DDD, TDD 필수), `docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **FR-01 폰트명 정규화**: PDF 서브패밀리 접미사(`Regular`/`Bold`/`Light`/`SemiBold`/`Medium` 등) 제거 후 패밀리명으로 정규화, `_FAMILY_ALIASES` 매칭 보강 (FontCatalog 설치 폰트 유무와 무관하게 동작)
- [ ] **FR-02 한글 ea 폰트 설정**: 렌더러의 모든 run(`_textbox`, `_style_cell`)에서 `a:latin`과 동일한 폰트를 `a:ea`(+`a:cs`)에도 설정
- [ ] **FR-03 소제목 heading 필드**: `SlotContent`에 선택적 `heading` 필드 추가 → bullets 슬롯 상단에 h3 크기 + heading 폰트 + primary 색으로 렌더, 슬롯 작성 LLM 스키마/프롬프트에 heading 반영
- [ ] **FR-04 헤더 타이틀 폴백**: content/body 패턴 슬라이드에서 title 슬롯 내용이 비면 슬라이드 계획(SlidePlan)의 제목 등으로 폴백해 24pt 헤더가 항상 출력되도록 함. 빈 슬라이드(내용 슬롯 전무) 생성 방지 또는 degraded 경고
- [ ] 상기 항목 전체 단위 테스트 (TDD Red → Green)

### 2.2 Out of Scope

- 서버 폰트 파일 설치·배포, `BLUEPRINT_FONT_DIR` 운영 구성 (폰트명 정규화만으로 해결 — 사용자 결정)
- `SlotKind.SUBHEADING` 신설 등 추출·분류 LLM 프롬프트의 슬롯 구조 변경 (heading 필드 방식으로 대체 — 사용자 결정)
- 추출 파이프라인의 크기·색·좌표 정책 변경 (`SizeHierarchyPolicy`, `PaletteClusterPolicy` — 정상 동작 확인됨)
- 목차 페이지번호 표기 형식 등 LLM 생성 콘텐츠 문구 자체의 품질
- 차트 내부 폰트 세부 스타일 (`chart_builder`) — 필요 시 후속 feature

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 폰트명 정규화: `"Malgun Gothic Regular"` → `"맑은 고딕"`(또는 `"Malgun Gothic"`) 등 서브패밀리 접미사를 제거한 실존 패밀리명을 blueprint `font_mapping`에 기록. Bold 계열은 패밀리명 + `bold=True` 속성으로 표현 | High | Pending |
| FR-02 | 렌더러가 생성하는 모든 텍스트 run의 rPr에 `<a:latin>`·`<a:ea>`(·`<a:cs>`)를 동일 타입페이스로 설정 (텍스트박스·표 셀 포함) | High | Pending |
| FR-03 | `SlotContent.heading: str \| None` 추가. bullets 슬롯 렌더 시 heading이 있으면 첫 문단을 h3 크기·heading 폰트·bold·primary 색으로 출력. 슬롯 작성 LLM 출력 스키마에 heading 필드 추가(하위호환: 없으면 기존 동작) | High | Pending |
| FR-04 | 비표지 콘텐츠 슬라이드에서 title 슬롯 내용 부재 시 SlidePlan 제목으로 폴백 렌더. 렌더 가능한 내용이 전무한 슬라이드는 생성을 건너뛰고 warnings에 기록 | Medium | Pending |
| FR-05 | 기존 v1 블루프린트(heading 필드 없는 직렬화 데이터) 로드 시 무결성 유지 (serialization 하위호환) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 기존 저장 블루프린트(JSON) 역직렬화 무결 | `serialization` 단위 테스트 |
| 아키텍처 | Thin DDD 레이어 준수 — 정규화 규칙은 domain 정책 또는 infra FontCatalog, lxml 조작은 infrastructure에만 | `/verify-architecture` |
| 회귀 | 기존 blueprint 렌더러·추출 테스트 전부 통과 | pytest 전체 실행 |
| 코딩 규칙 | 함수 40줄 이하, print 금지, 명시적 타입 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 골든 샘플로 재생성한 PPTX의 rPr XML에서: 타입페이스가 실존 패밀리명이고 `a:latin`=`a:ea`로 설정됨
- [ ] 소제목이 있는 페이지(골든 p4 "핵심 관찰", p6 "심사 기준 강화" 유형)가 h3 스타일 소제목 + 본문 bullets 구조로 렌더됨
- [ ] 모든 비표지 콘텐츠 슬라이드에 24pt 헤더 타이틀이 존재 (또는 의도된 생략이 warnings로 기록)
- [ ] FR-01~05 단위 테스트 작성·통과 (TDD)
- [ ] 기존 테스트 회귀 없음

### 4.2 Quality Criteria

- [ ] 신규/변경 모듈 테스트 커버리지 확보 (renderer·fonts·serialization)
- [ ] lint/타입 오류 0
- [ ] PowerPoint(또는 LibreOffice)에서 육안 확인: 한글 텍스트가 지정 폰트로 렌더, 폰트 대체 경고 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| python-pptx가 `a:ea` 공식 API 미제공 → lxml 직접 조작 필요 | Medium | High | `rPr` 요소 조작을 헬퍼 함수 1곳으로 격리 + XML 검증 단위 테스트 |
| 정규화된 패밀리명이 사용자 환경에 미설치(예: 리눅스 서버에서 변환 시) | Medium | Medium | 정규화는 "실존 가능성이 높은 패밀리명"으로만 변환; 미매핑 시 기존 경고 유지. PDF 변환 경로는 별도 이슈로 관찰 |
| heading 필드 추가로 슬롯 작성 LLM 출력 파싱 실패 증가 | Medium | Low | Optional 필드 + 파싱 실패 시 heading 무시 폴백 (degraded 경고) |
| 직렬화 스키마 변경으로 기존 저장 블루프린트 로드 실패 | High | Low | `data.get("heading")` 방식 하위호환 + 역직렬화 테스트 |
| Bold를 패밀리명+bold 속성으로 바꿀 때 원본이 세미볼드 등 중간 굵기인 경우 표현 손실 | Low | Medium | v1은 bold 이분법 유지, 경고 없이 수용 (골든 샘플 범위 내 충분) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/infrastructure/blueprint/fonts.py` (FontCatalog) | Infra | 서브패밀리 접미사 정규화 로직 추가, `_FAMILY_ALIASES` 보강 |
| `src/infrastructure/blueprint/renderer/pptx_renderer.py` | Infra | `_textbox`·`_style_cell`에 ea/cs 폰트 설정, title 폴백, heading 렌더 |
| `src/domain/blueprint/value_objects.py` (SlotContent) | Domain VO | `heading: str \| None` 필드 추가 |
| `src/domain/blueprint/serialization.py` | Domain | heading 직렬화/역직렬화 (하위호환) |
| `src/infrastructure/blueprint/prompts.py` | Infra | 슬롯 작성 프롬프트에 heading 필드 안내 추가 |
| `src/application/blueprint/generation_use_case.py` | Application | LLM 응답 → SlotContent 매핑에 heading 반영, 빈 슬라이드 스킵/경고 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `FontCatalog.propose_mapping` | READ | `extraction_use_case._assemble` → blueprint.font_mapping | 정규화 결과가 저장 블루프린트에 기록 — 기존 저장본은 재추출 전까지 옛 폰트명 유지 (Needs verification) |
| `FontCatalog.installed/default_font` | READ | `admin_use_case.FontsView` → `admin_blueprint_router` `/fonts` | None (조회 API 형태 불변) |
| `SlotContent` | CREATE/READ | `generation_use_case` (슬롯 작성) → `pptx_renderer.render` | heading Optional 추가 — 생성·렌더 양쪽 동시 수정 (Breaking 방지: Optional) |
| `SlotContent` 직렬화 | READ | `serialization.py` ← DB 저장 블루프린트/실행 이력 | 하위호환 필수 (Needs verification) |
| `PptxSlideRenderer.render` | CALL | `generation_use_case:132` | 시그니처 불변, 내부 동작만 변경 (None) |
| 렌더러 산출 PPTX | READ | `_maybe_pdf` MCP PDF 변환 | 폰트명 변경이 PDF 변환 결과에 영향 — 육안 확인 필요 (Needs verification) |
| 프론트 blueprint 타입 | READ | `idt_front/src/types` (blueprint 관련) | 스키마 응답에 heading 노출 시 `/api-contract-sync` 체크 (Needs verification) |

### 6.3 Verification

- [ ] 기존 저장 블루프린트 역직렬화 테스트 통과
- [ ] `/fonts` 관리 API 응답 불변 확인
- [ ] PDF 변환 경로(output_format=pdf) 육안 확인
- [ ] 프론트 타입 동기화 필요 여부 판정 (heading이 API 응답에 노출되는 경우만)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (기존 idt Thin DDD 구조 유지) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 폰트 해결 방식 | 정규화만 / FONT_DIR 구성 병행 / 고정 기본 폰트 | **폰트명 정규화** | 서버 폰트 설치 없이 해결, 사용자 확정 |
| 소제목 재현 방식 | SlotContent.heading 필드 / SlotKind.SUBHEADING 신설 / 제외 | **heading 필드** | 추출·분류 프롬프트 무변경으로 위험 최소, 사용자 확정 |
| 정규화 위치 | domain 정책 / infra FontCatalog | 설계 단계에서 결정 | domain은 외부 폰트 지식 없음 원칙과 규칙 순수성 사이 트레이드오프 — Design에서 확정 |
| ea 폰트 설정 방식 | lxml 직접 조작 / oxml 헬퍼 | 설계 단계에서 결정 | python-pptx 공식 API 부재 |

### 7.3 Clean Architecture Approach

기존 구조 유지: domain(value_objects, serialization) → application(generation_use_case) → infrastructure(fonts, renderer, prompts). 레이어 이동 없음.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 (40줄 제한, TDD, logger)
- [x] `docs/rules/testing.md` — TDD 절차
- [x] pyproject.toml (ruff/pytest 설정)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| oxml 네임스페이스 조작 | 없음 (첫 사례) | rPr 조작 헬퍼의 위치·네이밍 (Design에서) | High |
| 폰트 정규화 규칙 | `_FAMILY_ALIASES` 존재 | 접미사 목록·한글 패밀리명 우선순위 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음 — 기존 `BLUEPRINT_FONT_DIR`/`BLUEPRINT_DEFAULT_FONT` 그대로) | | | ☐ |

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design pptx-font-fidelity`) — 정규화 규칙 상세, rPr 조작 방식, heading 렌더 레이아웃(소제목-본문 간격) 확정
2. [ ] TDD 구현 (`/pdca do pptx-font-fidelity`)
3. [ ] 골든 샘플 재생성 육안 검증 + Gap 분석 (`/pdca analyze pptx-font-fidelity`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-24 | 최초 작성 — 샘플 비교·코드 분석 기반 원인 4종 진단 및 범위 확정 | 배상규 |
