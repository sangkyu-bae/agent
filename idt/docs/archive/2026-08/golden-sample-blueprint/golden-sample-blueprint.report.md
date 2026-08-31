# golden-sample-blueprint Completion Report

> **Status**: Completed (QA_SKIP — L1/L2/L3 자동 테스트·실 LLM 스모크로 대체, 실 브라우저 E2E 이월)
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0.0
> **Author**: 배상규 (with Claude)
> **Date**: 2026-08-22
> **PDCA Cycle**: Plan → Design(C) → Do(7 modules) → Check(94%) → Act-1(98%) → Report
> **Documents**: [Plan](../../01-plan/features/golden-sample-blueprint.plan.md) · [Design v0.8](../../02-design/features/golden-sample-blueprint.design.md) · [Analysis](../../03-analysis/golden-sample-blueprint.analysis.md)

---

## Executive Summary

### 1.1 Project Overview

| Perspective | Content |
|---|---|
| **Problem** | 기존 문서생성기는 "섹션 아웃라인 → LLM HTML → html→pdf/docx"라 회사 표준 양식(레이아웃·팔레트·폰트·페이지 구성·문체)을 재현할 수 없고 PPT 출력이 없었다. |
| **Solution** | Golden Sample(PDF/PPTX 1부) → PyMuPDF/python-pptx 수치 + 비전 LLM 페이지 분류 → `DocumentBlueprint`(style·patterns·narrative·assets) → 관리자 검토·편집·저장(전역 라이브러리). 새 워커 `presentation_generator`가 blueprint 슬롯만 LLM으로 채우고 python-pptx가 네이티브 차트 포함 PPTX를 렌더(PDF는 MCP 변환). |
| **Function/UX Effect** | `/admin/blueprints`(업로드→분류 결과·팔레트·폰트·서사·에셋 검토/편집→저장), 에이전트 빌더의 발표자료 워커 설정, 채팅에서 "OO 데이터로 OO 주제 PPT" → 표준 양식 PPTX 다운로드. |
| **Core Value** | "형식은 blueprint가 고정, 내용만 LLM" — 양식 준수를 프롬프트 운이 아닌 구조로 보장. multimodal-extractor·document_generator 자산 재사용, 탈착형 워커(기존 경로 회귀 0). |

### 1.2 Results Summary

| Metric | Plan | Actual |
|---|---|---|
| Match Rate | ≥ 90% | **98%** (Check 94 → Act-1 98) |
| 신규 테스트 | 각 FR 대응 | 백엔드 ~250 / 프론트 21 (전체: 백엔드 7842 passed, 프론트 1116 passed) |
| 회귀 | 0 | **0** (백엔드 58 failed = baseline, 프론트 9 failed = baseline 4파일) |
| 실 LLM 스모크 | 1회 | ✅ gpt-4o 분류 5/5 + gpt-4o-mini 4장 생성, 토큰 4,239 |
| 코드 | — | 신규 ~60 파일, 기존 수정 16 파일 (백엔드 7 · 프론트 9), python-pptx 의존성 추가 |

### 1.3 Value Delivered

| Perspective | Delivered |
|---|---|
| **Problem → 해결** | PDF·PPTX 양쪽 Golden Sample에서 팔레트(`#1F3A5F/#E07A1F/#222222`)·크기 체계(28/20/14/10)·반복 에셋(cover/logo)을 결정적으로 추출(fixture 고정 테스트), 페이지 패턴은 비전 LLM(PDF) / 도형 휴리스틱(PPTX) |
| **Solution → 동작** | 계획(strict) → 슬롯 작성(동시) → 검증 정책 → 렌더: 생성 PPTX 재오픈 검증으로 패턴 순서·폰트 매핑·accent 차트·header_bg 표·로고 100% 적용 확인(L3) |
| **UX → 운영** | 분류 실패(unknown)·폰트 미설치·에셋 채택을 관리자가 편집으로 보정; 가역 패턴 제외; 경고 탭 |
| **Core Value → 안전성** | LLM 출력은 strict 스키마→VO 검증→데이터 렌더만(마크업 0); 건별 degraded(슬롯/슬라이드/PDF) vs 설정 오류 예외(409/415) 경계 테스트로 고정 |

## 1.4 Success Criteria Final Status

| # | Criterion (Plan §4.1) | Status | Evidence |
|---|---|:-:|---|
| SC-1 | FR-01~20 구현 + 대응 테스트(TDD) | ✅ Met | 20/20 (FR-17 Act-1에서 UsageCallback 배선 완료), 테스트 21+ 파일 |
| SC-2 | 합성 샘플 추출→편집→저장→워커→PPTX E2E | ✅ Met | `tests/api/test_blueprint_e2e.py` 2건(정상·degraded) |
| SC-3 | 실 LLM 스모크 1회 | ✅ Met | `tests/api/test_blueprint_smoke.py` (OpenAI) |
| SC-4 | 생성 PPTX: 순서·팔레트·폰트·네이티브 차트 | ✅ Met | `test_pptx_renderer.py` 6 + L3 재오픈 검증 |
| SC-5 | 관리자 화면 Vitest + adminNav 갱신 | ✅ Met | `AdminBlueprintsPage/index.test.tsx` 10, 패널 3, validators 8, nav G4/G6 |
| SC-6 | verify-architecture/logging/tdd, 회귀 0 | ✅ Met | 도메인→인프라 0, 라우트→인프라 0, 인프라 Policy 0, print 0, 계약 테스트 2, 회귀 0 |
| SC-7 | 신규 모듈 커버리지 ≥ 80% | ⚠️ Unmeasured | 테스트 밀도는 높으나 coverage 실행 안 함 → 이월 |
| SC-8 | ruff/ESLint 0, tsc 신규 0 | ✅ Met | 기능 파일 ruff/ESLint 0, tsc 199 = baseline |
| SC-9 | 40줄·if 2단계·DDL COMMENT | ✅ Met | AST 길이 검사 0건, V066 전 컬럼 COMMENT 테스트 통과 |

**Success Rate: 8/9 Met (1 미측정)**

## 1.5 Decision Record Summary

| Source | Decision | Followed | Outcome |
|---|---|:-:|---|
| [Plan] | 새 워커 `presentation_generator` 분리(기존 문서생성기 무변경) | ✅ | 기존 docgen 테스트 불변, 컴파일 분기 1개 |
| [Plan] | PPTX 우선 + PDF는 MCP 변환 | ✅ | `to_pdf_from_pptx` 추가, 실패 시 PPTX만(degraded) |
| [Plan] | PDF + PPTX 원본 입력 | ✅ | 추출기 2종 + 레지스트리 |
| [Plan] | 전역 라이브러리 + 워커에서 선택 | ✅ | `document_blueprint` + `/api/v1/blueprints/options` |
| [Plan] | 미리보기+편집 후 저장, 에셋 채택제, 네이티브 차트, LLM 계획+사용자 지시 | ✅ | 전부 구현 |
| [Plan] | 입력 데이터 = 첨부+상류 근거 (가정) | ✅ | `_split_fill_context` 재사용 — Design에서 확정 |
| [Design] | Option C (Pragmatic) | ✅ | 신규 도메인 1 + 포트 3, 재사용 중심 |
| [Design] D1 좌표 0..1 | ✅ | EMU 변환은 렌더러 1곳 |
| [Design] D2 에셋 LONGBLOB (Plan FR-09 조정) | ✅ | TTL 첨부 저장소 회피 |
| [Design] D3 multimodal_setting 재사용 | ✅ | 새 설정 키 0 (폰트 2개만, §8.3 허용) |
| [Design] D4 PPTX 도형 휴리스틱 / PDF 렌더+비전 | ✅ | 스모크로 PDF 경로 검증 |
| [Design] D5/D6/D7/D8 | ✅ | 슬라이드당 LLM 1회 동시, bar/line/pie+표, 소프트 참조, `describe_with` 1개 |
| [Design] §5.4 MCP select | ⚠️ 변경 | 문서생성기 패널도 text input → 동형 유지, Design v0.8 갱신 |
| [Design] §3.3 DATETIME(6) | ⚠️ 변경 | V065 관례(DATETIME) 따름, Design v0.8 갱신 |

## 2. Related Documents

- Plan: `docs/01-plan/features/golden-sample-blueprint.plan.md` (v0.1)
- Design: `docs/02-design/features/golden-sample-blueprint.design.md` (v0.8 — v0.2~0.8은 구현 중 결정 기록)
- Analysis: `docs/03-analysis/golden-sample-blueprint.analysis.md` (94% → Act-1 98%)
- 선행: `docs/archive/2026-08/multimodal-extractor/` (비전 어댑터·추출기 재사용 기반)
- 위키 패턴 적용: llm-output-trust-boundary, structured-output-strict-schema, degradation-vs-failure-boundary, ast-source-contract-tests, config-single-source-at-consumption, false-green-quality-gates, detachable-module-seam

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요약 | Status | 위치 |
|---|---|:-:|---|
| FR-01 | 업로드 → 초안 (30MB/415) | ✅ | `admin_blueprint_router.extract` |
| FR-02 | PDF 추출기(span/표/이미지/렌더) | ✅ | `pdf_style_extractor.py` |
| FR-03 | PPTX 추출기(테마/도형/표/차트) | ✅ | `pptx_style_extractor.py` |
| FR-04 | 비전 페이지 분류(strict, degraded) | ✅ | `page_classifier.py` + `extraction_use_case._classify_vision` |
| FR-05 | 종합(팔레트·크기·에셋·서사) | ✅ | `policies.py` + `synthesizer.py` |
| FR-06 | strict Draft/VO 분리 | ✅ | `schemas.py` + 필드셋 동등성 테스트 |
| FR-07 | 폰트 매핑 | ✅ | `fonts.py` + 경고 |
| FR-08 | 관리자 API 9개 | ✅ | 라우터 + 16 테스트 |
| FR-09 | 에셋 저장(LONGBLOB로 조정) | ✅ | `document_blueprint_asset` |
| FR-10 | 관리자 화면 탭 | ✅ | `AdminBlueprintsPage/*` |
| FR-11 | 워커 도구 등록 + tool_config | ✅ | `tool_registry`, 바인딩 |
| FR-12 | 계획 LLM + 검증·재시도 | ✅ | `slide_planner.py`, `_plan` |
| FR-13 | 슬롯 작성 LLM | ✅ | `slot_writer.py` |
| FR-14 | PPTX 렌더러 | ✅ | `pptx_renderer.py`, `chart_builder.py` |
| FR-15 | 저장 + PDF 변환(degraded) | ✅ | `generation_use_case._maybe_pdf` |
| FR-16 | 컴파일러 연동 | ✅ | `_create_presentation_generator_node` |
| FR-17 | 구조화 로그 + UsageCallback | ✅ (Act-1) | `callbacks=[UsageCallback]` |
| FR-18 | 결정적 fixture | ✅ | `tests/fixtures/blueprint_samples.py` |
| FR-19 | 실 LLM 스모크 | ✅ | `test_blueprint_smoke.py` |
| FR-20 | 기존 코드 무변경(재사용), inactive 안내 | ✅ | docgen 불변; adapter `describe_with`·conversion `to_pdf_from_pptx` 메서드 추가만 |

### 3.2 Non-Functional Requirements

| Category | 결과 |
|---|---|
| Performance | 스모크: 5페이지 추출(비전 5 + 종합 1) + 4장 생성 ≈ 18s (목표 90s/60s 이내) |
| Reliability | degraded 경계 7행 전부 테스트(분류·서사·폰트·계획·슬롯·VO변환·PDF) |
| Security | admin 전용 9/9, 30MB·확장자·max_pages 가드, 에셋 MIME sniff·2MB·20개, 프롬프트 "data" 선언, 마크업 미해석 |
| Architecture | Thin DDD 계약 테스트 2, 탈착형 `wire_blueprint` 1호출 + 컴파일러 분기 1 |
| Quality Gate | FAILED 목록 diff 0(백·프론트), ruff/ESLint 0, tsc baseline |

### 3.3 Deliverables

- DB: `V066__create_document_blueprint.sql`
- 백엔드: `src/domain/blueprint/`(7), `src/application/blueprint/`(4), `src/infrastructure/blueprint/`(13), `src/interfaces/schemas/blueprint.py`, `src/api/routes/admin_blueprint_router.py`, `src/api/blueprint_di.py`; 수정 `config.py`, `main.py`, `base_vision_adapter.py`(describe_with), `document_conversion_adapter.py`(to_pdf_from_pptx), `tool_registry.py`, `agent_builder/{schemas,create,update,workflow_compiler}.py`, `presentation_generator_binding.py`(신규)
- 프론트: `types/{blueprint,presentationGenerator}.ts`, `services/blueprintService.ts`, `hooks/useBlueprints.ts`, `utils/{blueprintValidators,presentationGenerator}.ts`, `pages/AdminBlueprintsPage/`(5), `components/agent-builder/PresentationGeneratorConfig{Panel,Modal}.tsx`; 수정 `LeftConfigPanel`, `AgentBuilderPage`, `agentFormPrefill`, `agentDetailMapping`, `types/agentBuilder`, `api.ts`, `queryKeys.ts`, `adminNav.ts`, `App.tsx`, MSW handlers
- 의존성: `python-pptx>=1.0.2` (`pyproject.toml`, `uv.lock` 신규 — 커밋 포함 결정)

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | 이유 | 제안 |
|---|---|---|
| 신규 모듈 커버리지 수치(SC-7) | 측정 미실행 | `pytest --cov=src/domain/blueprint --cov=src/application/blueprint --cov=src/infrastructure/blueprint` |
| 관리자 화면 실 브라우저 E2E | Playwright 미도입, MSW L2로 대체 | QA 단계 또는 Chrome MCP 수동 점검 |
| 로컬 vLLM/Ollama 스모크 | 로컬 엔드포인트 없음 | `MM_SMOKE_LOCAL_*` 설정 후 `-m llm` |
| 실 차트가 있는 Golden Sample로 비전 분류 확인 | 합성 샘플의 단색 차트 이미지는 `image_with_notes`로 분류됨 | 실제 사내 샘플 1부로 검증 |
| 커밋/PR | 전부 미커밋(multimodal-extractor 포함), V064~V066 배포 필요 | `/git-workflow` — python-pptx 설치·마이그레이션 배포 노트 |
| `/wiki update` | 자동 갱신 금지 규칙 | 사용자 명시 호출 시: "LLM 출력 VO 변환도 degraded 경계 안에"(G1), "에이전트 transcript에서 보고서 복구", "CRLF 파일 스크립트 편집" 패턴 후보 |

### 4.2 Cancelled/On Hold

- Phase 2 범위(Plan §2.2): DOCX 출력, 다중 샘플 병합, blueprint 버전 관리, .potx, 스캔 PDF 정밀 — 계획대로 보류.

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Axis | Check | Act-1 |
|---|:-:|:-:|
| Structural | 97 | 97 |
| Functional Depth | 89 | 97 |
| API Contract | 96 | 99 |
| Runtime | 95 | 99 |
| **Overall** | **94** | **98** |

### 5.2 Resolved Issues (Act-1)

| # | Sev | Issue | Fix |
|---|---|---|---|
| G1 | Critical | LLM 슬롯 출력 VO 검증 실패가 전체 생성 실패로 전파 | `_convert_slots` 슬롯 제외+warning, 단위+L3 테스트 |
| G2/G3 | Important | 표 색·로고 select 누락 | 스타일 탭 입력 추가 |
| G4 | Important | `FontCatalogPort.propose_mapping` 미선언 | 포트 선언 |
| G5 | Important | FR-17 UsageCallback 미배선 | 노드 → `generate(callbacks)` |
| G7 | Minor | max_pages 422 | 400 VALIDATION_ERROR |
| G9 | Minor | 패턴 제외 비가역 | 가역 토글 + 저장 시 적용 |
| G6/G8/G10 | Minor | 설계-코드 표기 차이 | Design v0.8 갱신(코드가 진실) |

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- **degraded/failure 경계를 테이블로 먼저 고정**(Design §6.3)하고 각 행에 테스트를 붙이니 Act-1에서 G1을 놓친 지점이 정확히 "표에 없던 단계(VO 변환)"로 드러났다.
- 합성 Golden Sample fixture(PDF·PPTX 코드 생성)가 추출·정책·렌더·E2E·스모크 전부를 결정적으로 묶어줬다.
- 기존 자산 재사용 원칙(비전 어댑터 `describe_with` 1개, conversion adapter 메서드 1개)으로 기존 테스트 회귀 0.
- 스파이크(python-pptx 차트/폰트/배경 API)를 Design 단계에서 끝내 렌더러 구현이 한 번에 통과.

### 6.2 Problem
- gap-detector 에이전트가 두 번 모두 보고서 전달 전에 멈춤 → transcript JSONL에서 최장 assistant 텍스트를 추출해 복구. 에이전트 출력은 파일로 쓰게 하는 편이 안전.
- 프론트 파일이 CRLF라 문자열 치환 스크립트가 조용히 실패(중복 삽입 1건 발생) → LF 정규화 후 편집·CRLF 복원 헬퍼 필요.
- Bash heredoc에 백틱/`\n` 포함 TS·Python을 넣으면 깨짐 → Write 도구 사용이 안전.
- 팔레트/크기 휴리스틱은 실 fixture를 돌려보고 3번 보정(배경 근접색 제외, 글자수 가중, caption=최소) — 정책은 실 데이터 테스트와 함께 설계해야 함.

### 6.3 Try
- 설계 시 "LLM 출력이 통과하는 모든 변환 단계"를 열거하고 각 단계를 degraded 표에 넣기.
- 에이전트 위임 시 "결과를 `scratchpad/x.md`에 Write하고 경로만 반환" 규약.
- 프론트 편집은 Write 도구 또는 CRLF-안전 스크립트만 사용.

## 7. Process Improvement Suggestions

- PDCA: Check 단계에서 gap-detector 실행 전에 런타임 테스트를 먼저 돌려 시간 절약(이번에 병행 실행 효과 있었음).
- 도구: `false-green-quality-gates` 절차(FAILED 목록 diff)를 스크립트로 고정하면 매 모듈 1분 절약.

## 8. Next Steps

### 8.1 Immediate
1. `/pdca archive golden-sample-blueprint --summary`
2. 커밋/PR (multimodal-extractor + golden-sample-blueprint, `uv.lock` 포함, 배포 노트: `uv sync`, V064~V066, 관리자 `/admin/multimodal` 비전 모델 설정 선행)
3. 실제 사내 Golden Sample 1부로 `/admin/blueprints` 수동 점검

### 8.2 Next PDCA Cycle
- `multimodal-store` (Phase 2: 멀티모달 요소 저장·색인·출처 표기) — 이전에 시작했다가 중단된 Plan
- blueprint Phase 2: DOCX 출력·다중 샘플·버전 관리

## 9. Changelog

### v1.0.0 (2026-08-22)
- Added: Golden Sample 추출(PDF/PPTX) → blueprint 라이브러리(관리자 화면·API·DB) → `presentation_generator` 워커 → PPTX(+PDF) 생성
- Changed: `BaseVisionAdapter.describe_with`, `DocumentConversionAdapter.to_pdf_from_pptx`, 에이전트 빌더 요청 `presentation_generator` 필드, config 키 2개
- Dependency: python-pptx

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0.0 | 2026-08-22 | 완료 보고서 | 배상규 (with Claude) |
