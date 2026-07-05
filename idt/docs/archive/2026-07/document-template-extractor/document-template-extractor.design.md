# Design: document-template-extractor

> Created: 2026-07-02
> Phase: Design
> Plan: `docs/01-plan/features/document-template-extractor.plan.md` (rev.6)
> Scope: `idt/` 백엔드 + `idt_front/` 프론트 — 신규 "문서추출기(document_extractor)" 도구. (A) 빌드타임 등록(compiler 무관) + (B) 런타임 실행(compiler 경유).

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 정형 문서(여신심의서 등)는 양식 고정·값만 변동인데, MCP `pdf/doc↔html` 변환 자산을 "양식 등록 → 채팅 자동 완성"으로 잇는 경로가 없다. |
| **Solution** | 도구 `document_extractor` 하나에 두 단계를 설계: (A) stateless 추출 API(`extract`/`refine`) + 에이전트 생성 트랜잭션 편승 저장(`document_template`), (B) `workflow_compiler` 전용 합성 노드(템플릿 로드 → LLM 슬롯 채움 JSON → 순수 토큰 치환 → MCP `html→pdf/doc` → 첨부 저장 → 다운로드 링크). |
| **Function/UX Effect** | 빌더에서 업로드→슬롯 추천 미리보기→확정→생성 payload에 동봉. 채팅에서 "여신금액 5억, oo문서 근거로 소견도" → 완성 PDF/Word 다운로드 링크. 근거 없는 슬롯은 공란+하이라이트. |
| **Core Value** | LLM은 "값 결정"만, 문서 변형은 **순수 문자열 토큰 치환**으로 분리해 재현성 100%. 미근거 공란(GB6) 하드 규칙으로 금융 문서 신뢰성 확보. |

---

## 0. 확정된 설계 결정 (Plan §8-2 잔여 답변)

| # | Open Question | 결정 |
|---|---------------|------|
| **D1** | 작성 지침 위치 | **합성 노드 프롬프트 인라인 상수 확정.** `application/document_extractor/compose_prompt.py`에 `COMPOSE_GUIDELINES`(소견 규칙·근거 제약·GB6)를 상수로 둔다. 도구 config 편집 필드는 **비목표**(범용 지침 필요 시 Skill 분리 후속 — Plan N 계열과 일관). |
| **D2** | 토큰화 실행 지점 | **프론트가 확정 시점에 치환한 `html_skeleton`을 전송.** 사용자가 미리보기 DOM에서 확정한 텍스트 범위를 프론트만 정확히 알기 때문(백엔드 sample_value 문자열 치환은 중복 출현 시 오치환 위험). 백엔드는 저장 직전 `TemplateTokenPolicy`로 **검증만** 수행: ① 모든 slot.key가 `{{key}}`로 1회 이상 존재 ② 슬롯에 정의되지 않은 `{{...}}` 토큰 부재 ③ key 패턴/중복 검증. 검증 실패 = 400, 에이전트 생성 전체 롤백. |
| **D3** | 원본 파일 TTL/권한 | **2단계 보관.** extract 시 `AgentAttachmentStore`에 임시 저장(신규 `AttachmentType.DOCUMENT`, 기존 TTL 적용) → 에이전트 생성 확정 시 `settings.document_template_dir/{template_id}{ext}`로 **복사(영구, TTL 없음)**하고 그 경로를 `source_file_ref`로 저장. soft-delete 후에도 파일 보관(Plan 결정). 원본 다운로드 API는 이번 범위 제외(보관만). **산출 파일**은 owner-only 다운로드(`GET /document-extractor/files/{file_id}`, uploader==viewer 재사용). |
| **D4** | (추가) `(agent_id, worker_id)` 유니크 인덱스 | Plan의 "유니크 인덱스"는 **soft-delete와 충돌**(재등록 시 deleted 행과 유니크 충돌). → **일반 복합 인덱스 `(agent_id, worker_id, status)` + 애플리케이션 레벨 정합**으로 변경: 저장 경로(create/update)가 기존 active 템플릿을 먼저 soft-delete 후 신규 insert. 단일 UseCase·단일 세션이라 race 무시 가능. |
| **D5** | (추가) MCP 변환 도구 id 공급 | extract 요청에 optional 필드로 받되, 미지정 시 `settings.document_extractor_pdf_to_html_tool_id` / `..._html_to_doc_tool_id` 폴백. 둘 다 없으면 400(어떤 MCP 도구가 필요한지 명시). extract 응답이 **실제 사용한 id를 에코** → 프론트가 확정 payload에 그대로 동봉 → `DocumentExtractorToolConfig`에 명시 저장(Plan 결정 3). |
| **D6** | (추가) LLM 채움 출력 계약 | 합성 LLM은 **JSON 오브젝트 `{slot_key: string \| null}`만** 반환(모든 key 필수, 근거 없으면 null — GB6). 파싱 실패 시 1회 재시도, 재실패 시 파일 미생성 + 에러 AIMessage(전면 공란 문서 생성 금지). 치환 자체는 LLM이 아닌 **순수 코드**(`{{key}}` 문자열 치환, 값은 HTML escape) — 재현성 100%. |

---

## 1. 설계 개요

### 1-1. 핵심 아이디어

```
[(A) 빌드타임 — compiler 무관, stateless]
 업로드 → MCP pdf/doc→html → SlotExtractor(LLM) → {html, suggested_slots} 반환
 (refine 재추천 · 유휴 5분 재호출) → 프론트가 확정: 샘플값을 {{key}}로 치환한 html_skeleton 보유
 → POST /agents payload.document_template 동봉
 → CreateAgentUseCase: TemplateTokenPolicy 검증 → document_template 저장(동일 세션)
   + worker.tool_config = DocumentExtractorToolConfig(template_id, mcp ids, output_format)

[(B) 런타임 — compiler 경유]
 workflow_compiler가 tool_id=="document_extractor" 워커를 전용 합성 노드로 컴파일
 → 노드: tool_config.template_id로 템플릿 로드 → state.messages 전체(대화+상류 산출물)
 → LLM 1회: {slot_key: value|null} JSON → 순수 토큰 치환(null→공란 하이라이트)
 → MCP html→pdf/doc(원본 포맷) → AgentAttachmentStore 저장 → 다운로드 링크 AIMessage
```

### 1-2. 목표 그래프 (런타임)

```
supervisor → internal_document_search_worker(search 파이프라인)   # 근거 수집 (선택)
           → document_extractor_worker  = 전용 합성 노드(function node)
                └ quality_gate → supervisor → … → final_answer → END
```

- `document_extractor_worker`는 `function_node_ids`에 포함(analysis/search와 동일하게 `_wrap_worker` 우회, `_wrap_step`으로 관측성 유지).
- 엣지는 기존 워커와 동일: `worker → quality_gate` 직결. chart_router 경유 없음.
- `flow_hint`는 기존 생성 로직(`" → ".join(tool_ids)`)이 자동 생성 — "리서치 → 문서 합성" 순서 유도(GB4).

---

## 2. 데이터 모델

### 2-1. Domain VO — `src/domain/document_extractor/schemas.py` (신규)

```python
SlotType = Literal["value", "generated"]
SLOT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,49}$")   # 토큰 안전(ASCII)

@dataclass(frozen=True)
class TemplateSlot:
    key: str                    # 토큰명. anchor = "{{key}}" (프로퍼티로 노출)
    label: str                  # 화면/하이라이트 표기 (한글 가능, ≤100자)
    slot_type: SlotType         # value=사실 값 | generated=근거 기반 서술
    description: str = ""       # ≤300자
    fill_hint: str = ""         # 채움 힌트("숫자+단위 그대로" 등, ≤300자)
    sample_value: str = ""      # 원본 문서에서 추출된 예시값 (≤500자)

    @property
    def anchor(self) -> str:    # "{{loan_amount}}"
        return "{{" + self.key + "}}"

@dataclass
class DocumentTemplate:
    id: str
    agent_id: str
    worker_id: str              # "document_extractor_worker"
    name: str
    html_skeleton: str          # {{key}} 토큰화된 HTML (방식 A)
    slots: list[TemplateSlot]
    source_file_ref: str        # 영구 보관 원본 경로 (D3)
    source_format: str          # "pdf" | "docx"
    status: str                 # "active" | "deleted" (soft-delete)
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class SuggestedSlots:           # 추출/재추천 DTO
    slots: list[TemplateSlot]
```

### 2-2. Domain Policy — `src/domain/document_extractor/policies.py` (신규)

| Policy | 규칙 | 위반 시 |
|--------|------|---------|
| `DocumentFilePolicy` | 확장자 ∈ {.pdf, .docx}(v1 — .doc/.hwp 제외), 빈 파일 금지, 크기 ≤ `max_file_mb` | `InvalidDocumentError` / `DocumentTooLargeError` |
| `SlotPolicy` | 슬롯 1~`max_slots`(기본 30)개, key는 `SLOT_KEY_PATTERN`+중복 금지, label 필수, slot_type ∈ {value, generated}, 길이 상한 | `InvalidSlotError` |
| `TemplateTokenPolicy` (D2) | ① 모든 slot의 `{{key}}`가 html_skeleton에 ≥1회 존재 ② skeleton 내 `{{...}}` 토큰은 전부 슬롯에 정의 ③ skeleton 비어있지 않음, ≤ `max_skeleton_bytes` | `TemplateTokenMismatchError` |
| `RegenPolicy` | `regen_count < MAX_REGEN`(settings, 기본 10). 초과 시 거부+로깅(R5) | `RegenLimitExceededError` |
| `UnfilledSlotPolicy` (GB6) | 순수 판정: `value is None or value.strip() == ""` → 공란. 공란 마크업 상수 `render_unfilled(slot)` = `<mark data-unfilled="{key}" style="background:#FFF3B0">{label}</mark>` | — |
| `SlotValuePolicy` | 채움 값에서 `{{`/`}}` 제거(토큰 주입 방지), HTML escape는 치환기에서 수행 | — |

파일 검증/슬롯 규칙/공란 판정은 전부 **순수 함수**(외부 의존 없음) — domain 레이어 금지사항 준수.

### 2-3. Tool Config — `src/domain/document_extractor/tool_config.py` (신규)

```python
@dataclass(frozen=True)
class DocumentExtractorToolConfig:      # RagToolConfig 패턴 (frozen + __post_init__ 검증)
    template_id: str                            # 지정 템플릿 (그 도구 전용)
    mcp_pdf_to_html_tool_id: str                # "mcp_{uuid}" — 명시 저장 (Plan 결정 3)
    mcp_html_to_doc_tool_id: str                # "mcp_{uuid}"
    output_format: str                          # "pdf" | "docx" — 원본 포맷 따름 (Plan 결정 4)

    # __post_init__: template_id 필수, mcp id는 "mcp_" 접두사, output_format ∈ {pdf, docx}
```

`WorkerDefinition.tool_config: dict`에 `model_dump()` 형태로 저장(기존 RagToolConfig와 동일한 직렬화 경로 — agent_tool JSON 컬럼 재사용, 스키마 변경 없음).

### 2-4. DB — `db/migration/V037__create_document_template.sql` (신규)

```sql
CREATE TABLE document_template (
    id            VARCHAR(36)  NOT NULL PRIMARY KEY,
    agent_id      VARCHAR(36)  NOT NULL,
    worker_id     VARCHAR(100) NOT NULL,
    name          VARCHAR(200) NOT NULL,
    html_skeleton LONGTEXT     NOT NULL,
    slots         JSON         NOT NULL,          -- TemplateSlot 배열 통째 (Plan 결정 2(저장))
    source_file_ref VARCHAR(500) NOT NULL,
    source_format VARCHAR(10)  NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    KEY idx_document_template_agent_worker (agent_id, worker_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- **유니크 인덱스 없음(D4)** — "도구당 active 템플릿 1개"는 저장 UseCase가 보장(기존 active soft-delete 후 insert).
- FK는 기존 마이그레이션 관례 확인 후 Do 단계에서 결정(`agent_definition` 참조 관례가 없으면 인덱스만).
- `/db-migration` 스킬로 models.py → DDL 추출·검증.

### 2-5. ORM — `src/infrastructure/document_extractor/models.py` (신규)

`DocumentTemplateModel` (SQLAlchemy): 위 컬럼 매핑. slots는 `JSON` 타입 — repository가 `TemplateSlot` 리스트 ↔ JSON 배열 변환.

---

## 3. (A) 빌드타임 등록 상세

### 3-1. API — `src/api/routes/document_extractor_router.py` (신규)

| Method | Path | Auth | 설명 |
|--------|------|------|------|
| POST | `/api/v1/document-extractor/extract` | `get_current_user` | multipart 업로드 → HTML+추천 슬롯 (stateless) |
| POST | `/api/v1/document-extractor/refine` | `get_current_user` | 재추천 (stateless, 상한) |
| GET | `/api/v1/document-extractor/files/{file_id}` | `get_current_user` | (B)에서 생성된 산출 파일 다운로드 (owner-only) |

DI는 `agent_attachment_router` 패턴: placeholder 함수 + `main.py` lifespan override.

#### `POST /extract` — Request (multipart form)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file` | UploadFile | ✔ | PDF/Word 원본 |
| `mcp_pdf_to_html_tool_id` | Form(str) | — | 미지정 시 settings 폴백 (D5) |
| `mcp_html_to_doc_tool_id` | Form(str) | — | 확정 payload용 에코 대상 (D5) |

#### `POST /extract` — Response 200

```json
{
  "source_file_id": "a3f...hex32",          // AgentAttachmentStore 임시 file_id
  "source_format": "pdf",
  "html": "<html>…원본 변환 HTML…</html>",   // sanitize 후 (script/iframe 제거)
  "suggested_slots": [
    {"key": "loan_amount", "label": "여신금액", "slot_type": "value",
     "description": "신청 여신금액", "fill_hint": "숫자+단위 그대로", "sample_value": "500,000,000원"},
    {"key": "opinion", "label": "소견", "slot_type": "generated",
     "description": "심사역 소견", "fill_hint": "근거 문서 기반 3~5문장", "sample_value": "…"}
  ],
  "mcp_pdf_to_html_tool_id": "mcp_xxx",     // 실제 사용 id 에코 (D5)
  "mcp_html_to_doc_tool_id": "mcp_yyy"
}
```

#### `POST /refine` — Request/Response (JSON)

```json
// Request
{ "html": "...", "instruction": "금액 항목을 더 잘게 나눠줘",
  "prev_slots": [ …TemplateSlot… ], "regen_count": 2 }
// Response 200
{ "suggested_slots": [ … ] }
```

`regen_count`는 프론트가 증가시켜 전달(유휴 5분 재생성 포함) — `RegenPolicy.validate(regen_count)` 초과 시 429 + 로깅(R5).

#### 에러 계약 (공통 `{"code", "message"}` detail)

| Status | code | 원인 |
|--------|------|------|
| 400 | `INVALID_DOCUMENT` | 미허용 확장자/빈 파일 |
| 413 | `DOCUMENT_TOO_LARGE` | 크기 초과 |
| 400 | `MCP_TOOL_NOT_CONFIGURED` | 변환 MCP id 미지정+settings 폴백 부재 (어떤 도구가 필요한지 메시지 명시) |
| 502 | `MCP_CONVERSION_FAILED` | MCP 연결/변환 실패 (CC 메모리: 'Session terminated'=404 진단 힌트 포함) |
| 502 | `SLOT_EXTRACTION_FAILED` | LLM 추출 실패(슬롯 0개는 실패 아님 — 빈 배열 정상 반환, 수동 지정 허용) |
| 429 | `REGEN_LIMIT_EXCEEDED` | MAX_REGEN 초과 |
| 404/403 | `FILE_NOT_FOUND` / `FORBIDDEN` | 다운로드: 부재 / owner 불일치 |

### 3-2. UseCase — `src/application/document_extractor/`

**`extract_use_case.py` — `ExtractDocumentUseCase.execute(file_bytes, filename, owner_user_id, mcp_ids, request_id)`**
1. `DocumentFilePolicy.validate(filename, size)` → source_format 결정(확장자).
2. `AgentAttachmentStore.save(type=DOCUMENT)` → `source_file_id` (TTL 임시 — D3).
3. `DocumentConversionAdapter.to_html(file_bytes, source_format, mcp_tool_id, request_id)` → raw HTML.
4. `HtmlSanitizer.clean(raw_html)` — script/on* 속성/iframe 제거(R7 방어 1선).
5. `SlotExtractor.extract(html, request_id)` → `SuggestedSlots`.
6. 응답 조립(사용한 mcp id 에코).

**`refine_use_case.py` — `RefineSlotsUseCase.execute(html, instruction, prev_slots, regen_count, request_id)`**
1. `RegenPolicy.validate(regen_count)`.
2. `SlotExtractor.refine(html, instruction, prev_slots, request_id)` → `SuggestedSlots`.

**`schemas.py`** — 위 요청/응답 Pydantic 모델(`ExtractResponse`, `RefineRequest/Response`, `TemplateSlotDto`).

둘 다 **stateless** — 서버 영속 상태 없음(Plan §3-4). `workflow_compiler` 미경유(GA2).

### 3-3. Infra — 슬롯 추출/변환

**`slot_extractor.py` — `SlotExtractor(llm_factory, llm_model_repository, logger)`**
- LLM: `llm_model_repository.find_default()` → `llm_factory.create(model, temperature=0.0)` (인스턴스 캐시).
- extract 프롬프트: HTML 제공 → "반복 문서에서 매번 바뀔 값(value)과 근거 기반 작성 항목(generated)을 JSON 배열로" (key는 영문 스네이크 강제, sample_value는 원본에서 그대로 발췌). refine 프롬프트: prev_slots + instruction 반영 재추천.
- 출력: JSON 파싱 → `SlotPolicy.validate` 통과분만 반환(불량 슬롯 drop + warning 로그). 파싱 실패 1회 재시도 후 `SLOT_EXTRACTION_FAILED`.

**`document_conversion_adapter.py` — `DocumentConversionAdapter(mcp_tool_loader, mcp_repository, logger)`**
- `to_html(file_bytes, fmt, mcp_tool_id, request_id) -> str` / `to_document(html, fmt, mcp_tool_id, request_id) -> bytes`.
- 내부: `MCPToolLoader.load_by_tool_id(tool_id, repository, request_id)` → `tool.ainvoke(...)`.
- **MCP 도구 입출력 계약은 서버마다 다름(R1)** → 어댑터가 정규화 계층: 입력은 base64/URL 중 도구 스키마에 맞춰 조립, 출력은 base64 문자열/URL/plain 텍스트를 감지해 bytes/str로 정규화. **Do 착수 전 등록된 실제 변환 MCP로 PoC 1회 필수**(`/verify-mcp-connections` 활용) — 계약 확정 후 정규화 로직 고정.
- 도구 미등록/로드 실패: 필요한 도구가 무엇인지 포함한 `McpConversionError` (§3-1 502 매핑).

### 3-4. 에이전트 생성/수정 시 템플릿 저장

**요청 스키마 확장 — `src/application/agent_builder/schemas.py`** (additive)

```python
class DocumentTemplateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    html_skeleton: str                          # {{key}} 토큰화 완료본 (D2 — 프론트 치환)
    slots: list[TemplateSlotDto]                # ≥1
    source_file_id: str                         # extract가 발급한 임시 file_id
    source_format: str = Field(..., pattern="^(pdf|docx)$")
    mcp_pdf_to_html_tool_id: str
    mcp_html_to_doc_tool_id: str

class CreateAgentRequest(BaseModel):
    ...  # 기존 필드 유지
    document_template: DocumentTemplateRequest | None = None   # ★ 신규 (additive)

class UpdateAgentRequest(BaseModel):
    ...
    document_template: DocumentTemplateRequest | None = None   # None=변경 없음
```

> `tool_configs: dict[str, RagToolConfigRequest]`는 **건드리지 않는다**(union 판별 리스크 회피). 문서추출기 설정은 전용 필드로 분리 — 기존 RAG 경로 무회귀.

**`create_agent_use_case.py` 변경점** (Step 4 이후, Step 4.5 스킬 동기화와 동일 패턴)

```
Step 4.6 (신규): request.document_template 존재 시
  a. "document_extractor" tool 워커 존재 검증 (없으면 ValueError → 400)
  b. TemplateTokenPolicy / SlotPolicy 검증 (실패 → 예외 전파 = 전체 롤백, R6)
  c. 원본 승격(D3): attachment_store.load(source_file_id) →
     document_template_dir/{template_id}{ext} 복사 → source_file_ref
     (임시 file_id 부재 시 ValueError — 프론트에 재추출 안내, R4)
  d. document_template_repository.save(DocumentTemplate(agent_id=saved.id,
     worker_id="document_extractor_worker", status="active", ...))  # 동일 세션
  e. 해당 워커 tool_config = DocumentExtractorToolConfig(...).model_dump()
     → repository로 agent_tool 갱신 (동일 세션)
```

- 템플릿 없이 `document_extractor`만 선택된 생성은 **허용**(경고 로그) — 런타임 노드가 안내 노옵(§4-4).
- **update**: `document_template` 제공 시 기존 active 템플릿 soft-delete → 신규 insert → tool_config 갱신(D4). 원본은 새로 승격.
- **에이전트 삭제**: delete 경로에서 해당 agent의 active 템플릿 soft-delete(원본 파일 보관 — Plan 결정 7/8).
- 트랜잭션: 전 과정 **요청 단위 단일 세션**(CLAUDE.md: repository 내 commit 금지, UseCase 간 세션 공유) — 부분 실패 시 에이전트 생성까지 원자 롤백(R6).

### 3-5. `TOOL_REGISTRY` 등록 — `src/domain/agent_builder/tool_registry.py`

```python
"document_extractor": ToolMeta(
    tool_id="document_extractor",
    name="문서추출기",
    description=(
        "등록된 문서 양식(템플릿)을 대화와 수집된 근거로 채워 "
        "PDF/Word 파일로 생성합니다. 정형 문서(심의서·보고서) 자동 작성에 사용하세요."
    ),
    requires_env=[],
    category="action",
),
```

`GET /agents/tools`는 기존 로직으로 자동 노출(GA1). description은 **런타임 supervisor 라우팅 기준** — "문서 생성/작성" 의도에 매칭되도록 서술.

---

## 4. (B) 런타임 실행 상세

### 4-1. WorkflowCompiler 변경 — `src/application/agent_builder/workflow_compiler.py`

**생성자 확장** (optional, 하위호환):

```python
def __init__(self, ...,
    document_template_repository=None,     # DocumentTemplateRepositoryInterface | None
    document_composer=None,                # DocumentComposer | None
) -> None:
```

**compile 루프 분기** — `category` 해석 직후, mcp/tool 생성보다 먼저:

```python
if worker_def.tool_id == "document_extractor":
    worker_map[worker_def.worker_id] = self._create_document_extractor_node(
        llm, worker_def,
    )
    function_node_ids.add(worker_def.worker_id)
    continue
```

- `function_node_ids` 합류 → `_wrap_worker` 우회 + `_wrap_step(NodeType.WORKER)` 관측성 유지.
- 엣지: 기존 규칙 그대로 `worker → quality_gate`(analysis 아님 → chart_router 미경유).
- ToolFactory 경유하지 않음(단일 툴 react agent 미채택 — Plan §3-3 확정).

### 4-2. 합성 노드 — `_create_document_extractor_node(llm, worker_def)`

```
async def node(state):
  1. 가드: repo/composer 미주입 or tool_config.template_id 부재
       → AIMessage("문서 템플릿이 등록되지 않았습니다. 에이전트 편집에서 양식을 등록하세요.")
  2. template = repo.find_by_id(tool_config["template_id"])
       (None or status!="active" → 1과 동일 안내, 노옵)
  3. fill_context = state["messages"] 전체 (대화 + 상류 워커 산출물 — GB2)
  4. result = await composer.compose(
       llm=llm, template=template,
       tool_config=DocumentExtractorToolConfig(**worker_def.tool_config),
       messages=fill_context,
       owner_user_id=auth_ctx.user_id,   # compile 클로저 캡처 (산출물 owner)
       request_id=request_id)
  5. AIMessage(name=worker_id, content=요약) 반환 + last_worker_id + token_usage
```

**AIMessage content 형식** (final_answer가 자연스럽게 인용 가능한 평문):

```
문서 「{template.name}」 생성 완료 ({output_format.upper()})
다운로드: /api/v1/document-extractor/files/{file_id}

[채운 항목] 여신금액=5억 원 · 신청일자=2026-07-02 · …
[공란(근거 없음 — 직접 확인 필요)] 담당자 연락처, 소견   ← GB6 하이라이트 항목
```

### 4-3. Composer — `src/infrastructure/document_extractor/composer.py` (신규)

`DocumentComposer(conversion_adapter, attachment_store, logger)` — LLM은 호출 시 인자로 수령(per-run 에이전트 LLM 사용, compile 시점 주입).

```
async compose(llm, template, tool_config, messages, owner_user_id, request_id) -> ComposeResult:
  1. 프롬프트 = COMPOSE_GUIDELINES(D1 인라인 상수)
       + 슬롯 정의(key/label/type/fill_hint)
       + "[근거 자료] = 검색 결과·워커 산출물" / "[대화]" 블록 분리
         (final_answer 노드의 _is_worker_output/_is_search_result 분류 재사용)
       + GB6: "근거가 없는 슬롯은 반드시 null. 추정·작문 금지.
              value는 발화/근거의 사실만, generated는 근거 문서 내용만 기반."
  2. llm.ainvoke → JSON {key: value|null} 파싱 (모든 key 존재 강제)
       파싱/키 누락 실패 → 1회 재시도 → 재실패 시 ComposeError (D6, 파일 미생성)
  3. 순수 치환 (재현성 100%, 테스트 대상):
       for slot in template.slots:
         value = SlotValuePolicy.sanitize(values[slot.key])
         filled = html_escape(value)            if not UnfilledSlotPolicy.is_unfilled
                = render_unfilled(slot)         else   # <mark data-unfilled=…>{label}</mark>
         html = html.replace(slot.anchor, filled)
  4. bytes = await conversion_adapter.to_document(html, tool_config.output_format,
                                                  tool_config.mcp_html_to_doc_tool_id, request_id)
  5. stored = attachment_store.save(bytes, f"{template.name}.{ext}",
                                    AttachmentType.DOCUMENT, owner_user_id)
  6. return ComposeResult(file_id, filename, filled_slots: dict, unfilled_slots: list[label])
```

- MCP 변환 실패 → `ComposeError`(필요 MCP 도구 명시) → 노드가 에러 AIMessage(그래프 비중단, `_run_excel_analysis` 실패 처리 패턴).
- 작성 지침 상수 `COMPOSE_GUIDELINES`는 `application/document_extractor/compose_prompt.py`(D1) — composer가 import (infra→application 방향 금지이므로 **compose 시 인자로 프롬프트 수신** 또는 상수를 domain `policies.py`에 배치. **결정: 상수는 domain `policies.py`의 `COMPOSE_GUIDELINES`** — 순수 문자열 규칙이라 domain 적합, application/infra 양쪽에서 참조 가능).

### 4-4. 산출 파일 다운로드

- `AgentAttachmentStore` 재사용: `AttachmentType.DOCUMENT` 추가(`value_objects.py`), 허용 확장자 .pdf/.docx 확장(업로드 UseCase의 타입 판정 분기 포함).
- `GET /api/v1/document-extractor/files/{file_id}`: `store.load(file_id)` → 부재 404 / `owner_user_id != current_user.id` 403 → `FileResponse`(Content-Disposition 원본 파일명).
- TTL: 기존 store TTL 정책 그대로(산출물은 일회성 — 만료 후 재실행 안내). 원본(source_file_ref)은 영구 디렉토리라 TTL 무관(D3).

---

## 5. 설정 — `src/config.py` (신규 키)

| 키 | 기본값 | 용도 |
|----|--------|------|
| `document_extractor_max_file_mb` | 20 | 업로드 상한 (R8) |
| `document_extractor_max_slots` | 30 | 슬롯 개수 상한 |
| `document_extractor_max_regen` | 10 | refine/재생성 상한 (R5) |
| `document_template_dir` | `uploads/document_templates` | 원본 영구 보관 (D3) |
| `document_extractor_pdf_to_html_tool_id` | `""` | 기본 MCP 변환 도구 (D5 폴백) |
| `document_extractor_html_to_doc_tool_id` | `""` | 〃 |

`.env.example`에 주석과 함께 추가. 하드코딩 금지 규칙 준수.

---

## 6. DI 배선 — `src/api/main.py`

```
lifespan:
  conversion_adapter = DocumentConversionAdapter(mcp_tool_loader, mcp_registry_repository, logger)
  slot_extractor     = SlotExtractor(llm_factory, llm_model_repository, logger)
  extract_uc         = ExtractDocumentUseCase(attachment_store, conversion_adapter, slot_extractor, logger)
  refine_uc          = RefineSlotsUseCase(slot_extractor, logger)
  document_template_repo = DocumentTemplateRepository(session_factory, logger)
  document_composer  = DocumentComposer(conversion_adapter, attachment_store, logger)

  # 기존 객체 확장
  WorkflowCompiler(..., document_template_repository=document_template_repo,
                        document_composer=document_composer)
  CreateAgentUseCase(..., document_template_repo=document_template_repo,
                          attachment_store=attachment_store)   # update도 동일
  app.dependency_overrides[get_extract_use_case] = ...          # router placeholder 패턴
```

세션 규칙: `DocumentTemplateRepository`는 요청 세션 주입 방식(기존 repo 패턴)과 동일 — `get_session_factory()()` 직접 생성 금지, commit/rollback 없음.

---

## 7. 프론트엔드 (idt_front/) — API 계약 & 컴포넌트

### 7-1. 계약 동기화 (`/api-contract-sync` 대상)

| 백엔드 | 프론트 |
|--------|--------|
| `POST /document-extractor/extract` / `refine` / `GET files/{id}` | `src/constants/api.ts` 상수 + `src/services/documentExtractor.ts` |
| `ExtractResponse`, `TemplateSlotDto`, `DocumentTemplateRequest` | `src/types/documentExtractor.ts` |
| `CreateAgentRequest.document_template` 확장 | 기존 agent 생성 서비스/타입 확장 |

### 7-2. 핵심 컴포넌트/흐름

| 컴포넌트 | 책임 |
|----------|------|
| `DocumentExtractorWizard` | 빌더에서 `document_extractor` 선택 시 업로드 스텝 모달. mcp 변환 도구 선택(기본값 = settings 에코) |
| `TemplatePreview` | **sandbox iframe**(`sandbox="allow-same-origin"` 없이) HTML 렌더 + 슬롯 하이라이트 오버레이 (R7 방어 2선) |
| `SlotConfirmPanel` | 추천 슬롯 수락/삭제/수동 추가/라벨 편집 → 확정 시 **sample_value → `{{key}}` 치환 실행(D2)** |
| `useIdleResuggest` | 미확정 5분 유휴 감지 → refine 재호출(`regen_count` 증가, 상한 도달 시 중지) |
| 폼 보유 | 확정 결과(`document_template` payload)를 빌더 폼 상태(+sessionStorage 드래프트, R4)로 보유 → 생성/수정 payload 동봉 |
| 채팅 | AIMessage 내 다운로드 경로 링크 렌더(기존 마크다운 링크 렌더 재사용) |

프론트 치환 규칙(D2): 사용자가 하이라이트로 확정한 **DOM 텍스트 노드 범위**를 `{{key}}`로 교체 → `html_skeleton` 직렬화. 동일 sample_value 다중 출현 문제를 프론트 선택 UI로 해소.

---

## 8. 테스트 계획 (TDD — Red → Green → Refactor)

| 파일 | 검증 |
|------|------|
| `tests/domain/document_extractor/test_policies.py` | 파일 확장자/크기/빈 파일, slot key 패턴·중복·상한, `MAX_REGEN`, **GB6 공란 판정 + 하이라이트 마크업**, 토큰 정합(누락 토큰/미정의 토큰/정상) |
| `tests/domain/document_extractor/test_tool_config.py` | config 필수값·mcp_ 접두사·output_format 검증 |
| `tests/application/document_extractor/test_extract_use_case.py` | (모의 MCP/LLM/store) 정상 추출, 미허용 파일 400, MCP 미설정/실패 에러 코드, sanitize 적용, 슬롯 0개 정상 |
| `tests/application/document_extractor/test_refine_use_case.py` | 재추천, regen 상한 초과 |
| `tests/application/agent_builder/test_create_agent_use_case.py` (확장) | document_template 동봉 생성 → 템플릿 저장+tool_config 연결, 토큰 검증 실패 롤백, document_extractor 워커 부재 시 400, 템플릿 없는 생성 허용 |
| `tests/application/agent_builder/test_update_agent_use_case.py` (확장) | 템플릿 교체 = 기존 soft-delete + 신규 insert |
| `tests/application/agent_builder/test_workflow_compiler.py` (확장) | `document_extractor` 워커 → function node 컴파일, 템플릿 미등록 안내 노옵, composer 호출 배선, repo 미주입 하위호환 |
| `tests/infrastructure/document_extractor/test_repository.py` | CRUD + soft-delete + active 조회 |
| `tests/infrastructure/document_extractor/test_composer.py` | **토큰 치환 재현성(같은 입력→같은 출력)**, HTML escape, **GB6: null 슬롯 공란+하이라이트·추정값 미생성**, JSON 재시도/실패 시 파일 미생성, MCP 실패 에러 |
| `tests/infrastructure/document_extractor/test_conversion_adapter.py` | (모의 MCPToolLoader) to_html/to_document 정규화, 도구 부재 에러 메시지 |
| `tests/api/test_document_extractor_router.py` | 3 엔드포인트 상태코드/에러 계약/owner 403 |

- 실행: **Windows 격리 pytest**(CC 메모리 — 교차 실행 flakiness), 사전 실패 28+30건은 회귀로 오인 금지(CC 메모리).
- 검증 스킬: `verify-architecture`(domain 순수성), `verify-logging`(LOG-001), `verify-tdd`, `verify-mcp-connections`(PoC·실연결).

---

## 9. 구현 순서 (Do 체크리스트 — Plan §6 매핑)

```
Phase 1 (A: 추출·등록)
 1. [ ] domain: schemas / policies / tool_config (+tests Red→Green)
 2. [ ] TOOL_REGISTRY 등록 (+tests)
 3. [ ] ★ MCP 변환 PoC: 등록된 pdf↔html MCP 실도구로 어댑터 계약 확정 (R1, /verify-mcp-connections)
 4. [ ] infra: conversion_adapter / slot_extractor (모의 테스트)
 5. [ ] app/api: extract_use_case + router + main.py DI / AttachmentType.DOCUMENT 확장
 6. [ ] V037 마이그레이션 + models + repository / create·update_agent 템플릿 저장 연결
Phase 2 (B: 런타임)
 7. [ ] composer (+GB6·재현성 테스트) / files 다운로드 엔드포인트
 8. [ ] workflow_compiler 합성 노드 + DI 배선
Phase 3
 9. [ ] refine_use_case + 라우터 (+상한 테스트)
Phase 4
10. [ ] /api-contract-sync → idt_front 타입/서비스/훅 + 위저드/미리보기/확정/드래프트/유휴 재추천
11. [ ] verify-architecture / verify-logging / verify-mcp-connections / 격리 pytest 전체
```

---

## 10. 주의사항 / 영향 범위

- **무회귀(additive)**: 기존 워커 컴파일 경로 분기는 `tool_id == "document_extractor"` 한 줄 선행 분기 — RAG/search/analysis/MCP 경로 불변. `tool_configs` 스키마 불변(전용 필드 분리).
- **레이어 준수**: domain은 순수(정규식·dataclass만). LLM/MCP/DB는 전부 infrastructure. compiler(application)가 infra 구현체를 주입받는 기존 관례 유지.
- **함수 40줄/중첩 2단계**: 합성 노드는 가드 절 조기 반환으로 유지, composer는 단계별 private 메서드 분해.
- **R1(HTML 품질)**: PoC(체크리스트 3번)를 Phase 1 중반에 강제 배치 — 계약 불일치 조기 발견.
- **보안**: 업로드 확장자·크기 검증(domain), HTML sanitize(백엔드) + sandbox iframe(프론트) 이중 방어, file_id uuid4 hex + owner 검사, 원본/산출물 경로는 file_id·template_id로만 구성(path traversal 차단 — store 패턴 계승).
