# Document Generator Design Document

> **Summary**: 문서 유형(이름+설명+섹션 아웃라인)을 근거로 LLM이 HTML 문서를 자유 작성하는 신규 도구 `document_generator` 설계. 조사는 **에이전트에 선택된 search 워커가 선행 실행**(supervisor 라우팅 가이드)하고, 생성 노드는 추출기와 동형의 **함수형 노드**로 누적 근거+대화만 소비한다. 변환은 기존 `DocumentConversionAdapter.to_document` 재사용
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-11
> **Status**: Draft
> **Plan**: `docs/01-plan/features/doc-generator.plan.md`

---

## 1. 설계 요약

```
[빌드타임 — 에이전트 create/update 편승]
빌더: 도구 document_generator 선택 + 문서 유형 정의(이름·설명·섹션·포맷)
  → build_document_generation_type_plan (검증 + 워커 tool_config 주입)
  → persist (agent 저장과 동일 세션 트랜잭션, V059 테이블)

[런타임 — supervisor 그래프]
supervisor: 문맥 판단(가이드 블록 D6) — 아웃라인을 채울 정보가
  대화·보유 데이터에 충분하면 바로 생성 워커로, 부족하면 필요한
  워커(search=근거 조사, analysis=데이터 분석)를 먼저 위임

예1) "AI 시장조사 보고서 만들어줘"
  → search 워커(근거 수집·압축) → 생성 워커
예2) "8/10~8/12 2일 휴가계획서, 사유는 개인사유"
  → 정보가 대화에 전부 있음 → 바로 생성 워커
예3) "첨부 데이터 분석해서 실적 보고서로"
  → analysis 워커(분석 결과) → 생성 워커

  → document_generator 노드 (함수형, 추출기 동형):
      유형 로드 → _split_fill_context(근거+대화)
      → DocumentGenerator.generate:
          ① LLM 1회 — 아웃라인 기준 HTML 전문 작성 (GENERATE_GUIDELINES)
          ② 섹션 커버리지 검사 → 미달 시 재시도 1회
          ③ HtmlSanitizePolicy.clean
          ④ adapter.to_document(html→pdf|docx) — 기존 MCP 어댑터
          ⑤ attachment 저장
      → 요약 AIMessage(name=worker_id) 1건 + 다운로드 참조
```

### 코드 확인으로 확정된 사실 (2026-08-11)

| 사실 | 위치 |
|------|------|
| 추출기 전용 노드 분기 선례 — `tool_id == "document_extractor"` → 함수형 노드 + `function_node_ids` 등록 | `workflow_compiler.py:268-276` |
| 누적 컨텍스트 분리 — `_split_fill_context(messages)` → (근거 블록, 대화 블록). 근거=상류 워커 AIMessage(name) 규약 | `workflow_compiler.py:825` |
| search 워커는 `create_search_pipeline_node`(rewrite→search→validate→compress)로 컴파일 — 조사 경로 재사용 근거 | `workflow_compiler.py:300-310` |
| supervisor 결정 프롬프트에 인지 블록 주입 패턴 (`_render_viz_guidance_block` 등) — 라우팅 가이드 삽입 지점 | `supervisor_nodes.py:219-245` |
| MCP 변환 `to_document(html, output_format, tool_id)` — `html_to_{pdf\|docx}` 도구 자동 선택·정규화 | `document_conversion_adapter.py:69` |
| tool_config VO 패턴 — frozen dataclass + `__post_init__` 검증 + `model_dump()` | `domain/document_extractor/tool_config.py` |
| create/update 편승 바인딩 선례 — Step 1.75 검증 → Step 4.6 동일 세션 저장 | `create_agent_use_case.py:126-137, 206-213` |
| 요청 스키마 additive 확장 선례 — `document_template: DocumentTemplateRequest \| None` | `application/agent_builder/schemas.py:78, 121` |
| DI 배선 선례 — 런타임 session-scoped repo + 빌드타임 세션 주입 팩토리 분리 | `api/main.py:2492-2523, 2556` |
| sanitize·LangSmith tracer·설정 폴백(D5) 선례 | `policies.py:167`, `composer.py:131`, `extract_use_case.py:140` |
| 마이그레이션 최신 V058 → 이번 **V059** | `db/migration/` |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | **생성 노드는 자체 조사 루프를 갖지 않는다** — 근거 수집·분석은 **상류 워커 전체**(search·analysis 등)가 담당하고, 생성 노드는 누적된 **모든 워커 산출물+대화**를 소비(`_split_fill_context` — 근거 블록은 워커 종류를 가리지 않음). 상류 산출물이 없으면 근거 없음 상태로 진행하되, 대화에 필요한 정보가 있으면 그것만으로 작성(예: 휴가계획서) | 2026-08-11 사용자 확정 (Plan의 "워커 직접 호출" 대체 + 소비 범위를 search 한정이 아닌 전체 워커로 명시). 검색·분석 파이프라인 재사용, 도구 이중 바인딩 제거, 추출기 규약과 동형 |
| **D2** | **작성 계약: LLM 1회 + 섹션 커버리지 재시도 1회** — 출력은 HTML 전문(코드펜스 허용→제거), 모든 섹션 제목이 heading으로 존재해야 함. 재시도에도 미달이면 누락 섹션 명시하고 산출물은 그대로 진행(경고 로그) | 사용자 확정(2단계). 긴 HTML을 react 루프 밖에서 생성 — 중간 절단·형식 이탈 위험 최소화. 실패해도 부분 산출물이 전무보다 유용 |
| **D3** | **V059에 source_tool_ids 없음** — 소스는 에이전트 워커 구성이 결정. 섹션별 조사 방향은 guidance 텍스트로만 표현 | 사용자 확정. 워커 구성과 어긋나는 지정 필드의 혼란 소지 제거 (YAGNI) |
| **D4** | **출력 포맷 기본 DOCX** — 빌더 기본값 docx, PDF 선택 시 한글 폰트 경고문 노출. 백엔드 스키마는 pdf\|docx 동등 수용 | 사용자 확정. MCP html_to_pdf 한글 글리프 깨짐 실측(doc-convert-pdf-korean-font-broken) — 근본 해결은 별도 트랙 |
| **D5** | **MCP 변환 도구 해석: tool_config 명시 → `document_generator_html_to_doc_tool_id` → `document_extractor_html_to_doc_tool_id` 순 폴백** — 모두 없으면 설정 안내 에러 | 추출기 D5 동형 + 보통 같은 doc MCP 서버를 쓰므로 extractor 키 최종 폴백으로 설정 중복 제거 |
| **D6** | **supervisor 라우팅 가이드 블록 — 조사 강제가 아니라 문맥 판단 기준 제시**: "문서 생성 요청 시 ① 아웃라인을 채울 정보가 대화·보유 데이터에 충분하면 **바로 생성 워커로 위임** ② 부족하면 필요한 워커(search=외부/내부 근거, analysis=데이터 분석)를 먼저 호출해 수집한 뒤 위임" (`_render_viz_guidance_block` 패턴). 주입 조건: generator 워커 존재 **and** 그 외 워커 1개 이상 (generator 단독이면 미주입) | 2026-08-11 사용자 확정 — 휴가계획서처럼 대화에 정보가 전부 있는 문서에 조사를 강제하면 낭비. 기존 "보유 데이터 인지 블록"(재사용 vs 재수집 판단)과 동일 철학. 강제 라우팅 훅 미사용 |
| **D7** | **sanitize·예외·추적은 추출기 자산 재사용** — `HtmlSanitizePolicy.clean`(domain 간 import 허용), `McpConversionError` 계열, LangSmith tracer는 신규 project `document-generator`로 동형 헬퍼 | 검증된 규칙 재사용. 추적 프로젝트만 분리해 도구별 비용·품질 가시화 |
| **D8** | **워커 산출물 규약 준수** — 노드 반환은 `AIMessage(content=요약, name=worker_id)` 1건 + `last_worker_id` 갱신 (worker-toolmessage-leak-fix 규약). 요약에 파일명·섹션 수·근거 사용 여부·(재시도 후에도 누락된) 섹션 목록 포함 | 고아 tool 메시지 400 재발 방지, 추출기 `_render_compose_summary` 동형 |
| **D9** | **가드 실패는 안내 노옵** — 미배선(repo/generator 없음)·유형 미등록·soft-delete 상태면 그래프를 중단하지 않고 안내 AIMessage 반환 | 추출기 §4-4 하위호환 패턴 동일 |

---

## 3. DB 설계 — V059

`V059__create_document_generation_type.sql` (+ `infrastructure/db/models.py` 동반, `comment=` 필수):

```sql
CREATE TABLE document_generation_type (
    id         VARCHAR(36)  NOT NULL COMMENT '문서 유형 ID (UUID)',
    agent_id   VARCHAR(36)  NOT NULL COMMENT '소유 에이전트 ID (agent_definition FK)',
    worker_id  VARCHAR(64)  NOT NULL COMMENT '대상 워커 ID (document_generator 도구 워커)',
    name       VARCHAR(100) NOT NULL COMMENT '문서 유형명 (산출 파일명에 사용)',
    description VARCHAR(500) NOT NULL DEFAULT '' COMMENT '문서 용도 설명 (작성 프롬프트에 주입)',
    sections   JSON         NOT NULL COMMENT '섹션 아웃라인 [{"title","guidance"}] (순서 보존)',
    output_format VARCHAR(8) NOT NULL DEFAULT 'docx' COMMENT '출력 포맷 (pdf|docx, 기본 docx — D4)',
    status     VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT '상태 (active|deleted, soft-delete)',
    created_at DATETIME     NOT NULL COMMENT '생성 시각 (UTC)',
    updated_at DATETIME     NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id),
    KEY idx_dgt_agent (agent_id),
    CONSTRAINT fk_dgt_agent FOREIGN KEY (agent_id) REFERENCES agent_definition (id)
        ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='문서생성기 문서 유형 — 에이전트·워커 전용 아웃라인 정의 (doc-generator)';
```

- FK에 CHARSET/COLLATE 명시 금지 (errno 3780 — V037 선례), `ENGINE=InnoDB`만.
- `mcp_html_to_doc_tool_id`·`type_id`는 **워커 tool_config에 저장**(추출기 동형) — 테이블은 유형 본문만.
- 에이전트당 활성 유형 1건 (교체 시 기존 soft-delete — 추출기 템플릿 규약 동일). UNIQUE 제약 대신
  바인딩 로직에서 보장 (soft-delete 이력 공존 허용).

---

## 4. 백엔드 설계 (M1)

### 4-1. 파일 구조

```
src/
├── domain/document_generator/            # 신규 (순수 — 외부 의존 금지)
│   ├── __init__.py
│   ├── schemas.py        # DocumentSection, DocumentGenerationType, GenerateResult DTO
│   ├── policies.py       # SectionPolicy, SectionCoveragePolicy, GENERATE_GUIDELINES
│   ├── tool_config.py    # DocumentGeneratorToolConfig
│   └── exceptions.py     # GenerateError (McpConversionError는 추출기 것 재사용)
├── domain/agent_builder/tool_registry.py           # [수정] document_generator ToolMeta 추가
├── application/agent_builder/
│   ├── schemas.py                                  # [수정] DocumentGenerationTypeRequest + create/update 필드
│   ├── document_generation_type_binding.py         # 신규 — build_plan/persist/ensure_wiring
│   ├── create_agent_use_case.py                    # [수정] Step 1.8/4.7 편승
│   ├── update_agent_use_case.py                    # [수정] 교체(soft-delete) 편승
│   ├── delete_agent_use_case.py                    # [수정] 종속 유형 soft-delete 캐스케이드
│   ├── get_agent_use_case.py                       # [수정] FR-12 프리필 스냅샷 조회
│   ├── workflow_compiler.py                        # [수정] document_generator 분기 + 노드
│   └── supervisor_nodes.py                         # [수정] _render_docgen_guidance_block (D6)
├── infrastructure/document_generator/
│   ├── generator.py                # DocumentGenerator (작성 LLM·검사·변환·저장)
│   └── generation_type_repository.py  # 빌드타임(세션 주입) + SessionScoped(런타임) 2종
├── infrastructure/db/models.py                     # [수정] DocumentGenerationTypeModel
├── infrastructure/langsmith/langsmith.py           # [수정] document-generator tracer 헬퍼
├── config.py                                       # [수정] 신규 설정 3건 (§4-5)
└── api/main.py                                     # [수정] DI 배선 (§4-6)
```

라우터 신설 **없음** — 문서 유형 CRUD는 에이전트 create/update 편승, 실행은 기존 run 경로.

### 4-2. 도메인 설계

**schemas.py**:

```python
@dataclass(frozen=True)
class DocumentSection:
    title: str          # 섹션 제목 (heading으로 출력 강제)
    guidance: str = ""  # 작성 지침 (조사 방향·포함할 내용 — D3의 소스 힌트 표현처)

@dataclass
class DocumentGenerationType:
    id: str
    agent_id: str
    worker_id: str
    name: str
    description: str
    sections: list[DocumentSection]
    output_format: str      # pdf | docx
    status: str             # active | deleted
    created_at: datetime
    updated_at: datetime
```

**policies.py**:

- `SectionPolicy.validate(sections, max_sections)` — 1개 이상, 상한(config, 기본 20),
  title 1~100자·중복 금지, guidance ≤500자. `name` 1~100자, `description` ≤500자,
  `output_format ∈ {pdf, docx}`.
- `SectionCoveragePolicy.missing_titles(html, sections) -> list[str]` —
  각 섹션 title이 `<h1|h2|h3>` 텍스트에 포함되는지 검사(공백 정규화 후 부분 일치).
  D2 재시도 판정의 단일 규칙 출처.
- `GENERATE_GUIDELINES` (작성 프롬프트 상수 — COMPOSE_GUIDELINES 동형):
  1. 출력은 완결된 HTML 문서 1개만 (`<h1>` 제목 + 섹션별 `<h2>` heading, 그 외 텍스트 금지)
  2. [근거 자료]에 있는 사실만 사용, 근거 없는 수치·주장 생성 금지
  3. 근거가 부족한 섹션은 본문에 `근거 부족으로 확인이 필요합니다` 문구를 명시 (창작 금지)
  4. 허용 태그: h1~h3, p, ul/ol/li, table/thead/tbody/tr/th/td, strong/em, br —
     script·style·iframe·외부 리소스 금지
  5. 섹션 아웃라인의 제목·순서를 그대로 따른다

**tool_config.py**:

```python
@dataclass(frozen=True)
class DocumentGeneratorToolConfig:
    type_id: str
    mcp_html_to_doc_tool_id: str   # "mcp_" 검증 (빈 값 허용 — D5 폴백)
    output_format: str             # pdf | docx
```

### 4-3. 빌드타임 바인딩 (`document_generation_type_binding.py`)

`document_template_binding.py` 동형 — 차이점만:

- 대상 워커: `tool_id == "document_generator"` (`DOCUMENT_GENERATOR_TOOL_ID` 상수).
- 검증: `SectionPolicy` (파일 업로드·원본 승격 없음 → source_archiver 불필요, 배선 검사는 repo만).
- `build_document_generation_type_plan(request, workers, max_sections)` →
  워커 `tool_config = DocumentGeneratorToolConfig(type_id, mcp_html_to_doc_tool_id, output_format).model_dump()`.
- `persist_document_generation_type(plan, agent_id, repo, request_id)` — 동일 세션 편승(R6).
- update 경로: 새 유형 저장 + 기존 활성 유형 soft-delete (추출기 "교체" 규약 동일).

**요청 스키마 (additive — 기존 필드 무변경)**:

```python
class DocumentSectionRequest(BaseModel):
    title: str
    guidance: str = ""

class DocumentGenerationTypeRequest(BaseModel):
    name: str
    description: str = ""
    sections: list[DocumentSectionRequest]
    output_format: str = "docx"                 # D4 기본값
    mcp_html_to_doc_tool_id: str = ""           # 빈 값 = settings 폴백 (D5)

# CreateAgentRequest / UpdateAgentRequest 공통 (None = 미변경):
document_generation_type: DocumentGenerationTypeRequest | None = None

# GetAgentResponse (FR-12 — edit 폼 프리필용, additive):
document_generation_type: DocumentGenerationTypeInfo | None = None
#   = name/description/sections/output_format + 워커 tool_config의 mcp_html_to_doc_tool_id
```

에러 매핑: `InvalidGenerationTypeError`는 `ValueError` 겸용 상속 — 기존 라우터의
`except ValueError` → 400에 라우터 무변경으로 편승.

### 4-4. 런타임 설계

**workflow_compiler 분기** (`document_extractor` 분기 직후, 동형):

```python
if worker_def.tool_id == "document_generator":
    worker_map[worker_def.worker_id] = self._create_document_generator_node(
        llm, worker_def, auth_ctx=auth_ctx, request_id=request_id,
    )
    function_node_ids.add(worker_def.worker_id)
    continue
```

**`_create_document_generator_node`** — `_create_document_extractor_node` 동형:

1. 가드(D9): repo/generator 미배선 → 안내 노옵. `tool_config.type_id` 없음 → "문서 유형을 등록해주세요".
   유형 조회 실패·status≠active → "문서 유형을 찾을 수 없습니다".
2. `evidence_block, conversation_block = self._split_fill_context(state["messages"])` (그대로 재사용).
3. `DocumentGenerator.generate(...)` 호출, `(GenerateError, McpConversionError, ValueError)` →
   `문서 생성 실패: {e}` 안내(FR-07 표면화).
4. 성공 요약(D8): 파일명, 섹션 수, 근거 사용 여부(`evidence_block` 유무), 누락 섹션 목록.

**`DocumentGenerator.generate`** (infrastructure):

```python
async def generate(
    self, llm, gen_type, tool_config, evidence_block, conversation_block,
    owner_user_id, request_id,
) -> GenerateResult:
    # ① 작성: system=GENERATE_GUIDELINES+유형(이름·설명·섹션 아웃라인),
    #    user=[근거 자료](없으면 "(수집된 근거 없음 — 대화 문맥만으로 작성)")+[대화]
    #    입력 상한: evidence/conversation 각각 config 문자 수로 절단 (429 방지 선례)
    # ② 코드펜스 제거 → SectionCoveragePolicy.missing_titles 검사
    #    → 미달 시 누락 섹션 피드백 포함 재시도 1회 (D2) → 그래도 미달이면 경고 로그+진행
    # ③ HtmlSanitizePolicy.clean (D7)
    # ④ output_format·mcp_tool_id 해석 (D5 폴백 체인) → adapter.to_document
    # ⑤ attachment_store.save(f"{gen_type.name}.{output_format}", DOCUMENT, owner)
    # LangSmith: run_name=f"generate:{gen_type.name}", project=document-generator (D7)
```

`GenerateResult(file_id, filename, section_count, missing_sections, used_evidence)`.

**supervisor 가이드 블록 (D6)** — `create_supervisor_node`에 `docgen_guidance_block` 추가:

- 주입 조건: generator 워커 존재 **and** 그 외 워커 1개 이상 (컴파일러가 판별해 전달 —
  generator 단독 에이전트는 미주입).
- 내용(판단 기준 제시 — 순서 강제 아님):
  "문서 생성 요청 처리 기준: 문서 아웃라인을 채우는 데 필요한 정보가 대화와 보유 데이터에
  충분하면 다른 워커를 거치지 말고 바로 문서생성 워커({id})로 위임하세요(예: 날짜·사유가
  대화에 명시된 신청서류). 외부/내부 근거 조사가 필요하면 search 워커({ids}), 데이터 분석이
  필요하면 분석 워커({ids})를 먼저 호출해 결과를 수집한 뒤 위임하세요. 문서생성 워커는
  이전 워커들의 산출물 전체를 근거로 사용합니다."
- 기존 `_render_data_context_block`(보유 데이터 인지)과 결합되어 중복 재검색 방지
  (data-inventory-requery 규약과 정합).

### 4-5. 설정 (config.py — 하드코딩 금지)

```python
document_generator_max_sections: int = 20        # 섹션 개수 상한
document_generator_llm_input_max_chars: int = 20000  # 근거+대화 입력 절단 (429 방지 선례)
document_generator_html_to_doc_tool_id: str = "" # 기본 MCP 변환 도구 (D5 — 빈 값이면 extractor 키 폴백)
```

### 4-6. DI 배선 (main.py — 추출기 배선 블록 인접)

- 런타임: `SessionScopedDocumentGenerationTypeRepository` + `DocumentGenerator(adapter, store, logger)`
  → `WorkflowCompiler(document_generation_type_repository=…, document_generator=…)` (optional 주입 —
  미주입 시 D9 노옵, 하위호환).
- 빌드타임: `_make_document_generation_type_repo(session)` 팩토리 → create/update use case 주입.
- `DocumentConversionAdapter`·attachment_store는 **기존 인스턴스 공유** (신규 생성 금지 — idt venv 증폭 교훈).

---

## 5. 프론트엔드 설계 (M2)

### 5-1. 파일 구조

```
idt_front/src/
├── types/documentGenerator.ts            # 신규 — DocumentSection, DocumentGenerationTypeRequest
├── types/agentBuilder.ts                 # [수정] create/update 요청에 document_generation_type 추가
├── components/agent-builder/
│   ├── DocumentGeneratorConfigPanel.tsx (+test)   # 신규 — Extractor 패널 선례
│   └── LeftConfigPanel.tsx / ToolPickerModal.tsx  # [수정] 도구 노출·패널 연결
└── (services/hooks는 기존 에이전트 create/update 훅 재사용 — 신규 엔드포인트 없음)
```

`constants/api.ts` 변경 **없음** (편승 계약) — api-contract-sync 체크는 요청 타입 확장분만.

### 5-2. DocumentGeneratorConfigPanel 동작

- 문서 유형명·설명 입력 + 섹션 목록 편집(추가/삭제/↑↓ 순서, 각 행 title+guidance).
- 출력 포맷 라디오: **기본 DOCX**, PDF 선택 시 경고문
  "⚠ 현재 PDF 변환은 한글 폰트가 깨질 수 있습니다. 해결 전까지 DOCX를 권장합니다." (D4).
- MCP 변환 도구 선택(선택 입력, 미지정 시 "서버 기본값 사용" 안내 — D5).
- 안내문: "검색 도구(웹 검색·내부 문서 검색)를 함께 선택하면 근거 조사 후 작성합니다.
  없으면 대화 내용만으로 작성됩니다." (D1·D3 — 소스 체크박스 없음).
- 수정 진입 시 저장된 유형 프리필 (PUT 전체교체 프리필 선례).

### 5-3. 테스트 함정 선반영

- vitest `--pool=threads`, MSW per-file listen 3종 훅.
- 섹션 편집 폼: 커스텀 인라인 검증이므로 `noValidate` + 음수/빈 값은 fireEvent 주입.
- 저장 버튼은 공용 `LoadingButton(isPending)` 사용 (mutation-pending-guard).

---

## 6. 테스트 설계 (TDD — Red 먼저)

### 백엔드 (M1)

| 파일 | 검증 |
|------|------|
| `tests/domain/document_generator/test_policies.py` | SectionPolicy(빈/초과/중복/길이), SectionCoveragePolicy(전부 존재·일부 누락·공백 정규화), tool_config 검증 |
| `tests/application/agent_builder/test_document_generation_type_binding.py` | 워커 부재 ValueError, 검증 실패 전파(롤백), tool_config 주입 값, update 교체 시 기존 soft-delete |
| `tests/infrastructure/document_generator/test_generator.py` | 작성 계약(HTML 반환·코드펜스 제거), 섹션 누락 → 재시도 1회 → 경고 진행, 근거 없음 폴백 문구, sanitize 적용, adapter/store 호출 인자 (LLM·adapter mock) |
| `tests/application/agent_builder/test_workflow_compiler_docgen.py` | 분기·function_node_ids 등록, 가드 노옵 3종(D9), 실패 표면화, AIMessage(name) 1건 규약 |
| `tests/application/agent_builder/test_supervisor_docgen_guidance.py` | 가이드 블록 주입 조건(generator+타 워커 공존 시만, 단독 시 미주입), 문구에 "충분하면 바로 위임" 기준 포함 |
| `tests/db/test_migration_ddl_comments.py` | V059 COMMENT 자동 검사 (기존 테스트에 포섭) |

### 프론트 (M2)

- Panel 단위: 섹션 CRUD·순서 변경, PDF 경고문 노출(FR-13), 검증 에러 표시.
- MSW 통합: 유형 포함 에이전트 생성 → 수정 진입 프리필 → 섹션 수정 저장 왕복.

---

## 7. 구현 순서 (M1 → M2)

1. **M1-1** V059 마이그레이션 + models.py (DDL 테스트 Green 확인)
2. **M1-2** domain/document_generator (schemas·policies·tool_config·exceptions) — 테스트 먼저
3. **M1-3** tool_registry에 `document_generator` 추가 (설명에 추출기와 역할 경계 명시)
4. **M1-4** binding 모듈 + create/update use case 편승 + 요청 스키마 — 테스트 먼저
5. **M1-5** generation_type_repository 2종 (추출기 repo 동형)
6. **M1-6** DocumentGenerator (generator.py) — LLM·adapter mock 테스트 먼저
7. **M1-7** workflow_compiler 분기·노드 + supervisor 가이드 블록 (D6)
8. **M1-8** config.py 설정 3건 + main.py DI 배선 → 백엔드 전체 회귀 (격리 실행)
9. **M2-1** types + agentBuilder 요청 확장 (api-contract-sync)
10. **M2-2** DocumentGeneratorConfigPanel + 빌더 연결 — 테스트 먼저
11. **M2-3** MSW 통합 왕복 + 프론트 회귀

## 8. 영향 범위 / 주의사항

- **기존 추출기 무변경** — `HtmlSanitizePolicy`·`McpConversionError`·adapter는 import 재사용만.
  추출기 테스트 전체 통과가 회귀 기준선 (FR-08).
- **repo update() 화이트리스트 함정**: `document_generation_type`은 별도 테이블이라 agent repo
  화이트리스트 무관하지만, **워커 tool_config 갱신**은 기존 workers 저장 경로를 타므로
  update 경로에서 tool_config 반영 여부를 테스트로 고정할 것.
- **supervisor 프롬프트 변경(D6)은 전 에이전트 공유 표면** — 가이드 블록은 generator 워커
  존재 시에만 주입해 기존 에이전트 결정 프롬프트 무변경 보장 (교차 회귀 교훈).
- 쓰기 세션 `begin()` 필수 (agent-memory-extraction 교훈), Repository 내 commit 금지.
- **분석 결과 vs 차트 이미지 경계**: analysis 워커의 수치·표 텍스트는 근거 블록으로 문서에
  반영된다(허용 태그에 table 포함). 그러나 **차트 이미지 삽입은 이번 사이클 불가** — 차트는
  프론트 렌더링 전용(스펙만 생성, chart-rendering-general-chat-only)이라 서버측 이미지
  렌더링이 없다. Plan Out of Scope 유지, 후속 후보(서버측 차트 렌더링)로 명시.
- E2E(실 MCP doc 서버·LLM)는 기존 이월 체크리스트에 합류 — DOCX 산출·한글 정상 여부 실측 필수.
  E2E 시나리오에 "휴가계획서(조사 없이 대화만)"와 "시장조사 보고서(search 선행)" 두 경로 포함.
