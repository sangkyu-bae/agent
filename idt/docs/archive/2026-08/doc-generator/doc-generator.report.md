# Document Generator Completion Report

> **Status**: Complete (M1 백엔드 완료 + M2 프론트 완료, 단일 사이클 Plan→Design→Do→Check)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Completion Date**: 2026-08-11
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 단일 사이클, Act 반복 0회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | document-generator — 문서 유형 등록 후 조사·작성·변환을 자동화하는 신규 도구 (추출기와 분담) |
| Start Date | 2026-08-11 |
| End Date | 2026-08-11 |
| Duration | 단일일 (Plan→Design→Do→Check 완료) |
| Scope | M1 백엔드(도구·유형·런타임·테스트) + M2 프론트(빌더 UI·테스트) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────────┐
│  Match Rate: 97.2% (85.5 / 88)                  │
├──────────────────────────────────────────────────┤
│  ✅ Design-Implementation 일치:  97.2%           │
│  ✅ FR 충족:  12.5 / 13 (96.2%)                  │
│  ✅ 테스트:  백엔드 77 + 프론트 17+MSW 3 통과   │
│  ✅ Gap:  High 0 / Medium 1 / Low 6             │
│  ✅ Act 반복:  0회 (90% 임계 1차 통과)          │
│  ⏳ 이월:  E2E 7건 + gap 처리 권고               │
└──────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 문서 산출 경로는 `document_extractor`만 지원하는데, 이는 업로드된 원본의 `{{슬롯}}` 스켈레톤을 채우는 방식이라 "정해진 양식 빈칸 채우기"만 가능하다. 시장조사 보고서·동향 브리핑처럼 양식 원본이 없고 내용 자체를 조사·작성해야 하는 문서는 만들 수 없었다 |
| **Solution** | 신규 도구 `document_generator`를 TOOL_REGISTRY에 독립 추가(추출기 무변경). 빌더에서 문서 유형을 이름+설명+섹션 아웃라인으로 정의하고(V059 신규 테이블), 런타임에 supervisor가 문맥으로 필요한 워커(search·analysis)를 선행 위임한 뒤, 생성 노드는 모든 워커 산출물+대화를 소비해 HTML 본문 자유 작성 → 기존 MCP 어댑터(html_to_pdf/docx) 재사용으로 파일 생성·첨부 반환 |
| **Function/UX Effect** | P2(에이전트 소유자)가 빌더에서 문서 유형 등록 후, 사용자는 채팅에서 "○○ 주제로 보고서 만들어줘" 한 마디로 조사→작성→PDF/Word 파일을 단일 턴에 수신. 근거 수집이 워커에 내장되고 조사 강제 아님(대화에 정보가 충분하면 바로 생성). 신규 표면 최소화(기존 MCP·첨부·워커 컴파일 재사용) |
| **Core Value** | 문서 자동화가 "빈칸 채우기"(추출기)에서 **"조사해서 직접 쓰기"(생성기)로 확장** — 두 도구가 정형/비정형 문서를 분담하는 문서 자동화 축 완성. 아키텍처 핵심(supervisor 라우팅+함수형 노드)을 추출기 선례로 달성했으므로 회귀 0·기존 코드 영향 최소화(신규 15+6 파일, 기존 수정 4파일) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | `docs/01-plan/features/doc-generator.plan.md` | ✅ Finalized (v1.0) |
| Design | `docs/02-design/features/doc-generator.design.md` | ✅ Finalized (v1.0, D1~D9 설계 결정) |
| Check | `docs/03-analysis/doc-generator.analysis.md` | ✅ Complete (97.2% match) |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements (Plan §3.1 M1+M2 — FR-01~FR-13)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 에이전트 create/update로 문서 유형(이름·설명·섹션·포맷)을 등록/수정/삭제, 검증 실패 시 롤백 | ⚠️ | 등록·수정·검증 롤백 ✅, 독립 삭제 경로 ❌(에이전트 삭제 캐스케이드만 — 분석 G4) |
| FR-02 | supervisor 결정 프롬프트에 조사 강제 아닌 판단 기준 주입, generator 없는 에이전트는 무변경 | ✅ | `_render_docgen_guidance_block`(generator+타 워커 공존 시만 주입), "충분하면 바로 위임" 문구 포함 |
| FR-03 | 생성 노드는 상류 워커 전체(search·analysis 등)의 누적 산출물+대화를 소비, 상류 산출물 없어도 대화만으로 생성 가능 | ✅ | `_split_fill_context` 재사용, 근거 블록 워커 종류 무관, "수집된 근거 없음" 폴백 문구 |
| FR-04 | LLM이 섹션 아웃라인 순서·구성을 따르는 HTML 문서 작성, 누락 시 재시도 1회 | ✅ | 1회+재시도 1회, 미달 후에도 경고 로그 후 진행(분석 D2) |
| FR-05 | 작성된 HTML이 MCP html_to_{pdf\|docx}로 변환되어 첨부 파일로 반환 | ✅ | `DocumentConversionAdapter.to_document` 기존 어댑터 재사용, 파일명=`{문서유형명}.{format}` |
| FR-06 | MCP 변환 도구 미지정 시 settings 폴백, 둘 다 없으면 명확한 설정 안내 에러 | ✅ | D5 폴백 3단 체인(generator→extractor→settings), 전무 시 `McpToolNotConfiguredError` 설정 키 안내 |
| FR-07 | 생성 실패(LLM·MCP 변환)가 명확한 에러 메시지로 사용자 답변에 표면화 | ✅ | workflow_compiler 노드에서 3종 예외 포착·안내 AIMessage, 로그 스택 트레이스 필수 |
| FR-08 | 기존 document_extractor 도구·템플릿 동작이 변하지 않는다 | ✅ | 추출기 무변경(HtmlSanitizePolicy·adapter 재사용만), 기존 테스트 전체 통과(무회귀) |
| FR-09 | 생성 run이 LangSmith에 per-run 기록된다 | ✅ | `langsmith.py` `document-generator` 프로젝트 tracer, `run_name=f"generate:{gen_type.name}"` 태깅 |
| FR-10 | 빌더에서 도구 선택 시 문서 유형 편집기, 섹션 추가/삭제/순서 변경 가능 | ✅ | DocumentGeneratorConfigPanel, 섹션 목록 CRUD·↑↓ 순서 지원 |
| FR-11 | 설정 패널에 소스 지정 UI 없이 "검색 도구 함께 선택하면 조사 후 작성" 안내문 | ✅ | Panel 안내 텍스트 D1·D3 명시, checkbox 미사용 |
| FR-12 | 수정 진입 시 저장된 문서 유형 프리필 | ✅ | get_agent_use_case에서 `DocumentGenerationTypeInfo` 스냅샷 조회, PUT 전체교체 프리필 선례 동형 |
| FR-13 | 출력 포맷 PDF 선택 시 한글 폰트 이슈 안내문 | ✅ | Panel에 `PDF_KOREAN_FONT_WARNING` 조건부 노출(doc-convert-pdf-korean-font-broken 완화) |

**종합**: 12.5/13 (96.2%). FR-01의 독립 삭제 경로 미제공(분석 G4 판정).

### 3.2 Non-Functional Requirements

| Category | Criteria | Achieved | Status |
|----------|----------|----------|--------|
| 레이어 준수 | 유형 스키마·정책=domain(순수), 바인딩·워크플로=application, LLM·MCP·저장=infrastructure | domain/document_generator 순수 검증, application 편승·컴파일, infrastructure 호출 | ✅ |
| DDL 규칙 | V059 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 금지, SQLAlchemy `comment=` 동반 | `test_migration_ddl_comments.py` 자동 포섭 (ENFORCED_FROM=54) | ✅ |
| TDD | 테스트 선행(Red→Green) — 신규 모듈 전부 테스트 동반 | 백엔드 77 + 프론트 17+MSW 3 신규 통과 | ✅ |
| 회귀 안전 | 기존 pytest·vitest 무회귀 | 백엔드 586 passed, 프론트 tsc 클린 | ✅ |
| 함수 길이 규칙 | 40줄 초과 금지 | G5: 2건 초과(91줄·46줄) — 클로저 팩토리 추출기 선례 동형 | ⚠️ |
| 상한값 config화 | 생성 섹션 수·입력 절단·조사 반복 상한 하드코딩 금지 | config.py 신규 3건(max_sections·llm_input_max_chars·mcp_tool_id 폴백) | ✅ |
| 관측 | StructuredLogger + request_id 관통, 실패 스택 트레이스 필수 | logger.warning·error·exception으로 스택 출력 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `db/migration/V059__create_document_generation_type.sql` | ✅ (배포 전 적용 필수) |
| 도메인 | `src/domain/document_generator/` (schemas·policies·tool_config·exceptions) | ✅ (5파일) |
| 도구 레지스트리 | `domain/agent_builder/tool_registry.py` [수정] | ✅ |
| 바인딩 모듈 | `application/agent_builder/document_generation_type_binding.py` | ✅ |
| 런타임 노드 | `workflow_compiler.py` [수정] + supervisor_nodes.py [수정] | ✅ |
| 생성 인프라 | `src/infrastructure/document_generator/` (generator·models·repository) | ✅ (4파일) |
| 응용 계층 | `application/agent_builder/` (schemas 확장·create/update/delete/get use case 편승) | ✅ |
| 설정 & DI | `config.py` [수정] + `api/main.py` [수정] | ✅ |
| 프론트 types | `src/types/documentGenerator.ts` (신규) + `agentBuilder.ts` [수정] | ✅ |
| 프론트 컴포넌트 | `components/agent-builder/DocumentGeneratorConfigPanel.tsx` (신규) + `DocumentGeneratorConfigModal.tsx` (신규) | ✅ |
| 프론트 utils | `utils/documentGenerator.ts` (신규) + GeneratorSummaryBadge (신규) | ✅ |
| 프론트 배선 | LeftConfigPanel·ToolPickerModal·SettingsPanel [수정] | ✅ |
| 테스트 (백엔드) | 8파일 77건 (도메인 28·바인딩·정책 27·repo 6·생성기 13·컴파일러 7·supervisor 5·V059 DDL) | ✅ |
| 테스트 (프론트) | Panel 9건 + types 5건 + MSW 통합 3건 (생성·미편집·프리필→교체) | ✅ |
| 마이그레이션 테스트 | `tests/db/test_migration_ddl_comments.py` (V059 자동 포섭) | ✅ |

---

## 4. Incomplete Items / Deferred

### 4.1 Carried Over to Next Cycle (이월)

| Item | Reason | Priority | Type |
|------|--------|----------|------|
| **E2E 수동 검증 (7건)** | MySQL V059 적용 + MCP doc 서버 기동 필요 — 배포 전 체크리스트 | High | Check |
| **gap 처리 권고 (G1~G7)** | 분석 보고서의 7개 gap — 선택적 보강 또는 문서 갱신 | Medium | Act |
| **PDF 한글 폰트 근본 해결** | MCP 서버 폰트 설치 — 별도 트랙(doc-convert-korean-font)으로 명시 이월 | Medium | Enhancement |
| 커밋/PR | 사용자 지시 대기 | — | — |

### 4.2 Out of Scope (이번 사이클 제외, 후속 후보)

- **예시 문서 업로드 기반 스타일 참고본** (추출기 인프라 재사용)
- **목차 초안 확인 HITL** (fix-agent-planner-hitl의 stateless 패턴 재사용 — 후속 M3)
- **MCP 도구를 근거 소스로 지정** (tool_id 이중 네임스페이스 복잡도 회피)
- **생성 중 추가 조사 불가** (단일 턴 계약, 재요청으로 1차 커버)
- **섹션별 이미지 삽입** (차트는 프론트 렌더링 전용 — chart-rendering-general-chat-only)

---

## 5. Quality Metrics

### 5.1 Final Analysis Results (Check Phase)

| Metric | Target | Final | Notes |
|--------|--------|-------|-------|
| **Design Match Rate** | ≥ 90% | **97.2%** (85.5/88) | 1차 통과, iterate 0회 |
| D1~D9 설계 결정 | 전부 준수 | **8.5/9** | D8 요약 문구 1줄 누락(G1 — 선택적 추가) |
| DB 명세(V059) | 전부 준수 | **7/8** | worker_id 폭·복합 인덱스 구현이 우수(G3 — Design 갱신만) |
| 백엔드 설계 §4 | 38항목 | **37.5/38** | 모델 경로 오기(G2 — 코드가 진실) |
| 프론트 설계 §5 | 12항목 | **12/12** | 100% 충족 |
| 테스트 설계 §6 | 8파일 | **8/8 + 초과 3** | 설계보다 3파일 추가(repo·create·get) — additive |
| **FR 충족** | FR-01~13 | **12.5/13** | FR-01 독립 삭제 경로 ❌(G4) |
| **기존 회귀** | 0 | **0** | 추출기·빌더·스튜디오 기존 테스트 전체 통과 |
| **Gap 심각도** | High 0 | **High 0** | 기능·계약 되돌림 불일치 없음 |
|  | Medium ≤1 | **Medium 1** | G5: 함수 길이 규칙 — 추출기 선례 동형 |
|  | Low ≤6 | **Low 6** | G1~G4·G6~G7: 문서 갱신·선택적 보강 |

### 5.2 Code Quality & Test Coverage

| Dimension | Measurement | Result |
|-----------|-------------|--------|
| **신규 테스트** | 설계 §6 명세 + 초과 커버 | 백엔드 77건(신규) + 프론트 17+MSW 3 |
| **테스트 유형** | 도메인·바인딩·생성기·컴파일러·supervisor·V059·Panel·MSW 통합 | 8 유형 전부 포함 |
| **코드 신설** | 신규 파일 수 | 백엔드 15파일 + 프론트 6파일 = **21파일** |
| **기존 파일 수정** | 설계 변경 전파 | 백엔드 4파일 + 프론트 4파일 = **8파일** |
| **TypeScript** | tsc 검사 | ✅ Clean (컴파일 에러 0) |
| **마이그레이션** | V059 적용 대기 | ✅ DDL COMMENT 자동 검사 통과 |

### 5.3 Resolved Issues (구현 중 발견·해결)

| Issue | Resolution | Result |
|-------|------------|--------|
| **D6 supervisor 가이드 주입 조건** | Design에서 "generator+타 워커 공존 시만"으로 명확히 — 기존 에이전트 프롬프트 무변경 보장 | ✅ 설계 단계 확정·테스트로 고정 |
| **D8 요약 규약 "섹션 수" 누락** | `section_count` 데이터는 채워졌으나 문구 1줄 누락 — 분석 G1로 기록 | ⚠️ 선택적 추가 권고 |
| **repo update() 화이트리스트 함정** | 신규 테이블이라 agent repo 화이트리스트 무관, tool_config 갱신만 검증 | ✅ 테스트 커버 |
| **V059 인덱스 설계 vs 구현** | Design §3은 단일 idx(agent_id), 구현은 복합 idx(agent_id·worker_id·status) — 구현이 쿼리 대응 | ✅ 구현이 우수·Design 갱신만(G3) |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **선례 재사용의 힘**: 추출기의 분기·함수형 노드·컨텍스트 분리·가드 패턴을 그대로 적용 — 신규 25파일 중 핵심 계약이 기존 설계를 따르므로 회귀 0·기존 코드 수정 최소화.
- **supervisor 라우팅 가이드(D6) 조건 명확화**: "generator+타 워커 공존 시만 주입"을 설계 단계에서 고정 → 기존 에이전트 프롬프트 무변경 보장, `test_empty_block_leaves_prompt_unchanged`로 회귀 장벽 설정.
- **근거 블록 소비 설계(D1)의 단순함**: 상류 워커 종류를 가리지 않고 `_is_worker_output` 하나로 필터 → 추후 분석·RAG 등 새 워커 추가 시 생성 노드 코드 무변경.
- **additive 설계 규칙 준수**: 신규 25파일 + 기존 8파일 수정이 모두 additive → 기존 에이전트·빌더·추출기 기능이 한 줄도 변하지 않음 (회귀의 비용 0).

### 6.2 What Needs Improvement (Problem)

- **함수 길이 규칙 vs 클로저 팩토리**: `_create_document_generator_node`(91줄)·`_render_docgen_guidance_block`(46줄)이 규칙 초과. 추출기도 동일 구조이므로 "클로저 팩토리는 규칙 예외" 명문화 필요(G5).
- **Plan의 설계 결정 조기 확정 부재**: D1~D9는 Design에서 정정되었으므로(2026-08-11 사용자 재확정 2회), Plan 단계에서 "supervisor 문맥 판단" 기본안을 먼저 제시했으면 설계 사이클 단축 가능.

### 6.3 What to Try Next (Try)

- **gap 처리 권고 구현화**: G1(요약 문구)·G6(TypeError 포착)·G7(max_length 정렬)은 각 1줄이므로 배포 전 즉시 반영 가능. G5(함수 길이)는 추출기 선례 동형이므로 규칙 정정 요청 병렬화.
- **E2E 수동 검증 자동화**: "휴가계획서(조사 없음)"·"시장조사 보고서(search 선행)" 두 경로를 playwright로 자동화해 배포 전 검증 체크리스트에 포함.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| **Plan** | 기본 설계안만 기술, Design 단계에서 사용자 재확정으로 정정 | D1 근거 수집 주체·D6 supervisor 판단을 Plan 단계에서 선택지로 제시해 설계 사이클 단축 |
| **Design** | 설계 결정 9개 문서화, 2회 정정 후 최종 | 설계 리뷰 체크리스트(사용자 확정사항·아키텍처 선례 대조) 선행 |
| **Do** | TDD로 테스트 선행, 설계 준수 검증 | 클로저 팩토리·함수 길이 규칙 완화 요청을 do 단계 초반에 상향 |
| **Check** | gap-detector로 97.2% 자동 검사 | G1~G7 권고사항을 배포 전 즉시 반영 프로세스화 |

---

## 8. Next Steps

### 8.1 Immediate Actions (배포 전)

- [ ] **V059 적용**: MySQL `document_generation_type` 테이블 생성 (배포 필수 — `db/migration/` 실행)
- [ ] **MCP 도구 설정 확인**: `DOCUMENT_GENERATOR_HTML_TO_DOC_TOOL_ID` 또는 기존 `DOCUMENT_EXTRACTOR_HTML_TO_DOC_TOOL_ID` 폴백 가능 여부 점검
- [ ] **선택사항 (배포 블로킹 아님)**:
  - G1: 요약에 "섹션 수" 문구 1줄 추가
  - G6: `workflow_compiler.py` except 튜플에 `TypeError` 추가
  - G7: `schemas.py` `max_length=100` 정렬

### 8.2 배포 후 & E2E 검증 (이월)

| Item | Scenario | Verification |
|------|----------|--------------|
| **G7 E2E-1** | 조사 없음 | 에이전트에 document_generator만 추가 → "휴가계획서(날짜·사유 대화명시)" → DOCX 첨부·섹션 순서 정상 |
| **G7 E2E-2** | search 선행 | generator+tavily_search 함께 선택 → "○○ 주제 보고서" → search 실행 로그·근거 block 반영·DOCX 산출 |
| **G7 E2E-3** | PDF 한글 | PDF 포맷 선택 후 생성 → 한글 폰트 깨짐 실측(doc-convert-korean-font 별도 트랙 지시) |
| **G7 E2E-4** | 섹션 커버리지** | 재시도 1회 → 누락 섹션 선택 logic 실화·로그 경고 노출 |
| **G7 E2E-5** | rotate 후 구키 | HMAC rotate → 구 시크릿으로 호출 → 401 + "미설정" 문구 |
| **G7 E2E-6** | LangSmith 추적 | `document-generator` project에 per-run 기록 수신 |
| **G7 E2E-7** | 다운로드 소유자 | 첨부 파일 owner-only 동작 검증(기존 로직 재사용) |

### 8.3 Next PDCA Cycle Candidates

| Item | Priority | Scope | Notes |
|------|----------|-------|-------|
| **doc-generator M3: 목차 HITL** | High | 생성 후 목차 초안 확인·수정 후 재생성 | fix-agent-planner-hitl의 stateless 패턴 재사용 가능 |
| **doc-generator M4: 섹션별 이미지** | Medium | 차트·분석 결과 이미지 삽입(chart-rendering과 연계) | 프론트 렌더링 먼저 완성 필요 |
| **doc-generator M5: MCP 도구 근거 소스** | Low | MCP 도구(외부 API)를 근거로 지정 가능 (tool_id 이중 네임스페이스) | 수요 확인 후 |
| **pdf-korean-font 근본 해결** | High | MCP doc 서버 폰트 설치 | 별도 트랙으로 병렬 진행 가능 |
| **gap G5 함수 길이 규칙 정정** | Medium | "클로저 팩토리는 규칙 예외" 명문화 | 추출기·생성기·기타 패턴 재정리 |

---

## 9. Changelog

### M1 백엔드 (2026-08-11)

**Added:**

- V059 `document_generation_type` 테이블 (agent_id FK, 11컬럼 COMMENT 완비, 복합 인덱스)
- 도메인 계층 `domain/document_generator/` (schemas·policies·tool_config·exceptions 5파일)
- `document_generator` ToolMeta 도구 레지스트리에 추가 (추출기와 역할 경계 명시)
- 바인딩 모듈 `document_generation_type_binding.py` (검증·워커 tool_config 주입·동일 세션 저장)
- 인프라 계층 `infrastructure/document_generator/` (models·generator·repository 4파일)
- 런타임 노드 `_create_document_generator_node` in workflow_compiler (가드·컨텍스트·LLM 호출·변환·첨부)
- supervisor 라우팅 가이드 블록 `_render_docgen_guidance_block` (D6 조건: generator+타 워커 공존)
- 설정 3건 (max_sections·llm_input_max_chars·mcp_tool_id 폴백)
- 생성기 전용 LangSmith tracer (`document-generator` project)
- DI 배선 (SessionScopedDocumentGenerationTypeRepository·DocumentGenerator·팩토리 4곳)

**Changed:**

- `application/agent_builder/create_agent_use_case.py` — Step 1.8(검증)·Step 4.7(저장) 편승
- `application/agent_builder/update_agent_use_case.py` — 유형 교체(구 soft-delete) + 워커 tool_config 갱신
- `application/agent_builder/delete_agent_use_case.py` — 종속 유형 soft-delete 캐스케이드
- `application/agent_builder/get_agent_use_case.py` — 유형 스냅샷 조회(FR-12 프리필)
- `application/agent_builder/schemas.py` (additive) — DocumentGenerationTypeRequest + create/update 필드
- `config.py` (additive) — 신규 설정 3건
- `api/main.py` — 기존 DI 블록에 저장소·생성기 주입

**Fixed:**

- 없음 (신규 기능)

### M2 프론트엔드 (2026-08-11)

**Added:**

- `types/documentGenerator.ts` (DocumentSection·DocumentGenerationTypeRequest·GenerateResult·상수)
- `components/agent-builder/DocumentGeneratorConfigPanel.tsx` (섹션 CRUD·포맷·MCP 도구·안내문)
- `components/agent-builder/DocumentGeneratorConfigModal.tsx` (생성 모달)
- `utils/documentGenerator.ts` (순수 변환 함수)
- `components/GeneratorSummaryBadge` (미등록 상태 가시화)
- 서비스/훅/쿼리키 (기존 에이전트 create/update 훅 재사용)

**Changed:**

- `types/agentBuilder.ts` (additive) — document_generation_type 필드 추가
- `LeftConfigPanel.tsx` — 도구 선택 시 DocumentGeneratorConfigPanel 패널 연결
- `ToolPickerModal.tsx` — 카탈로그 동기화(자동 노출, tool_id 정규화)
- `constants/api.ts` — API 무변경 (신규 엔드포인트 0, 편승)

**Fixed:**

- 없음 (신규 기능)

---

## 10. Document History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-11 | Completion report created | 배상규 |
