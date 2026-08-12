# Document Generator Planning Document

> **Summary**: 문서 유형(이름+설명+섹션 아웃라인)을 빌더에 등록해두면, 런타임에 생성 워커가 지정된 근거 소스(웹서치·내부 RAG)를 **직접 호출해 조사**하고 LLM이 **HTML 문서 본문을 자유 작성** → 기존 MCP doc 변환 서버(`html_to_pdf/docx`)로 파일화하는 **문서생성기 도구** 신설. 추출기(고정 스켈레톤 슬롯 채우기)와 대비되는 "자유 작성" 축의 풀스택 사이클 (M1=백엔드, M2=빌더 UI)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 문서 산출 경로는 `document_extractor` 하나뿐인데, 이는 **업로드된 원본의 `{{슬롯}}` 스켈레톤을 채우는 방식**이라 "정해진 양식 빈칸 채우기"만 가능하다. 시장조사 보고서·동향 브리핑처럼 **양식 원본이 없고 내용 자체를 조사·작성해야 하는 문서**는 만들 수 없고, 근거 수집도 다른 search 워커가 모아둔 evidence_block에 수동 의존한다 |
| **Solution** | ① 신규 도구 `document_generator`를 TOOL_REGISTRY에 독립 추가(추출기 무변경) ② 빌더에서 문서 유형을 **이름+설명+섹션 아웃라인**으로 정의하고 근거 소스(tavily_search·internal_document_search)를 빌드타임에 지정 (신규 테이블 V059) ③ 런타임 생성 워커(react agent)가 소스 도구를 직접 호출해 조사 → 섹션 아웃라인에 따라 HTML 작성 → 기존 `DocumentConversionAdapter.to_document`(MCP `html_to_pdf/docx`) 재사용으로 파일 생성·첨부 반환 |
| **Function/UX Effect** | P2(에이전트 소유자)가 "AI 시장조사 보고서" 같은 문서 유형을 한 번 등록하면, 사용자는 채팅에서 "○○ 주제로 보고서 만들어줘" 한 마디로 조사→작성→PDF/Word 파일까지 단일 턴에 받는다. 근거 수집이 워커에 내장되어 별도 검색 워커 구성 없이도 동작 |
| **Core Value** | 문서 자동화가 "빈칸 채우기"(추출기)에서 **"조사해서 직접 쓰기"(생성기)로 확장** — 두 도구가 정형/비정형 문서를 분담하는 문서 자동화 축 완성. MCP 변환 어댑터·첨부 저장·워커 컴파일 등 기존 인프라 최대 재사용으로 신규 표면 최소화 (일반화 우선 원칙 부합) |

---

## 1. Overview

### 1.1 Purpose

에이전트 소유자가 빌더에서 문서생성기 도구를 선택하고 문서 유형(아웃라인+근거 소스)을 등록하면:

- **런타임**: 사용자 요청 → 생성 워커가 지정 소스로 조사(react agent 루프) →
  섹션 아웃라인 기준 HTML 본문 작성 → MCP `html_to_{pdf|docx}` 변환 → 첨부 파일 반환.
- **빌드타임**: 문서 유형 CRUD는 에이전트 생성/수정 요청에 편승(추출기의 template 바인딩과 동형),
  빌더 UI에서 아웃라인 편집기 + 소스 선택 제공.

### 1.2 Background (2026-08-11 코드 조사로 확정)

**재사용 가능한 기존 자산**:

| 구간 | 위치 | 상태 |
|------|------|------|
| MCP doc 변환 어댑터 | `infrastructure/document_extractor/document_conversion_adapter.py` — `to_document(html, format, tool_id)` 로 `html_to_pdf/docx` 도구 자동 선택·정규화 | 기존재 (그대로 재사용) |
| MCP 도구 ID 폴백 | `DOCUMENT_EXTRACTOR_HTML_TO_DOC_TOOL_ID` settings 폴백 (`extract_use_case._resolve_mcp_ids` D5) | 기존재 (동일 패턴 재사용) |
| 첨부 저장 | attachment_store `save(file_bytes, filename, AttachmentType.DOCUMENT, owner)` — composer.py:69 | 기존재 |
| 워커 컴파일 분기 | `workflow_compiler.py:268` — `tool_id == "document_extractor"` 전용 노드 생성 선례 | 선례 (생성기 분기 추가) |
| 도구 레지스트리 | `domain/agent_builder/tool_registry.py` TOOL_REGISTRY — search 카테고리: `tavily_search`, `internal_document_search` | 기존재 (소스 후보) |
| 템플릿 바인딩 선례 | `application/agent_builder/document_template_binding.py` — create/update 편승 + worker tool_config 주입 + 동일 세션 저장(R6) | 선례 (문서 유형 바인딩 동형 설계) |
| LangSmith 추적 | `make_document_extractor_tracer` — compose per-run 기록 | 선례 (generate 추적 동형) |
| 마이그레이션 | 최신 V058 → 이번 사이클 **V059** | — |

**추출기와의 역할 대비 (관심사 분리)**:

| | document_extractor (기존) | document_generator (신규) |
|---|---|---|
| 문서 정의 | 원본 업로드 → `{{key}}` 스켈레톤 + 슬롯 | 이름+설명+**섹션 아웃라인** (업로드 없음) |
| LLM 역할 | 슬롯 값만 JSON 결정 (D6, 재현성 100%) | **HTML 본문 자유 작성** |
| 근거 수집 | 타 워커 evidence_block 수동 의존 | **워커가 소스 도구 직접 호출** (react agent) |
| 변환 | html→doc (원본 포맷 따름) | html→doc (**pdf/docx 유형별 설정**) |

**사전 결정 사항 (2026-08-11 사용자 확정)**:

1. **문서 유형 정의**: 이름+설명+섹션 아웃라인 방식 (예시 문서 업로드 기반은 이번 스코프 제외).
2. **근거 수집**: ~~빌드타임 소스 지정 + 워커 직접 호출~~ → **(2026-08-11 Design에서 사용자 재확정)**
   supervisor가 **문맥으로 판단**해 필요한 상류 워커(search=근거 조사, analysis=데이터 분석)만
   선행 위임하고, 생성 노드는 **모든 워커 산출물+대화**를 소비 (추출기 evidence_block 동형).
   대화에 정보가 충분한 문서(예: 휴가계획서)는 조사 없이 바로 생성. V059의 source_tool_ids 제거.
3. **생성 플로우**: **단일 턴** — 조사→작성→변환→첨부를 한 턴에. 목차 확인 HITL은 후속 마일스톤.
4. **도구 형태**: `document_extractor` 무변경, **신규 `document_generator` 독립 추가** (독립 opt-in 관례).
5. **스코프**: 풀스택(빌더 UI 포함) + 출력 포맷 PDF·DOCX 모두 + 마일스톤 분리(M1 백엔드 / M2 프론트).

### 1.3 Related Documents

- 추출기 설계 선례: `docs/archive/` document-extractor 계열 + `document_extractor-langsmith-tracing`
- 계약 확장 관례: `docs/wiki/conventions/additive-contract-extension.md` (additive·독립 opt-in)
- MCP 도구 규칙: `docs/rules/tool-and-mcp.md`
- 라우터 지도: `docs/wiki/backend/api/router-map.md`
- 알려진 이슈: PDF 한글 폰트 깨짐 (CC 메모리 doc-convert-pdf-korean-font-broken — §5 리스크 반영)

---

## 2. Scope

### 2.1 In Scope — M1: 백엔드 (도구·문서 유형·런타임 생성)

- [ ] **S1. DB — V059 `document_generation_type` 테이블 신설** (기존 스키마 무변경):
      `id, agent_id(FK), worker_id, name, description, sections(JSON — [{title, guidance}]),`
      `output_format('pdf'|'docx' — 기본 docx), status(active|deleted), created_at, updated_at`
      (mcp_html_to_doc_tool_id·type_id는 워커 tool_config에 저장 — 추출기 동형, source_tool_ids 없음)
      — 테이블+전 컬럼 COMMENT 필수, FK CHARSET/COLLATE 명시 금지(ENGINE=InnoDB만), SQLAlchemy `comment=` 동반.
- [ ] **S2. 도메인 — `domain/document_generator/`**: 문서 유형 스키마(dataclass)·정책
      (섹션 수/이름 길이 상한, source_tool_ids는 TOOL_REGISTRY search 카테고리만 허용,
      output_format 검증, 생성 HTML sanitize는 추출기 `HtmlSanitizePolicy` 재사용 검토).
- [ ] **S3. 도구 등록**: TOOL_REGISTRY에 `document_generator` ToolMeta 추가
      ("등록된 문서 유형을 근거 조사와 함께 처음부터 작성해 PDF/Word로 생성").
- [ ] **S4. 빌드타임 바인딩 — `document_generation_type_binding`**: 에이전트 create/update 요청에
      문서 유형 정의 편승(추출기 template 바인딩과 동형) — 검증 + 워커 tool_config(`type_id` 등) 주입 +
      동일 세션 저장(R6). repo update() 컬럼 화이트리스트 4곳 세트 확인.
- [ ] **S5. 런타임 — 생성 워커 노드**: `workflow_compiler`에 `tool_id == "document_generator"` 분기 신설.
      `DocumentGenerator`(infrastructure) — ① 지정 소스 도구를 바인딩한 react agent로 조사
      ② 섹션 아웃라인 프롬프트로 HTML 본문 작성 ③ sanitize ④ 기존 `DocumentConversionAdapter.to_document`
      호출 ⑤ attachment 저장 → 파일 응답(추출기 ComposeResult 동형 계약). LangSmith per-run 추적 태깅.
- [ ] **S6. 테스트 (TDD — Red 먼저)**: 도메인 정책 단위(섹션/소스/포맷 검증), 바인딩 단위(검증 실패 롤백·
      워커 부재 에러), 생성기 단위(HTML 작성 계약·변환 어댑터 mock·소스 도구 호출), DDL COMMENT 검사 통과.

### 2.2 In Scope — M2: 프론트 (빌더 UI)

- [ ] **S7. 빌더 — 문서생성기 도구 선택 시 설정 패널**: 문서 유형 편집기
      (이름·설명·섹션 목록 추가/삭제/순서, 섹션별 guidance 입력) + 근거 소스 체크박스
      (에이전트에 선택된 search 도구 목록에서) + 출력 포맷(PDF/DOCX) 선택 + MCP 변환 도구 지정(폴백 안내).
- [ ] **S8. API 계약 동기화**: types/services/hooks + `constants/api.ts` — 에이전트 create/update
      스키마 확장분 반영 (`api-contract-sync` 체크리스트).
- [ ] **S9. 테스트**: 편집기 단위(섹션 CRUD·검증) + MSW 통합(생성/수정 왕복 프리필) —
      `--pool=threads`, per-file listen 관례.

### 2.3 Out of Scope (이번 사이클 제외)

- **예시 문서 업로드 기반 스타일 참고본** (추출기 인프라 재사용 — 후속 사이클 후보)
- **목차 초안 확인 HITL** (fix-agent-planner-hitl의 stateless HITL 패턴 재사용 — 후속)
- **MCP 도구를 근거 소스로 지정** — M1은 내부 search 도구(tavily·internal_document_search)만
  (tool id 이중 네임스페이스 복잡도 회피, 수요 확인 후 후속)
- 생성 문서의 사후 편집/버전 관리, 차트·이미지 삽입
- 다국어 문서, 스트리밍 중간 미리보기
- PDF 한글 폰트 문제의 근본 해결 (MCP doc 서버 측 이슈 — §5 리스크·별도 트랙)

---

## 3. Requirements

### 3.1 Functional Requirements — M1

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 에이전트 create/update로 문서 유형(이름·설명·섹션 아웃라인·소스·출력 포맷)을 등록/수정/삭제할 수 있다 (검증 실패 시 요청 전체 롤백) | High | Pending |
| FR-02 | generator와 타 워커 공존 시 supervisor 결정 프롬프트에 문맥 판단 가이드가 주입된다 — 정보가 충분하면 바로 생성 위임, 부족하면 필요한 워커(search/analysis) 선행 (generator 없는 에이전트는 무변경) | High | Pending |
| FR-03 | 생성 노드는 상류 워커 전체(search·analysis 등)의 누적 산출물+대화를 소비한다. 상류 산출물 없이도 대화 정보만으로 생성 가능하다 (예: 휴가계획서) | High | Pending |
| FR-04 | LLM이 섹션 아웃라인 순서·구성을 따르는 HTML 문서를 작성한다 (섹션 누락 시 재시도 1회 계약) | High | Pending |
| FR-05 | 작성된 HTML이 MCP `html_to_{pdf\|docx}`로 변환되어 첨부 파일로 반환된다 (파일명=`{문서유형명}.{format}`) | High | Pending |
| FR-06 | MCP 변환 도구 미지정 시 settings 폴백, 둘 다 없으면 명확한 설정 안내 에러 (추출기 D5 동형) | Medium | Pending |
| FR-07 | 생성 실패(LLM 계약 위반·MCP 변환 실패)가 명확한 에러 메시지로 사용자 답변에 표면화된다 (조용한 실패 금지) | High | Pending |
| FR-08 | 기존 document_extractor 도구·템플릿 동작이 변하지 않는다 (무회귀) | High | Pending |
| FR-09 | 생성 run이 LangSmith에 per-run 기록된다 (`generate:{유형명}` 태깅) | Medium | Pending |

### 3.2 Functional Requirements — M2

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-10 | 빌더에서 문서생성기 도구 선택 시 문서 유형 편집기가 나타나고, 섹션 추가/삭제/순서 변경이 가능하다 | High | Pending |
| FR-11 | 설정 패널에 소스 지정 UI 없이 "검색 도구를 함께 선택하면 근거 조사 후 작성" 안내문을 표시한다 | High | Pending |
| FR-12 | 수정 진입 시 저장된 문서 유형이 프리필된다 (PUT 전체교체 프리필 선례) | High | Pending |
| FR-13 | 출력 포맷 PDF 선택 시 한글 폰트 이슈 안내문이 표시된다 (§5 리스크 완화) | Medium | Pending |

### 3.3 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 레이어 준수 | 유형 스키마·정책=domain(순수), 바인딩·워크플로=application, LLM 호출·MCP 변환·저장=infrastructure | verify-architecture 스킬 |
| DDL | V059 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 금지, SQLAlchemy `comment=` 동반 | `tests/db/test_migration_ddl_comments.py` |
| TDD | 테스트 선행 (Red → Green) — 신규 모듈 전부 테스트 파일 동반 | verify-tdd 스킬 |
| 회귀 안전 | 기존 pytest·vitest 무회귀 (사전 실패 목록 제외 기준), 추출기 테스트 전체 통과 유지 | 격리 실행 |
| 생성 상한 | 섹션 수·guidance 길이·소스 호출 횟수(react agent 반복 상한) config화 — 하드코딩 금지 | 코드 리뷰 |
| 관측 | StructuredLogger + request_id 관통, 실패 스택 트레이스 필수 | verify-logging 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done — M1

- [ ] 문서 유형(예: "시장조사 보고서", 섹션 4개, 소스 tavily) 등록된 에이전트에 "○○ 주제로 보고서 만들어줘" →
      조사 로그 확인 → DOCX 첨부 수신, 섹션 아웃라인 순서 반영 (E2E 수동 — MCP doc 서버 기동 시)
- [ ] 소스 미지정 유형 → 대화 문맥만으로 생성 성공 (테스트 단언)
- [ ] 잘못된 source_tool_id·빈 섹션 등록 시도 → 400 + 에이전트 저장 롤백 (테스트 단언)
- [ ] MCP 변환 실패 시 에러가 사용자 답변에 표면화 (테스트 단언)
- [ ] 추출기 기존 테스트 전체 통과 (무회귀)

### 4.2 Definition of Done — M2

- [ ] 빌더에서 문서 유형 신규 등록 → 저장 → 재진입 프리필 → 섹션 수정 → 저장 왕복 (MSW 통합 테스트)
- [ ] PDF 선택 시 한글 폰트 안내문 노출 (테스트 단언)

### 4.3 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 상한값 config화

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **PDF 한글 폰트 깨짐** — MCP `html_to_pdf`(WeasyPrint) 서버 폰트 부재로 한글이 "견" 글리프로 출력 (실측 확인됨) | High | **High** | M1 기본 출력 포맷을 **DOCX 권장**으로, UI에 PDF 안내문(FR-13). 근본 해결은 MCP doc 서버 측 폰트 설치 — 별도 트랙(doc-convert-korean-font)으로 명시 이월. Plan 단계에서 사용자에게 재확인 |
| LLM 자유 작성 → 섹션 누락·형식 이탈·환각 | High | Medium | 섹션 아웃라인 프롬프트 계약 + 섹션 누락 검사·재시도 1회(FR-04). 근거 없는 수치는 guidance로 억제(추출기 COMPOSE_GUIDELINES 동형의 GENERATE_GUIDELINES). 완전 방지는 불가 — 한계로 문서화 |
| react agent 조사 루프 폭주 (소스 반복 호출 → 비용·지연) | Medium | Medium | 소스 호출 반복 상한(react agent recursion limit) config화, 워커 타임아웃. LangSmith per-run으로 비용 가시화 |
| 생성 HTML이 MCP 변환기에서 깨짐 (비정형 태그·인라인 스크립트) | Medium | Medium | 추출기 `HtmlSanitizePolicy` 재사용 + 프롬프트에 허용 태그 화이트리스트 명시. 변환 warnings 로깅(D2 선례) |
| 긴 문서 단일 턴 생성 → 방향 틀렸을 때 재생성 비용 | Medium | Medium | 사용자 확정으로 수용(M1). 대화 재요청으로 1차 커버, 목차 HITL은 후속 마일스톤 명시 |
| 추출기와 도구 혼동 (사용자·supervisor 라우팅 모두) | Low | Medium | ToolMeta description에 역할 경계 명시("양식 채우기=추출기 / 처음부터 작성=생성기"), 빌더 UI 문구 구분 |
| 워커 tool_config 주입·저장 누락 (화이트리스트 함정) | Medium | Low | agent-repo-update-column-whitelist 교훈 — 스키마+apply_update+repo+DI 4곳 세트 체크리스트를 Design에 포함 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 도구 형태 | 추출기 확장 / **신규 도구 분리** | **신규 `document_generator`** | 사용자 확정. 추출기(결정론적 슬롯 치환)와 생성기(자유 작성)는 계약·리스크가 달라 분리가 자연스러움. 독립 opt-in 관례 |
| 문서 유형 저장 | document_template 재사용 / **신규 테이블** | **V059 `document_generation_type`** | 스키마가 근본적으로 다름(스켈레톤·슬롯 없음, 섹션·소스 있음). 기존 테이블 오염 방지 |
| 문서 유형 CRUD 경로 | 독립 라우터 / **에이전트 create/update 편승** | **편승 (바인딩 모듈 동형)** | 추출기 template 바인딩 선례 — 에이전트-워커-유형 일관 저장(동일 세션 R6), 프론트도 기존 빌더 저장 플로우 재사용 |
| 근거 수집 주체 | evidence_block(워커 선행) / 워커 직접 호출 / 하이브리드 | **supervisor 문맥 판단 선행 위임 + 전체 워커 산출물 소비** (Design에서 재확정) | 검색·분석 파이프라인 재사용, 도구 이중 바인딩 제거, 추출기 규약 동형. 조사 불필요 문서는 바로 생성(강제 선행 없음). 트레이드오프(작성 중 추가 조사 불가)는 수용 |
| 소스 지정 필드 | source_tool_ids 유지 / **제거** | **제거 — 에이전트의 search 워커 구성이 곧 소스** | 워커 구성과 어긋나는 지정 필드의 혼란 소지 제거 (YAGNI). 섹션별 조사 방향은 guidance 텍스트로 표현 |
| 출력 포맷 | 유형별 고정 설정 / 런타임 선택 | **유형별 빌드타임 설정 (pdf\|docx)** | 단일 턴 계약 단순화. 런타임 "이번엔 워드로" 요청은 후속 |
| HTML→파일 변환 | 신규 어댑터 / **기존 어댑터 재사용** | **`DocumentConversionAdapter.to_document` 재사용** | 실측 계약(base64·도구 이름 선택·정규화)이 이미 검증됨 — 신규 표면 0 |
| 생성 LLM 호출 구조 | 단일 프롬프트 1회 / 섹션별 분할 생성 | **Design에서 확정** (기본안: 조사 후 본문 1회 작성 + 섹션 검사 재시도) | 문서 길이·토큰 상한 실측 필요 — 섹션별 분할은 품질/비용 트레이드오프 검토 후 결정 |

### 6.3 변경 대상 파일 (예상)

```
idt/
├── db/migration/
│   └── V059__create_document_generation_type.sql    # S1 (M1)
├── src/
│   ├── domain/
│   │   ├── document_generator/                      # S2: 유형 스키마·정책·가이드라인 (순수)
│   │   └── agent_builder/tool_registry.py           # S3: document_generator ToolMeta 추가
│   ├── application/agent_builder/
│   │   ├── document_generation_type_binding.py      # S4: create/update 편승 바인딩
│   │   ├── schemas.py                               # 문서 유형 요청 DTO (additive)
│   │   └── workflow_compiler.py                     # S5: 생성 워커 분기
│   └── infrastructure/document_generator/
│       ├── generator.py                             # S5: 조사→작성→변환→첨부 (react agent)
│       └── generation_type_repository.py            # S1: 저장/조회 (세션 주입, commit 금지)
└── tests/ (domain·application·infrastructure 대응)   # S6

idt_front/src/                                        # M2
├── constants/api.ts + types/ + services/ + hooks/   # S8: 계약 동기화
├── components/agent-builder/
│   └── DocumentGeneratorConfig.tsx (+test)          # S7: 유형 편집기·소스 선택·포맷
└── __tests__/ (MSW 통합)                             # S9
```

> 생성 프롬프트 계약(GENERATE_GUIDELINES)·react agent 조사 상한·섹션 검사 규칙·
> 에이전트 스키마 확장 필드명·기존 빌더 도구 설정 패널과의 통합 지점은 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] DDL: 테이블+전 컬럼 COMMENT, FK CHARSET/COLLATE 금지 (errno 3780 선례), SQLAlchemy `comment=` 동반 — V059 적용
- [x] DB 세션: Repository 내 commit 금지, use case 단일 세션, 쓰기 세션 begin() (`docs/rules/db-session.md`)
- [x] 로깅: StructuredLogger + request_id, 스택 트레이스 필수 (`docs/rules/logging.md`)
- [x] 도구 추가 규칙: `docs/rules/tool-and-mcp.md` 필수 확인 (TOOL_REGISTRY·카탈로그 동기화 여부)
- [x] repo update() 화이트리스트: 스키마+apply_update+repo+DI 4곳 세트 (agent-repo-update-column-whitelist)
- [x] 프론트 관례: vitest `--pool=threads`, MSW per-file listen, api-contract-sync 체크리스트 (M2)
- [ ] Design 단계 확정 항목: 생성 LLM 호출 구조(1회 vs 섹션 분할), react agent 조사 상한 값,
      에이전트 create/update 스키마 필드 상세, supervisor 위임 프롬프트 문구(추출기와 혼동 방지),
      PDF 한글 폰트 대응 수준(안내문만 vs DOCX 강제 기본값)
