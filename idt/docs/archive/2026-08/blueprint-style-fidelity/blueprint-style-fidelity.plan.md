# blueprint-style-fidelity Planning Document

> **Summary**: 골든 샘플(PDF)에서 추출한 블루프린트가 원본 스타일을 잃어 PPT 산출물이 "기본 폰트·장식 없음·로고 위치 오류·페이지번호 중복" 상태로 나오는 문제를 추출 정책·렌더러 양쪽에서 고친다.
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-23
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `golden_sample_report.pdf`로 추출한 블루프린트(`document_blueprint.id=3bac89cb…`)로 PPT를 만들면 폰트가 NanumGothic으로 바뀌고, 로고가 표지 좌표(좌상단)로 모든 슬라이드에 찍혀 제목과 겹치며, 페이지번호가 2중으로 나오고, 목차·강조 상자·푸터 띠 등 원본의 시각 규칙이 전혀 재현되지 않는다. |
| **Solution** | (1) 추출 정책의 정보 손실 제거 — 폰트 패스스루, 반복 에셋의 본문 좌표 채택, 원본 푸터 텍스트·배경 띠·강조 상자(채움 도형)·크기 계층(5단) 보존. (2) 렌더러 확장 — 장식 도형 슬롯, 푸터 슬롯 단일화, 목차/소제목 스타일, 정렬·줄간격 적용. (3) 기존 레코드 동일 id로 재추출·갱신. |
| **Function/UX Effect** | 골든 샘플과 동일한 폰트·색·로고 위치·푸터·강조 상자가 재현된 PPT가 나오고, 사용자가 "우리 회사 양식"으로 인지 가능한 수준이 된다. |
| **Core Value** | P2(에이전트 소유자)가 디자이너 없이 샘플 한 장으로 조직 표준 보고서 양식을 에이전트에 이식할 수 있다 — Blueprint 기능의 존재 이유 자체를 충족. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 블루프린트 추출이 폰트·좌표·도형·푸터 정보를 버려서 산출 PPT가 샘플 스타일과 무관해 보인다 |
| **WHO** | P2 KB 운영자/에이전트 소유자 (관리자 화면에서 골든 샘플 등록), 최종 PPT를 받는 에이전트 사용자 |
| **RISK** | 도형 슬롯 추가로 스키마(`blueprint_json`) 버전이 올라가면 기존 레코드 역직렬화 호환이 깨질 수 있음 → schema_version 2 + 기본값 폴백 |
| **SUCCESS** | 재추출 후 생성 PPT에서 ① 폰트명 = Malgun Gothic ② 로고 box = 본문 페이지 좌표(우상단) ③ 슬라이드당 페이지번호 1개 ④ 푸터 텍스트 = 원본 ⑤ 강조 상자·푸터 띠 도형 존재 — 자동 테스트로 검증 |
| **SCOPE** | Phase A 추출 정책(폰트·에셋·푸터·크기·도형) → Phase B 렌더러(도형·푸터·목차·정렬) → Phase C 재추출 스크립트/검증. 샘플 해상도·프론트 UI는 범위 밖 |

---

## 1. Overview

### 1.1 Purpose

`golden-sample-blueprint` 기능(2026-08 아카이브)의 추출→렌더 파이프라인이 원본 시각 정보를 충분히 보존하지 못한다. 본 작업은 **추출 시 손실되는 5가지 정보**를 보존하고 **렌더러가 그 정보를 실제로 사용**하도록 고쳐, 산출 PPT가 골든 샘플과 같은 인상을 주도록 한다.

### 1.2 Background — 원인 진단 (2026-08-23, 실데이터 대조)

DB 레코드 `document_blueprint.id=3bac89cb425a4bb5abffe3759ba460a6`, 원본 `samples/golden_sample_report.pdf`(6p), 산출물 `705d3343c85445a8a85c31a746e96186.pptx`(7장)를 PyMuPDF/python-pptx로 직접 대조한 결과:

| # | 증상 | 원인 | 근거 코드 |
|---|------|------|-----------|
| 1 | 폰트가 NanumGothic(=뷰어 기본 폰트) | 원본 폰트 `Malgun Gothic Bold/Regular`. `BLUEPRINT_FONT_DIR`가 빈 값 → `FontCatalog._installed=()` → `suggest()`가 항상 `None` → 무조건 `blueprint_default_font`(NanumGothic)로 치환. DB `font_mapping`에 `{'Malgun Gothic Bold': 'NanumGothic', …}` 저장됨 | `src/infrastructure/blueprint/fonts.py:56-85`, `src/config.py:158-159` |
| 2 | 로고가 모든 슬라이드 **좌상단**에 찍혀 제목과 겹침 | `RepeatAssetPolicy`가 sha256별 **첫 등장 페이지(표지)** 의 box를 채택. 표지 로고 `(0.06,0.07,0.19,0.11)` vs 본문 로고 `(0.83,0.04,0.12,0.07)`. 렌더러는 표지를 제외한 전 슬라이드에 그 box로 그림 | `src/domain/blueprint/policies.py:199-203`, `pptx_renderer.py::_logo` |
| 3 | 페이지번호 2중 표기 + LLM이 푸터 날조("페이지 3", "페이지 5/7") | 패턴에 `footer` 슬롯이 있어 LLM이 텍스트를 채우고, 렌더러가 추가로 `_PAGE_NUMBER_BOX`에 `{n}/{total}`을 찍음. 원본 푸터 `여신심사부 · 대외비 · 2026년 3분기`는 `footer_text=""`로 버려짐 | `extraction_use_case.py::_style_tokens`, `pptx_renderer.py::_footer`, `_render_slot` |
| 4 | 목차가 13pt 불릿 한 덩어리 | 원본: 16pt, `1. 2. 3.` 번호, 줄 간격 0.09. 크기 계층이 h1/h2/body/caption 4단이라 부제(18)·목차(16)·소제목(15)이 body(13)로 뭉개짐. bullets는 항상 `• ` 접두 + body 크기, 정렬·줄간격·세로 앵커 미적용 | `policies.py::SizeHierarchyPolicy`, `pptx_renderer.py::_render_slot/_textbox` |
| 5 | 강조 상자·푸터 띠·악센트 색 없음 | 채움 도형(`#F2F4F5` 푸터 띠·카드 박스, `#E07A1F` 악센트 라인)은 `_fills()`로 추출되지만 팔레트 추정에만 쓰이고 패턴에 저장되지 않음(`background=None`, 도형 슬롯 없음). 팔레트도 `accent1=#666666`(캡션 회색)으로 잘못 잡힘 | `pdf_style_extractor.py::_fills`, `policies.py::PaletteClusterPolicy`, `extraction_use_case.py::_pattern_from_draft` |
| 6 | 표지 배경 흐림 | 샘플 PDF 자체 임베드 이미지가 192×108px (369B) | 샘플 한계 — **범위 밖** |

### 1.3 Related Documents

- 원 설계: `docs/archive/2026-08/golden-sample-blueprint/golden-sample-blueprint.design.md`
- 원 계획: `docs/archive/2026-08/golden-sample-blueprint/golden-sample-blueprint.plan.md`
- 규칙: `docs/rules/testing.md`, `docs/rules/tool-and-mcp.md`

---

## 2. Scope

### 2.1 In Scope

**Phase A — 추출 정책 (domain/application/infrastructure)**
- [ ] A-1 폰트 패스스루: 설치 폰트 카탈로그가 비어 있거나 매핑 실패 시 **원본 폰트명을 그대로 유지**하고 경고만 남긴다 (NanumGothic 강제 치환 제거)
- [ ] A-2 반복 에셋 좌표: 로고/장식은 **비표지 페이지에서 최빈 box**를 채택 (표지 전용 좌표는 `cover_box`로 별도 보존)
- [ ] A-3 푸터 추출: 하단 밴드(y ≥ 0.9) 반복 텍스트를 `footer_text`로, 페이지번호 패턴(`n / N`)을 `page_number_format`과 그 box로 추출
- [ ] A-4 크기 계층 확장: `h1/h2/h3/subtitle/body/caption` 6단 (distinct size 클러스터 기반, 없으면 보간)
- [ ] A-5 장식 도형 보존: 페이지 채움 사각형(면적 ≥ 0.3%)을 `Decoration(kind=rect, box, fill)`로 패턴에 저장. 반복(≥2p) 도형은 스타일 레벨 `common_decorations`로 승격
- [ ] A-6 팔레트 보정: `accent1`을 캡션 회색이 아닌 **채움 도형 색 중 primary 외 최다**로 선택
- [ ] A-7 `schema_version=2` + 역직렬화 시 v1 레코드 기본값 폴백

**Phase B — 렌더러 (infrastructure/blueprint/renderer)**
- [ ] B-1 장식 도형 렌더 (텍스트/이미지보다 먼저 z-order 하단)
- [ ] B-2 푸터 단일화: 패턴 `footer` 슬롯은 **LLM이 채우지 않고** 스타일의 `footer_text` + `page_number_format`로 렌더러가 채움 (프롬프트에서 footer 제외)
- [x] B-3 역할별 텍스트 스타일: `toc` 패턴 bullets → 번호 리스트·`h3` 크기·1.5 줄간격; 표지 부제 → `subtitle`. **카드 소제목(`h3` bold primary)은 후속으로 descope** (v0.2, Check G1 — bullets 슬롯이 평문 리스트라 소제목/본문 쌍 표현에 LLM 출력 스키마 확장 필요, DR-7 과 충돌)
- [ ] B-4 정렬·줄간격·세로 앵커: 슬롯 `align`(left/center) + 패턴 `layout_notes` 해석 대신 **분류 LLM 출력 스키마에 `align` 필드 추가**
- [ ] ~~B-5 표 합계행 bold, 표 셀 여백~~ — **후속으로 descope** (v0.2, Check G3)

**Phase C — 마이그레이션·검증**
- [ ] C-1 재추출 절차: `POST /extract` → `PUT /{blueprint_id}` 로 **동일 id(3bac89cb…) 덮어쓰기** (운영 스크립트 `scripts/blueprint_reextract.py`)
- [ ] C-2 골든 샘플 회귀 테스트: `samples/golden_sample_report.pdf` → 추출 → 렌더 → 아래 성공 기준 자동 검증

### 2.2 Out of Scope

- 샘플 PDF 임베드 이미지 해상도 문제(#6) — 샘플 교체로 해결
- (v0.2) section_lead 카드 소제목 `h3` bold — bullets 슬롯 구조 확장 필요, 후속 피처
- (v0.2) 표 합계행 bold·셀 여백 (B-5)
- 프론트엔드 블루프린트 관리 UI 변경 (`schema_version` 표시만 확인)
- 폰트 파일 서버 설치·임베딩 (원 Plan §2.2와 동일하게 제외)
- 슬라이드 계획/슬롯 작성 LLM 프롬프트의 콘텐츠 품질 개선 (스타일 외)
- PPTX 골든 샘플의 도형 추출(`pptx_style_extractor`)은 인터페이스만 맞추고 채움 도형 추출은 후속

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 폰트 매핑 실패 시 원본 폰트명 유지 (`font_mapping[src]=src`), 경고는 "not installed — kept as-is"로 변경 | High | Pending |
| FR-02 | 로고/장식 에셋 box = 비표지 페이지 최빈 좌표; 표지 좌표는 `cover_box`로 보존, 렌더러는 표지에서 `cover_box` 사용 | High | Pending |
| FR-03 | 하단 밴드 반복 텍스트 → `HeaderFooter.footer_text`, `footer_box`; 페이지번호 → `page_number_format`, `page_number_box` (좌표 하드코딩 `_PAGE_NUMBER_BOX/_FOOTER_BOX` 제거) | High | Pending |
| FR-04 | 패턴 `footer` 슬롯은 생성 LLM 입력에서 제외, 렌더러가 스타일 값으로만 채움 → 슬라이드당 페이지번호 정확히 1개 | High | Pending |
| FR-05 | `StyleTokens.sizes`에 `h3`, `subtitle` 추가 (REQUIRED_SIZE_KEYS 유지 + 옵션 키); 추출 시 distinct size에서 매핑 | Medium | Pending |
| FR-06 | `PagePattern.decorations: tuple[Decoration, ...]` 추가 (rect: box, fill hex, optional line). 추출기 `_fills`→패턴 저장, 렌더러가 배경 다음·콘텐츠 전에 그림 | High | Pending |
| FR-07 | `PaletteClusterPolicy.accent1` = 채움 도형 색 중 primary/bg 근접색 제외 최다 | Medium | Pending |
| FR-08 | `toc` 패턴 bullets는 `1.` 번호 + `h3` 크기(SC-6 16pt) + 줄간격 1.5. ~~카드형 소제목 `h3` bold primary~~ → 후속 (G1) | Medium | Done (toc) |
| FR-09 | 분류 스키마 `PagePatternDraft.slots[].align ∈ {left,center,right}` 추가, 렌더러 적용 (기본 left) | Medium | Pending |
| FR-10 | `schema_version=2`; `serialization.from_dict`가 v1(decorations/align/h3 없음)도 기본값으로 로드 | High | Pending |
| FR-11 | 재추출 스크립트: 파일 경로 + blueprint_id 인자 → extract → PUT 갱신, 경고 출력 | Medium | Pending |
| FR-12 | 골든 샘플 회귀 테스트(§4.1 기준 자동 검증) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 기존 v1 `blueprint_json` 레코드 로드·렌더 무오류 | `tests/domain/blueprint/test_serialization.py` v1 픽스처 |
| 성능 | 추출 시간 증가 ≤ 10% (도형 수집은 기존 `_fills` 재사용) | `timings_ms.extract` 로그 비교 |
| 아키텍처 | domain은 PyMuPDF/python-pptx 미참조 유지 | `tests/*/blueprint/test_layer_contract.py`, `/verify-architecture` |
| 로깅 | 경고는 `warnings` 튜플 + logger.warning (LOG-001) | `/verify-logging` |
| 함수 길이 | 40줄 이하, if 중첩 ≤ 2 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done — 골든 샘플 회귀 (자동)

`samples/golden_sample_report.pdf` 추출 → 7장 샘플 계획 렌더 → python-pptx로 검사:

- [ ] SC-1 모든 run의 `font.name ∈ {"Malgun Gothic Bold","Malgun Gothic Regular","Malgun Gothic"}` (NanumGothic 0건)
- [ ] SC-2 2~N 슬라이드 로고 picture box ≈ `(0.83,0.04,0.12,0.07)` (±0.02), 표지는 `(0.06,0.07,0.19,0.11)`
- [ ] SC-3 슬라이드당 `"{n} / {total}"` 형태 텍스트 정확히 1개, 우하단(x ≥ 0.85, y ≥ 0.9)
- [ ] SC-4 2~N 슬라이드에 텍스트 `여신심사부 · 대외비 · 2026년 3분기` 존재, 캡션 크기·`#666666`
- [ ] SC-5 2~N 슬라이드에 `#F2F4F5` 채움 사각형(y ≥ 0.9, w ≈ 1.0) 존재; section_lead 패턴 슬라이드에 카드 사각형 ≥ 1
- [ ] SC-6 `toc` 슬라이드 항목이 `1.`로 시작, 크기 16pt, 제목 24pt bold `#1F3A5F`
- [ ] SC-7 팔레트 `accent1 == "#E07A1F"`, `primary == "#1F3A5F"`
- [ ] SC-8 v1 JSON 픽스처 로드 → 렌더 성공 (decorations 빈 튜플)

### 4.2 Quality Criteria

- [ ] 변경 모듈 테스트 선작성 (TDD) 및 통과: `tests/domain/blueprint/test_policies.py`, `test_value_objects.py`, `test_serialization.py`, `tests/infrastructure/blueprint/test_fonts.py`, `test_pdf_style_extractor.py`, `test_pptx_renderer.py`, `tests/application/blueprint/test_extraction_use_case.py`
- [ ] ruff 0 error, 레이어 계약 테스트 통과
- [ ] 실 DB 레코드 `3bac89cb…` 재추출 후 수동 PPT 육안 확인 1회

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `blueprint_json` 스키마 변경으로 기존 레코드·프론트 타입 불일치 | High | Medium | schema_version 2 + 옵션 필드 기본값; 프론트 `src/types/` 는 추가 필드 무시(읽기 전용) 확인 — `/api-contract-sync` 체크 |
| 폰트 패스스루 시 뷰어 PC에 폰트가 없으면 여전히 기본 폰트 | Medium | Medium | 경고 메시지로 안내; 한글 Windows 기본 탑재(Malgun Gothic)이라 실사용 영향 낮음 |
| 채움 도형을 무분별하게 저장하면 차트 막대·표 셀까지 장식으로 들어감 | High | High | 표 bbox·차트 슬롯 box 내부 도형 제외, 면적 상한(≤ 0.6)·색 수 제한, 반복(≥2p) 우선 |
| 분류 LLM이 `align`을 잘못 내놓음 | Low | Medium | 기본값 left, 표지 title만 LLM 값 신뢰; notes의 "중앙" 키워드 폴백 |
| 푸터 텍스트 추출이 샘플마다 다름(문서마다 y 위치 상이) | Medium | Medium | y ≥ 0.88 & caption 크기 & ≥2p 반복 조건 AND; 실패 시 빈 값 유지(현행과 동일) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `StyleTokens`, `HeaderFooter`, `PagePattern`, `Slot`, `BlueprintAsset` | Domain VO | `sizes` 키 확장, `footer_box/page_number_box`, `decorations`, `align`, `cover_box` 추가 |
| `PagePatternDraft` / `SlotDraft` | Domain schema (LLM strict) | `align` 필드 추가 |
| `serialization.py` | Domain | v2 직렬화 + v1 폴백 |
| `SizeHierarchyPolicy`, `PaletteClusterPolicy`, `RepeatAssetPolicy` | Domain policy | 계층 확장·accent 보정·최빈 좌표 |
| `FontCatalog.propose_mapping` | Infra | 패스스루 |
| `PdfStyleExtractor` | Infra | 푸터·도형 → PageStats 필드 추가(`footer_spans`, 기존 `fills` 활용) |
| `PptxSlideRenderer` | Infra | 도형·푸터·정렬·역할별 스타일 |
| `prompts_generation.py` / `slot_writer` | Infra | footer 슬롯 제외 |
| `BlueprintExtractionUseCase._style_tokens/_pattern_from_draft` | Application | 신규 필드 조립 |
| `document_blueprint.blueprint_json` | DB (JSON 컬럼, DDL 변경 없음) | schema_version 1→2 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `blueprint_json` | READ | `infrastructure/blueprint/repository.py` → `serialization.from_dict` | v1 폴백 필요 (Needs verification) |
| `blueprint_json` | READ | `application/agent_builder/presentation_generator_binding.py` → 생성 UseCase | 렌더 경로 — SC-8로 검증 |
| `blueprint_json` | READ | `idt_front` 블루프린트 관리 화면 (`BlueprintResponse`) | 추가 필드 무시 확인 (Needs verification) |
| `StyleTokens.sizes` | READ | `pptx_renderer.py`, `chart_builder.py` | 키 추가만 — None |
| `PagePattern` | CREATE | `extraction_use_case._pattern_from_draft`, `_heuristic_pattern`(PPTX) | `decorations=()` 기본 — None |
| `FontCatalog` | READ | `GET /admin/blueprints/fonts`, `test_fonts.py` | 경고 문구 변경 — 테스트 수정 |
| `HeaderFooter` | UPDATE | `PUT /{blueprint_id}` (admin_use_case) | 신규 필드 수용 — Needs verification |

### 6.3 Verification

- [ ] 위 consumer 전부 v2 JSON으로 동작 확인
- [ ] 권한 변경 없음 (admin 전용 유지)
- [ ] DDL 변경 없음 (JSON 컬럼 내부만)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain → application → infrastructure) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 장식 도형 표현 위치 | (a) Slot.kind=SHAPE / (b) PagePattern.decorations 별도 튜플 | **(b)** | 슬롯은 "LLM이 내용을 채우는 자리" 의미 — 장식은 내용이 없으므로 분리해야 SlotContentPolicy·프롬프트 오염이 없음 |
| 푸터 책임 | (a) LLM 슬롯 / (b) 스타일 토큰 + 렌더러 | **(b)** | 푸터는 문서 불변 요소. LLM 날조(#3) 원천 차단 |
| 폰트 미설치 처리 | (a) 기본 폰트 치환(현행) / (b) 원본명 유지 | **(b)** (사용자 결정) | 산출물 소비자 PC 기준으로 원본 폰트가 있을 확률이 더 높음 |
| 스키마 호환 | (a) in-place 마이그레이션 / (b) 버전 필드 + 읽기 폴백 | **(b)** | DB 스키마 임의 변경 금지 규칙; JSON 내부 버전만 올림 |
| 기존 레코드 | (a) 새 id / (b) 같은 id 덮어쓰기 | **(b)** (사용자 결정) | 에이전트 설정의 blueprint_id 참조 유지 |

### 7.3 Clean Architecture Approach

```
domain/blueprint/        value_objects(+Decoration, align, cover_box), policies(계층·팔레트·좌표), serialization(v2)
application/blueprint/   extraction_use_case(조립), generation_use_case(footer 제외)
infrastructure/blueprint/ extractors/pdf(푸터·도형), fonts(패스스루), renderer/pptx(도형·푸터·스타일), prompts_generation
scripts/                 blueprint_reextract.py (Phase C)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (함수 40줄, if 중첩 2, config 하드코딩 금지, print 금지)
- [x] `docs/rules/testing.md` TDD 절차
- [x] ruff 설정 (`pyproject.toml`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 좌표 하드코딩 | 렌더러에 `_PAGE_NUMBER_BOX/_FOOTER_BOX` 상수 | 스타일 토큰으로 이동, 상수는 폴백 전용 | High |
| 스키마 버전 | `schema_version=1` 고정 | 상수 `CURRENT_SCHEMA_VERSION=2` 단일 출처 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `BLUEPRINT_FONT_DIR` | 설치 폰트 스캔 (미설정 시 패스스루) | Server | 기존 — 변경 없음 |
| `BLUEPRINT_DEFAULT_FONT` | 원본 폰트명이 빈 경우에만 사용 | Server | 기존 — 의미 축소 |

---

## 9. Next Steps

1. [ ] `/pdca design blueprint-style-fidelity` — Decoration VO·푸터 추출 휴리스틱·렌더 z-order 상세 설계
2. [ ] Phase A → B → C 순 구현 (TDD)
3. [ ] `scripts/blueprint_reextract.py`로 `3bac89cb…` 재추출 후 PPT 육안 검증
4. [ ] `/api-contract-sync`로 프론트 타입 영향 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-23 | 초안 — 실데이터 대조 원인 진단 + 범위/요구사항 | 배상규 |
| 0.2 | 2026-08-23 | Check 반영 — FR-08 `subtitle`→`h3` 정정(G8), 카드 소제목·B-5 descope(G1/G3) | 배상규 |
