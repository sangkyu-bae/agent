# golden-sample-blueprint Planning Document

> **Summary**: Golden Sample(PDF/PPTX 1부)을 파싱·멀티모달 분석해 스타일 토큰 + 페이지 패턴 + 서사 구조를 `DocumentBlueprint`로 저장하고, "OO 데이터로 OO 주제 PPT 작성해줘" 요청 시 그 blueprint 형식대로 PPTX(+PDF)를 생성하는 기능.
>
> **Project**: sangplusbot (idt backend + idt_front)
> **Version**: 0.1
> **Author**: 배상규 (with Claude)
> **Date**: 2026-08-22
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 문서생성기(`DocumentGenerator`)는 섹션 아웃라인 → LLM HTML → html→pdf/docx 구조라 회사 표준 양식(레이아웃·팔레트·폰트 체계·페이지 구성·문체)을 재현할 수 없고, PPT 출력 경로도 없다. 매번 자유 창작된 형식의 문서가 나와 현업 재가공 비용이 크다. |
| **Solution** | 관리자가 Golden Sample 1부를 올리면 PyMuPDF/python-pptx 수치 추출 + 비전 LLM 페이지 분류로 `DocumentBlueprint`(style_tokens·page_patterns·narrative·assets)를 만들고, 검토·편집 후 전역 라이브러리에 저장한다. 새 워커 도구 `presentation_generator`가 blueprint를 선택해 LLM은 **슬롯 내용만** 계획·작성하고, python-pptx 렌더러가 네이티브 차트 포함 PPTX를 만든다(PDF는 MCP 변환). |
| **Function/UX Effect** | 관리자: `/admin/blueprints`에서 샘플 업로드 → 추출 결과(팔레트·폰트 매핑·페이지 패턴·서사) 미리보기·편집 → 저장. 에이전트 빌더: 문서생성기와 같은 방식으로 `presentation_generator` 워커에 blueprint 지정. 사용자: 대화 첨부/상류 근거 데이터로 "OO 주제 PPT" 요청 → 표준 양식 PPTX 다운로드. |
| **Core Value** | "형식은 blueprint가 고정, 내용만 LLM" — 표준 양식 준수율을 프롬프트 운에 맡기지 않고 구조로 보장. multimodal-extractor(추출기·비전 어댑터)와 document_generator(근거 수집·파일 저장)의 기존 자산을 재사용하며, 탈착형 워커 도구로 기존 경로에 영향 없음. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 표준 양식(레이아웃·팔레트·폰트·페이지 구성·문체) 재현이 불가능하고 PPT 출력이 없어 생성 문서의 현업 재가공 비용이 크다 |
| **WHO** | 주인공 P2(에이전트 소유자/관리자)가 blueprint를 등록·편집하고 워커에 연결; 최종 사용자는 에이전트 대화로 PPT를 받는다 |
| **RISK** | 비전 LLM의 페이지 패턴 분류 오류·폰트 파일 복제 불가로 "픽셀 동일"이 아닌 "구조·톤 재현"에 그침 → 관리자 편집 단계와 기대치 명시로 완화 |
| **SUCCESS** | Golden Sample 1부로 blueprint 생성·편집·저장 E2E; 동일 blueprint로 생성한 PPTX가 페이지 패턴 순서·팔레트·폰트 체계를 100% 적용; 네이티브 차트 포함; 실 LLM 스모크 통과; 기존 DocumentGenerator 테스트 회귀 0 |
| **SCOPE** | Phase 1(이 Plan): blueprint 추출·편집·저장 + presentation_generator 워커 + PPTX 렌더러 + PDF MCP 변환 / Phase 2: DOCX·PDF 직접 출력, 다중 샘플 병합, 슬라이드 마스터(.potx) 내보내기, blueprint 버전 관리 |

---

## 1. Overview

### 1.1 Purpose

조직이 이미 쓰는 보고서/발표자료 1부(Golden Sample)를 "형식의 단일 진실 공급원"으로 삼아, 이후 생성되는 발표자료가 그 형식을 따르게 한다. LLM은 형식을 창작하지 않고 blueprint가 정의한 슬롯 안에서 내용만 결정한다.

### 1.2 Background

- `DocumentGenerator`(doc-generator, 2026-08)는 섹션 커버리지는 보장하지만 시각 형식은 LLM HTML 자유 작성에 의존한다. 변환기(xhtml2pdf)도 CSS 지원이 약해 정밀 재현이 불가하다.
- `multimodal-extractor`(2026-08 아카이브)로 PDF 이미지·표·차트 추출기와 비전 어댑터 3종(strict 구조화 출력)이 갖춰져, 페이지 렌더 이미지를 LLM이 "패턴"으로 분류하는 기반이 생겼다.
- PPTX는 텍스트박스 절대좌표·테마 색·네이티브 차트를 가지므로 HTML→PDF보다 형식 재현에 유리하다.

### 1.3 Related Documents

- 선행: `docs/archive/2026-08/multimodal-extractor/` (추출기·비전 어댑터·strict 출력 경계)
- 선행: doc-generator Design (`DocumentGenerationType`, `DocumentConversionAdapter`, 워커 tool_config 패턴)
- 시나리오: `docs/USER-SCENARIOS.md` — P2 주인공, 특화는 데이터로(blueprint = 데이터)
- 위키 패턴(적용 예정): llm-output-trust-boundary, structured-output-strict-schema, degradation-vs-failure-boundary, detachable-module-seam, config-single-source-at-consumption, false-green-quality-gates

---

## 2. Scope

### 2.1 In Scope

- [ ] **Golden Sample 입력**: PDF 1부 또는 PPTX 원본 1부 (둘 다 지원, 확장자로 추출기 선택)
- [ ] **Blueprint 추출**: 수치(PyMuPDF/python-pptx) + 비전 LLM 페이지 분류 + 종합 LLM(strict) → `DocumentBlueprint`
  - style_tokens: 폰트 패밀리(본문/제목)·크기 체계·색 팔레트(primary/accent/text/bg)·여백·슬라이드 크기·표 스타일·헤더/푸터 패턴
  - page_patterns: 표지·목차·섹션 리드·본문(텍스트/차트+해설/표/2단)·결론 등 패턴별 슬롯 정의(위치·역할·최대 길이)
  - narrative: 섹션 순서·각 섹션 역할·문체 지침(예: 현황→원인→시사점)
  - assets: 반복 이미지(로고·표지 배경·장식)를 파일 저장하고 패턴 슬롯에 참조
- [ ] **폰트 매핑**: 추출 폰트명 → 서버 설치 폰트 매핑 테이블(관리자 편집), 미매핑 시 기본 폰트 + 경고
- [ ] **관리자 화면** `/admin/blueprints`: 업로드 → 추출 결과 미리보기(팔레트·폰트·페이지 패턴 썸네일·서사) → 편집 → 저장 / 목록·수정·비활성화
- [ ] **전역 라이브러리 저장**: `document_blueprint` 테이블(JSON 컬럼) + 에셋 파일 저장(기존 첨부 저장소 재사용)
- [ ] **새 워커 도구 `presentation_generator`**: tool_config에 `blueprint_id`, `output_format(pptx|pdf)`, `mcp_pptx_to_pdf_tool_id`, `max_slides`
- [ ] **생성 파이프라인**: 입력(대화 첨부 엑셀/CSV/PDF + 상류 워커 근거) → 페이지 계획 LLM(blueprint narrative 안에서, 사용자 지시로 상한/순서 조정) → 슬롯 작성 LLM(strict) → python-pptx 렌더(네이티브 차트: 막대/선/원/표) → 파일 저장 → (선택) MCP pptx→pdf
- [ ] **에이전트 빌더 연동**: 문서생성기와 동형의 워커 설정 UI(blueprint 드롭다운)
- [ ] **실 LLM 스모크** + 합성 Golden Sample 고정 fixture로 결정적 테스트

### 2.2 Out of Scope

- 픽셀 단위 동일 레이아웃 재현, 폰트 파일 복제·내장 (폰트명 매핑만)
- DOCX/PDF 직접 출력(기존 DocumentGenerator 영역), 기존 DocumentGenerator에 blueprint 적용
- 여러 Golden Sample 병합·blueprint 버전 관리·승인 워크플로우(활성/비활성만)
- 슬라이드 마스터(.potx) 생성·PowerPoint 애니메이션·스마트아트
- 스캔 PDF Golden Sample의 정밀 추출(비전 추정만, 경고 표시)
- Golden Sample 원본 파일 장기 보관(추출 후 폐기, 에셋만 보관)
- 사용자(비관리자)의 blueprint 등록

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 관리자가 PDF 또는 PPTX 1부를 업로드하면 `BlueprintExtractionUseCase`가 `DocumentBlueprint` 초안을 반환한다 (30MB 상한, 미지원 확장자 415) | High | Pending |
| FR-02 | PDF 추출기: PyMuPDF로 페이지별 텍스트 span(폰트명·크기·굵기·색·bbox)·표 영역·이미지 영역·페이지 크기 통계를 뽑는다. multimodal-extractor의 `PdfPyMuPdfExtractor`를 재사용해 이미지 후보를 얻는다 | High | Pending |
| FR-03 | PPTX 추출기: python-pptx로 슬라이드 크기·레이아웃명·테마 색/폰트·도형/텍스트박스 좌표·차트 유형·그림을 뽑는다 (원본이 있으면 수치 정확도 우선) | High | Pending |
| FR-04 | 비전 LLM 페이지 분류: 페이지 렌더 이미지를 기존 `VisionDescriberPort`와 동일한 어댑터·모델 설정(multimodal_setting의 vision_model)로 호출해 `PagePatternDraft`(pattern_kind, slots, layout_notes)를 strict 구조화 출력으로 받는다. 건별 실패는 degraded(패턴 `unknown`), 설정 오류는 예외 | High | Pending |
| FR-05 | 종합 단계: 수치 통계 + 페이지 분류를 합쳐 `DocumentBlueprint`를 만든다. 색 팔레트는 빈도 기반 클러스터링, 크기 체계는 분포에서 h1/h2/body/caption 추정, 반복 이미지(동일 sha256·동일 위치 ≥ 2페이지)는 로고/장식 에셋으로 분류, 서사 구조는 LLM(strict)이 페이지 패턴 순서에서 추론 | High | Pending |
| FR-06 | `DocumentBlueprint`는 pydantic strict 스키마(`extra="forbid"`, Literal 패턴 종류, dict/Any 금지)로 정의하고 Draft(LLM 출력)와 저장 엔티티를 분리한다. 서버 계산 필드(id·source_kind·page_count·extracted_at·warnings)는 LLM이 채울 수 없다 | High | Pending |
| FR-07 | 폰트 매핑: 추출 폰트명 목록에 대해 `font_mapping`(서버 설치 폰트 목록은 설정에서 1회 로드)을 제안하고 관리자가 편집한다. 미매핑 폰트는 blueprint `warnings`에 기록 | Medium | Pending |
| FR-08 | 관리자 API: `POST /api/v1/admin/blueprints/extract`(multipart → 초안 + 페이지 썸네일), `POST /api/v1/admin/blueprints`(저장), `GET/PUT/DELETE(soft) /api/v1/admin/blueprints/{id}`, `GET /api/v1/admin/blueprints`(목록). admin 전용, 에러 `{detail:{code,message}}` | High | Pending |
| FR-09 | 에셋 저장: 추출된 로고/장식 이미지를 기존 첨부 저장소(`AttachmentStore`)에 저장하고 blueprint에 file_id로 참조. 관리자가 미리보기에서 채택/제외 선택 | Medium | Pending |
| FR-10 | 관리자 화면 `/admin/blueprints`: 업로드·추출 진행 표시·결과 탭(팔레트/폰트 매핑/페이지 패턴 썸네일+슬롯/서사/에셋)·편집 폼·저장·목록. adminNav docs-quality 그룹에 추가 | High | Pending |
| FR-11 | 새 워커 도구 `presentation_generator`를 `tool_registry`에 등록. `PresentationGeneratorToolConfig(blueprint_id, output_format, mcp_pptx_to_pdf_tool_id, max_slides)` frozen VO + `__post_init__` 검증. 에이전트 빌더 UI는 문서생성기 워커 설정과 동형 | High | Pending |
| FR-12 | 페이지 계획: 입력 데이터(첨부·상류 근거)와 사용자 지시를 받아 LLM(strict)이 blueprint narrative 안에서 `SlidePlan[]`(pattern_id, 제목, 슬롯별 소스 힌트, 차트 스펙)을 만든다. 패턴 id는 blueprint에 존재하는 것만 허용(검증 실패 시 1회 재시도 후 해당 슬라이드 제외 + 경고). `max_slides` 상한 적용 | High | Pending |
| FR-13 | 슬롯 작성: SlidePlan별로 슬롯 내용을 LLM(strict)이 작성. 텍스트 슬롯은 최대 길이 준수, 표 슬롯은 행/열 제한, 차트 슬롯은 `ChartSpec(type∈bar|line|pie|table, categories, series)`로 수치만 | High | Pending |
| FR-14 | PPTX 렌더러: python-pptx로 slide 크기·배경·에셋·텍스트박스(폰트 매핑·크기 체계·색)·표·네이티브 차트(blueprint 팔레트 적용)를 패턴 슬롯 좌표에 배치. LLM 출력은 렌더러에 코드 경로 없이 데이터로만 전달(HTML/마크업 미사용) | High | Pending |
| FR-15 | 출력: 파일 저장(`AttachmentStore`, `AttachmentType.DOCUMENT`) 후 `GenerateResult` 동형 DTO 반환. `output_format=pdf`면 `DocumentConversionAdapter`를 확장해 `pptx_to_pdf` MCP 도구 호출; 도구 미지정/실패 시 PPTX만 반환하고 `warnings`에 기록(degraded) | Medium | Pending |
| FR-16 | 에이전트 런타임 연동: workflow_compiler가 `presentation_generator` 워커를 문서생성기와 같은 방식으로 컴파일(근거 블록·대화 블록·첨부 전달), 결과는 첨부 다운로드로 노출 | High | Pending |
| FR-17 | 관측: 구조화 로그(request_id, blueprint_id, slide_count, chart_count, llm 호출 수·usage·elapsed) + 기존 UsageCallback로 ai_run 사용량 기록(에이전트 런타임 경로에서) | Medium | Pending |
| FR-18 | 결정적 테스트 fixture: 합성 Golden Sample(PDF·PPTX 각 1부, 표지+목차+차트 페이지+표 페이지+결론)을 코드로 생성해 추출 통계·패턴 수·에셋 분류를 고정 검증 | High | Pending |
| FR-19 | 실 LLM 스모크(`pytest -m llm`): 합성 샘플 → blueprint 추출 → SlidePlan → PPTX 생성 1회, python-pptx로 재오픈해 슬라이드 수·차트 존재·폰트명 검증 | High | Pending |
| FR-20 | 기존 DocumentGenerator·multimodal-extractor 코드 변경 없음(재사용만). blueprint 비활성/삭제 시 연결된 워커는 실행 시 `BlueprintNotConfiguredError`(409 동형) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 20페이지 샘플 blueprint 추출 ≤ 90초(비전 동시성은 multimodal_setting.concurrency 재사용); 10장 PPT 생성 ≤ 60초(LLM 제외 렌더 ≤ 2초) | 통합 테스트 타이밍 로그 |
| Reliability | 비전 분류 건별 실패는 degraded, 전체 추출은 성공; 생성 시 슬라이드 1장 실패는 제외+경고, 전체는 성공 | 단위 테스트(위키 degradation-vs-failure-boundary) |
| Security | admin 전용 API; 업로드 30MB·확장자 화이트리스트; LLM 출력은 데이터로만 렌더(코드/마크업 주입 불가); 프롬프트 주입 방어 문구 | 라우터 테스트·AST 계약 테스트 |
| Architecture | Thin DDD 레이어 규칙(domain 외부 의존 0, ast 계약 테스트), 탈착형 이음매(DI 6줄 이내, 팩토리 None → 도구 미등록) | verify-architecture 스킬 |
| Quality Gate | 백엔드 FAILED 목록 baseline diff 0, 프론트 baseline diff 0, ruff/ESLint 신규 파일 0 에러 | false-green-quality-gates 절차 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~20 구현, 각 항목에 대응 테스트 존재(TDD)
- [ ] 합성 Golden Sample(PDF·PPTX)로 추출 → 편집 → 저장 → 워커 연결 → PPTX 생성 E2E 통합 테스트 통과(비전·작성 LLM은 fake)
- [ ] 실 LLM 스모크 1회 통과(OpenAI 또는 Anthropic)
- [ ] 생성 PPTX 검증: 슬라이드 순서가 SlidePlan과 일치, 팔레트 색이 테마/도형에 적용, 매핑 폰트명 적용, 차트가 네이티브 차트 객체
- [ ] 관리자 화면 Vitest 테스트 + adminNav 테스트 갱신
- [ ] verify-architecture / verify-logging / verify-tdd 통과, 기존 테스트 회귀 0

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] ruff / ESLint 신규 파일 0 에러, tsc 신규 에러 0
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, DDL 전 컬럼 COMMENT

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 비전 LLM 페이지 패턴 분류 오류(차트 페이지를 표로 등) | High | Medium | 관리자 편집 단계 필수; 수치 신호(표 영역·이미지 영역 유무)를 분류 힌트로 동봉; 패턴 `unknown` 허용 |
| "픽셀 동일" 기대와 실제 "구조·톤 재현"의 간극 | Medium | High | 화면·문서에 기대치 명시; PPTX 원본 입력 시 좌표 정확도 향상 안내 |
| 폰트 미설치로 렌더 결과 폰트 대체 | Medium | High | 폰트 매핑 테이블 + 미매핑 경고; 서버 기본 폰트 설정값 |
| python-pptx 차트/테마 API 한계(그라데이션·일부 서식 불가) | Medium | Medium | 차트 유형 4종으로 제한, 패턴 슬롯은 텍스트박스/표/차트/이미지 4 종류만 |
| LLM이 blueprint에 없는 패턴 id·초과 길이 출력 | Medium | Medium | strict 스키마 + 서버 검증 + 1회 재시도 후 제외(degraded) |
| pptx→pdf MCP 도구 부재 | Low | High | PPTX만 반환 + 경고(degraded), 도구는 설정으로 나중에 연결 |
| 로고·장식 이미지 저작권 | Low | Low | 관리자 채택 선택제, 원본 샘플은 보관 안 함 |
| 추출 비용(페이지 수 × 비전 호출) | Medium | Medium | 페이지 상한(기본 60) + multimodal_setting 동시성·타임아웃 재사용 + 중복 페이지 해시 스킵 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `document_blueprint` | DB Model (신규 V066) | blueprint JSON·메타·status·font_mapping |
| `document_blueprint_asset` | DB Model (신규 V066) | blueprint ↔ 첨부 file_id·kind(logo/decoration/cover) |
| `src/domain/agent_builder/tool_registry.py` | Config | `presentation_generator` 워커 도구 항목 추가 |
| `workflow_compiler.py` / `create|update_agent_use_case.py` / `agent_builder/schemas.py` | Application | 문서생성기 바인딩과 동형의 `presentation_generator` tool_config 검증·컴파일 분기 추가 |
| `DocumentConversionAdapter` | Infrastructure | `to_pdf_from_pptx()` 메서드 추가(기존 메서드 불변) |
| `src/api/main.py` | API | `wire_blueprint(app, ...)` 1회 호출 |
| `requirements` | Dependency | `python-pptx` 추가 |
| idt_front `adminNav.ts`, `App.tsx`, `constants/api.ts`, `queryKeys.ts`, 에이전트 빌더 워커 설정 폼 | Frontend | 라우트·상수·워커 설정 옵션 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `tool_registry` | READ | 에이전트 빌더 UI 도구 목록·`workflow_compiler` | None (항목 추가만; 기존 도구 키 불변) |
| `workflow_compiler` 문서생성기 분기 | READ | 에이전트 실행 그래프 컴파일 | Needs verification — 분기 추가 시 기존 `document_generator` 경로 테스트 유지 |
| `create/update_agent_use_case` tool_config 검증 | UPDATE | 에이전트 저장 | Needs verification — 새 worker_type 분기, 기존 검증 불변 |
| `DocumentConversionAdapter.to_document/to_html` | READ | DocumentGenerator, DocumentExtractor | None (메서드 추가만) |
| `AttachmentStore` | CREATE | DocumentGenerator·채팅 첨부 | None (동일 API 사용) |
| `multimodal_setting` / `VisionAdapterRegistry` | READ | multimodal preview·admin | None (읽기 재사용; 설정 스키마 불변) |
| `PdfPyMuPdfExtractor` | READ | MultimodalExtractionUseCase | None (인스턴스 재사용, 코드 불변) |
| `adminNav.test.ts` 전수 목록 | READ | 프론트 테스트 | Breaking(테스트) — 라우트 추가 시 목록 갱신 필요 |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트 통과(FAILED baseline diff 0)
- [ ] 권한 변경 없음(admin 전용 신규 라우트만)
- [ ] 기존 테이블 컬럼 변경 없음(신규 테이블 2개만)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | Simple structure | Static sites | ☐ |
| Dynamic | Feature modules, BaaS | SaaS MVP | ☐ |
| **Enterprise** | Strict layer separation, DI | 기존 Thin DDD 백엔드 | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 생성 도구 위치 | 기존 DocumentGenerator 확장 / 새 워커 도구 | **새 워커 `presentation_generator`** | 기존 도구 스키마·프롬프트 불변, 탈착형 유지 (사용자 결정) |
| 출력 포맷 | PPTX / PDF / DOCX | **PPTX 우선, PDF는 MCP 변환** | 절대좌표·네이티브 차트로 재현도 최고 (사용자 결정) |
| Golden Sample 입력 | PDF만 / PDF+PPTX | **PDF + PPTX 원본** | PPTX 원본이면 수치 정확도 ↑ (사용자 결정) |
| blueprint 소유 | 전역 / 에이전트별 / KB별 | **전역 라이브러리 + 워커에서 선택** | 양식은 조직 자산, 재사용 (사용자 결정) |
| 검토 흐름 | 자동 저장 / 미리보기+편집 | **미리보기 + 편집 후 저장** | 비전 분류 오류 완화 (사용자 결정) |
| 차트 | python-pptx 네이티브 / 이미지 / 제외 | **네이티브 차트** | 편집 가능·팔레트 적용 (사용자 결정) |
| 에셋 | 보관 / 미보관 | **blueprint 에셋으로 보관, 관리자 채택제** | 로고·표지 재현 (사용자 결정) |
| 페이지 구성 | LLM 계획 / 고정 | **LLM이 narrative 안에서 계획 + 사용자 지시** | 주제별 분량 차이 수용 (사용자 결정) |
| 입력 데이터 | 첨부+상류 근거 / KB RAG / 분석 결과 | **첨부 + 상류 워커 근거** (가정 — 미응답, Design에서 확인) | DocumentGenerator evidence 경로 재사용 |
| 비전 모델 | 별도 설정 / multimodal_setting 재사용 | **multimodal_setting.vision_model 재사용** | 설정 단일 소스, 새 설정 키 0 |
| LLM 출력 신뢰 경계 | HTML 생성 / 구조화 데이터만 | **구조화 데이터만, 렌더러는 코드** | 주입 차단·형식 보장 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 Thin DDD)

src/domain/blueprint/            value_objects(DocumentBlueprint, StyleTokens, PagePattern, Slot,
                                 SlidePlan, ChartSpec), schemas(Draft 계열 strict), policies
                                 (PaletteClusterPolicy, SizeHierarchyPolicy, RepeatAssetPolicy,
                                 SlidePlanValidationPolicy), interfaces(포트), errors
src/application/blueprint/       BlueprintExtractionUseCase, BlueprintAdminUseCase,
                                 PresentationGenerationUseCase, registries(SampleExtractorRegistry)
src/infrastructure/blueprint/    extractors/{pdf_style_extractor, pptx_style_extractor},
                                 vision/page_classifier(기존 어댑터 재사용), prompts,
                                 renderer/pptx_renderer, models, repository, fonts
src/interfaces/schemas/blueprint.py
src/api/routes/admin_blueprint_router.py, src/api/blueprint_di.py (wire_blueprint)
idt_front: pages/AdminBlueprintsPage/, types/blueprint.ts, services/hooks, 워커 설정 폼 확장
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙·금지 사항 (함수 40줄, print 금지, DDL COMMENT)
- [x] `docs/rules/` (db-session, logging, testing, tool-and-mcp — **도구 추가 시 필수 확인**)
- [x] ruff 설정, ESLint/TS 설정
- [x] 위키 패턴 (`docs/wiki/_INDEX.md`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| Blueprint JSON 스키마 버전 | 없음 | `schema_version` 필드 + 하위호환 규칙 | High |
| 패턴 슬롯 좌표 단위 | 없음 | EMU 대신 슬라이드 비율(0..1) 저장, 렌더 시 변환 | High |
| 워커 도구 키 | `document_generator` 패턴 | `presentation_generator` + tool_config 키 명명 | High |
| 폰트 설정 | 없음 | `settings`에 서버 폰트 목록·기본 폰트 1개 키(consumption 지점 1곳) | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음 — 비전 모델은 multimodal_setting, 변환 도구는 워커 tool_config) | | | ☐ |
| `BLUEPRINT_FONT_DIR` (선택) | 서버 설치 폰트 스캔 경로, 미설정 시 기본 폰트만 | Server | ☐ |

### 8.4 Pipeline Integration

해당 없음 (PDCA 단일 기능).

---

## 9. Next Steps

1. [ ] `/pdca design golden-sample-blueprint` — 설계안 A/B/C 비교, blueprint JSON 스키마·패턴 슬롯 모델·렌더러 계약 확정, 입력 데이터 소스 가정 확인
2. [ ] python-pptx 설치 및 차트/테마 API 검증 스파이크(설계 중 1시간 내)
3. [ ] Do 세션 분할: 도메인+추출기 → 비전 분류+종합 → 관리자 API/화면 → 워커 도구+계획/작성 → 렌더러+변환 → 통합/스모크

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-22 | Initial draft — Checkpoint 1·2 결정 반영 | 배상규 (with Claude) |
