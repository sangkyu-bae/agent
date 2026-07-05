# Design: nl-agent-composer

> Created: 2026-07-04
> Phase: Design
> Plan: `docs/01-plan/features/nl-agent-composer.plan.md`
> Scope: `idt/` 백엔드 — 자연어 → 내부+MCP 도구 조합 에이전트 초안(무저장) 단발 API. 완전 신규 모듈(`agent_composer`) + 저장 경로 최소 확장(FR-08/09).

---

## 0. 확정된 설계 결정 (Plan Open Questions 답변)

| # | Open Question | 결정 |
|---|---------------|------|
| **D1** (R3) | 초안 system_prompt 저장 반영 | **`CreateAgentRequest`에 `system_prompt: str \| None` 필드 추가.** 값이 오면 `PromptGenerator` 호출을 건너뛰고 검증(`AgentBuilderPolicy.validate_system_prompt`) 후 그대로 저장. 기존 호출자는 `None`이라 무회귀. 프론트 타입 동기화는 프론트 후속 feature에서 `/api-cotract`로 수행. |
| **D2** (R2) | tool_catalog에 MCP 항목 0건일 때 | **서버 단위 메타 폴백.** `mcp_registry.find_all_active`로 서버 name/description을 후보에 합류(`GET /agents/tools`와 동일 소스). 폴백 발생 시 warning 로그 + 응답 `notes`에 "MCP 도구 동기화 전 — 서버 단위 정보로 제안됨" 명시. |
| **D3** | LLM 호출 횟수 (1회 vs 2회) | **1회 structured output 통합** (역량 분해 + coverage + 도구 선택 + flow_hint + system_prompt + 이름 제안). 근거: compose는 미리보기라 지연 민감, 추가 I/O 최소화(NFR-01). `AgentComposer` 내부 메서드는 `_build_candidates_block` / `_parse_output`으로 분리해 향후 2회 분리 전환이 가능하게 유지. |
| **D4** | 라우터 파일 | **신규 `src/api/routes/agent_composer_router.py`** (기존 agent_builder_router 700줄 비대). `prefix="/api/v1/agents"`, 경로 `POST /compose`. 기존 라우터에 `POST /{agent_id}` 단일 세그먼트 라우트가 없으므로 등록 순서 무관하게 충돌 없음(검증 완료). |
| **D5** | compose에 쓰는 LLM | **빌더 LLM**(기존 ToolSelector/PromptGenerator와 동일: `ChatOpenAI(settings.openai_llm_model, temperature=0)`, `main.py:1974` 패턴). 요청의 `llm_model_id`는 **초안 에이전트의 실행 모델 필드**로만 해석(미지정 시 `find_default`). |
| **D6** | 내부 도구 후보 소스 | **내부 = `TOOL_REGISTRY`(도메인, 항상 최신), MCP = tool_catalog(`source="mcp"`)**. 내부 도구까지 카탈로그에 의존하면 stale 위험이 있어 분리. |
| **D7** | 정책 위반 초안 처리 | **에러가 아니라 clamp + notes.** 도구 수 > `MAX_TOOLS(5)` → sort_order 앞 5개만 유지하고 잘린 도구는 notes에 기재. system_prompt > 4000자 → 4000자 절단 + notes. coverage는 서버가 **재산정**(LLM 판정을 신뢰하지 않음, §3-3). |

---

## 1. 설계 개요

### 1-1. 전체 시퀀스

```
POST /api/v1/agents/compose  (인증: get_current_user)
  │ ComposeAgentUseCase.execute(request, request_id)
  │
  ├─ 1) llm_model_id 해석: find_by_id | find_default   (응답 필드용)
  ├─ 2) 후보 수집 CandidateCollector
  │      내부: TOOL_REGISTRY → CandidateTool(source="internal")
  │      MCP : tool_catalog.list_active() 중 source=="mcp"
  │            → CandidateTool(tool_id="mcp:{srv}:{tool}", mcp_server_id=srv)
  │            0건이면 mcp_repo.find_all_active() 폴백(D2)
  │            → CandidateTool(tool_id="mcp_{srv}", server_level=True)
  ├─ 3) AgentComposer.compose(user_request, candidates)   ← LLM 1회 (D3)
  │      → _ComposeOutput(capabilities[], workers[], flow_hint,
  │                        system_prompt, agent_name)
  ├─ 4) DraftAssembler (application 내 순수 함수)
  │      a. 환각 tool_id drop (후보 id set 대조, FR-06)
  │      b. mcp:{srv}:{tool} → mcp_{srv} 매핑 + 서버 단위 dedupe (FR-05)
  │      c. ComposePolicy.clamp (도구 수/프롬프트 길이, D7)
  │      d. ComposePolicy.derive_coverage 재산정 (§3-3)
  └─ 5) ComposeAgentDraftResponse 반환 — DB 쓰기 0건
```

### 1-2. 저장 연결 (기존 API 최소 확장)

```
프론트(후속): 초안 → 생성 폼 프리필 → 저장 버튼
  ▼
POST /api/v1/agents  (기존)
  body = { name, user_request, tool_ids: ["tavily_search","mcp_abc"],
           system_prompt: "<화면에서 수정된 초안>",     ← FR-09 (D1)
           llm_model_id, temperature, visibility, ... }
  │
  ├─ _build_skeleton_from_tool_ids: "mcp_" 접두사 분기 신설 (FR-08)
  │     mcp_* → mcp_server_repo.find_by_id(server_id)로 name/description 해석
  └─ Step 3: request.system_prompt 있으면 PromptGenerator 스킵 (FR-09)
```

---

## 2. 신규 파일 상세

### 2-1. `src/domain/agent_composer/schemas.py`

```python
"""agent_composer 도메인 VO — 외부 의존 없음(순수 dataclass)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CandidateTool:
    tool_id: str                  # 내부: "excel_export" / MCP: "mcp:{srv}:{tool}" / 폴백: "mcp_{srv}"
    name: str
    description: str
    source: str                   # "internal" | "mcp"
    mcp_server_id: str | None = None
    server_level: bool = False    # D2 폴백 여부(개별 도구 아님)


@dataclass(frozen=True)
class MissingCapability:
    capability: str               # 예: "사내 ERP 조회"
    reason: str                   # 예: "매칭되는 내부/MCP 도구 없음"
    suggestion: str = ""          # 예: "ERP MCP 서버 등록 필요"


@dataclass(frozen=True)
class ComposedDraft:
    """DraftAssembler 산출물 — application 응답 조립의 입력."""
    coverage: str                                  # "full" | "partial" | "none"
    name_suggestion: str
    system_prompt: str
    workers: list                                  # list[WorkerDefinition] (agent_builder 도메인 재사용)
    flow_hint: str
    missing_capabilities: list[MissingCapability] = field(default_factory=list)
    notes: str = ""
```

- `WorkerDefinition`은 `src/domain/agent_builder/schemas.py`의 기존 도메인 VO를 재사용한다(도메인→도메인 참조는 허용, 저장 경로와 타입 일치가 목적). agent_builder **application** 코드는 참조하지 않는다.

### 2-2. `src/domain/agent_composer/policies.py`

```python
class ComposePolicy:
    """초안 보정·판정 규칙 — LLM 출력을 신뢰하지 않고 서버가 최종 결정."""

    @staticmethod
    def drop_unknown_tools(workers, candidate_ids: set[str]) -> tuple[list, list[str]]:
        """후보에 없는 tool_id 제거. (남은 워커, drop된 id 목록) 반환."""

    @staticmethod
    def clamp_tool_count(workers, max_tools: int) -> tuple[list, list[str]]:
        """sort_order 오름차순 상위 max_tools 유지. (유지 워커, 잘린 tool_id) 반환."""

    @staticmethod
    def clamp_system_prompt(prompt: str, max_length: int) -> tuple[str, bool]:
        """max_length 초과 시 절단. (프롬프트, 절단 여부) 반환."""

    @staticmethod
    def derive_coverage(worker_count: int, missing: list) -> str:
        """서버 재산정: 워커 0 → 'none' / missing 있음 → 'partial' / 그 외 'full'."""
```

- `max_tools`/`max_length` 값은 호출부(application)에서 `AgentBuilderPolicy.MAX_TOOLS`(5), `MAX_SYSTEM_PROMPT_LENGTH`(4000)를 넘겨 단일 출처 유지(하드코딩 금지).

### 2-3. `src/application/agent_composer/schemas.py`

```python
class ComposeAgentRequest(BaseModel):
    user_request: str = Field(..., min_length=1, max_length=1000)
    name: str | None = Field(None, max_length=200)      # 없으면 LLM 제안 사용
    llm_model_id: str | None = None


class MissingCapabilityDto(BaseModel):
    capability: str
    reason: str
    suggestion: str = ""


class ComposeAgentDraftResponse(BaseModel):
    coverage: str                                        # full | partial | none
    name_suggestion: str = ""
    system_prompt: str = ""
    tool_ids: list[str] = []                             # CreateAgentRequest.tool_ids 호환 (mcp_* 포함)
    workers: list[WorkerInfo] = []                       # agent_builder.schemas.WorkerInfo 재사용
    flow_hint: str = ""
    llm_model_id: str = ""
    temperature: float = 0.70
    missing_capabilities: list[MissingCapabilityDto] = []
    notes: str = ""
```

- `coverage="none"`이면 `tool_ids/workers/system_prompt/flow_hint`는 빈 값, `missing_capabilities`+`notes`만 채운다.
- `WorkerInfo`는 `src/application/agent_builder/schemas.py`의 응답 DTO를 import 재사용(응답 계약 일치 목적의 스키마 참조 — 로직 재사용 아님).

### 2-4. `src/application/agent_composer/composer.py` — `AgentComposer`

LLM structured output 스키마(내부 전용):

```python
class _CapabilityOutput(BaseModel):
    capability: str = Field(description="요청에서 분해한 단위 역량")
    matched_tool_ids: list[str] = Field(description="이 역량을 커버하는 후보 tool_id. 없으면 빈 배열")
    reason: str = Field(description="매칭 근거 또는 커버 불가 사유")
    suggestion: str = Field("", description="커버 불가 시 대안(예: 특정 MCP 등록)")

class _WorkerOutput(BaseModel):
    tool_id: str          # 후보 목록의 tool_id 그대로 (검증은 서버가 수행)
    worker_id: str        # snake_case
    description: str      # 이 워커의 역할
    sort_order: int

class _ComposeOutput(BaseModel):
    capabilities: list[_CapabilityOutput]
    workers: list[_WorkerOutput]
    flow_hint: str
    system_prompt: str    # 한국어, 2000자 이내 (PromptGenerator와 동일 형식 요구)
    agent_name: str       # 이름 제안
```

시스템 프롬프트 골자:

```
당신은 AI 에이전트 설계 전문가입니다. 사용자의 요청을 단위 역량으로 분해하고,
아래 후보 도구만으로 에이전트를 설계하세요.

[후보 도구]  ← "- {tool_id} ({source}): {name} — {description}" 라인 나열, 상한 초과 시 절단+로그
{candidates_block}

[규칙]
- 후보 목록에 있는 tool_id만 workers에 사용하세요. 목록에 없는 도구를 지어내지 마세요.
- 각 역량(capability)마다 matched_tool_ids를 반드시 인용하세요. 커버할 후보가 없으면
  matched_tool_ids를 빈 배열로 두고 reason에 사유, suggestion에 대안을 쓰세요.
- workers에는 matched_tool_ids에 인용된 도구만 포함하세요.
- system_prompt는 한국어로: 1) 목적 1~2문장 2) [역할] 워커별 역할 3) [동작 원칙].
- 요청이 후보 도구와 전혀 무관하면 workers를 빈 배열로 두세요.
```

- 후보 라인 수 상한: `settings.composer_max_candidates`(신규 config, 기본 100). 초과분은 절단하고 warning 로그(무언 절단 금지 규칙 — "No silent caps").
- 생성자: `AgentComposer(llm, logger)` — `llm.with_structured_output(_ComposeOutput)`.
- 로깅: `AgentComposer start/done/failed` + `worker_count`, `capability_count`.

### 2-5. `src/application/agent_composer/compose_agent_use_case.py`

```python
class ComposeAgentUseCase:
    def __init__(self, composer, tool_catalog_repo, mcp_server_repo,
                 llm_model_repository, logger): ...

    async def execute(self, request, request_id) -> ComposeAgentDraftResponse:
        # 1) llm_model_id 해석 (find_by_id 실패 시 ValueError → 라우터 422)
        # 2) 후보 수집 (D6 + D2 폴백)
        # 3) composer.compose(...)
        # 4) 초안 조립 (아래 순서 고정)
        #    a. ComposePolicy.drop_unknown_tools      → drop 발생 시 warning 로그 + notes
        #    b. MCP 매핑: mcp:{srv}:{tool} → mcp_{srv}, 같은 서버 워커는 1개로 병합
        #       (병합 시 description은 "; " join, worker_id는 "mcp_{srv}_worker",
        #        sort_order는 병합 전 최솟값, 이후 전체 0..n 재부여)
        #    c. ComposePolicy.clamp_tool_count(AgentBuilderPolicy.MAX_TOOLS)
        #    d. ComposePolicy.clamp_system_prompt(MAX_SYSTEM_PROMPT_LENGTH)
        #    e. missing = matched_tool_ids가 빈 capabilities (+ drop/clamp로 탈락한 역량은 notes)
        #    f. coverage = ComposePolicy.derive_coverage(len(workers), missing)
        # 5) 응답 조립. coverage=="none"이면 초안 필드 비움. DB 쓰기 없음.
```

- 이름: `request.name`이 있으면 `name_suggestion`에 그대로 echo(사용자 지정 우선), 없으면 `output.agent_name`.
- `temperature`는 `CreateAgentRequest` 기본값과 동일한 `0.70` 고정 반환(초안 단계 조정 없음).

### 2-6. `src/api/routes/agent_composer_router.py`

```python
router = APIRouter(prefix="/api/v1/agents", tags=["Agent Composer"])

def get_compose_agent_use_case():
    raise NotImplementedError    # main.py에서 override

@router.post("/compose", response_model=ComposeAgentDraftResponse)
async def compose_agent(
    body: ComposeAgentRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_compose_agent_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
```

- status 200 (리소스 미생성이므로 201 아님).
- 그 외 예외는 use case에서 `logger.error(exception=e)` 후 전파 → 전역 500 핸들러(기존 관례).

### 2-7. `src/api/main.py` DI — `create_agent_composer_factories()`

`create_tool_catalog_factories()`(main.py:2581) 패턴을 따른다:

```python
def create_agent_composer_factories():
    app_logger = get_app_logger()
    llm = ChatOpenAI(model=settings.openai_llm_model,
                     api_key=settings.openai_api_key, temperature=0)   # D5
    composer = AgentComposer(llm=llm, logger=app_logger)

    def compose_factory(session: AsyncSession = Depends(get_session)):
        return ComposeAgentUseCase(
            composer=composer,
            tool_catalog_repo=ToolCatalogRepository(session=session, logger=app_logger),
            mcp_server_repo=MCPServerRepository(session=session, logger=app_logger,
                                                cipher=_mcp_cipher()),
            llm_model_repository=SessionScopedLlmModelRepository(session=session,
                                                                 logger=app_logger),
            logger=app_logger,
        )
    return compose_factory
```

- 한 요청 내 모든 repo가 동일 `session` 공유(DB-001 준수).
- `app.include_router(agent_composer_router)` + `dependency_overrides` 등록.

---

## 3. 기존 파일 변경 (최소 확장)

### 3-1. FR-09 — `src/application/agent_builder/schemas.py`

```python
class CreateAgentRequest(BaseModel):
    ...
    # nl-agent-composer D1: 초안 프리필 프롬프트. None이면 기존대로 LLM 자동 생성.
    system_prompt: str | None = Field(None, max_length=4000)
```

### 3-2. FR-09 — `src/application/agent_builder/create_agent_use_case.py` Step 3

```python
# Step 3: 시스템 프롬프트 — 프리필 우선(nl-agent-composer D1), 없으면 자동 생성
if request.system_prompt:
    system_prompt = request.system_prompt
else:
    tool_metas = [...]   # 기존 코드 (mcp_ 워커는 제외 — §3-3의 meta 해석과 함께 조정)
    system_prompt = await self._generator.generate(...)
AgentBuilderPolicy.validate_system_prompt(system_prompt)
```

### 3-3. FR-08 — `_build_skeleton_from_tool_ids`의 `mcp_` 분기

```python
# CreateAgentUseCase.__init__에 mcp_server_repo=None 선택 주입 추가
for i, raw_id in enumerate(tool_ids):
    tool_id = self._normalize_tool_id(raw_id)
    if tool_id.startswith("mcp_"):
        reg = await self._resolve_mcp_meta(tool_id, request_id)   # 신규 헬퍼
        workers.append(WorkerDefinition(tool_id=tool_id,
                                        worker_id=f"{tool_id}_worker",
                                        description=reg.description, sort_order=i))
        continue
    meta = get_tool_meta(tool_id)      # 기존 내부 도구 경로 무변경
    ...
```

- `_resolve_mcp_meta`: `mcp_server_repo.find_by_id(tool_id.removeprefix("mcp_"))`. 미주입/미등록/비활성 → `ValueError`(기존 unknown tool_id와 동일하게 422 매핑).
- 주의: 이 변경으로 `_build_skeleton_from_tool_ids`가 async 조회를 포함하게 됨 → 메서드를 `async def`로 전환(호출부 1곳 `await` 추가). Step 3의 `tool_metas = [get_tool_meta(w.tool_id) ...]`도 `mcp_` 워커에서 터지므로, **프리필 프롬프트가 있으면 Step 3 자체를 건너뛰는 3-2 순서가 선행 조건**. 프리필 없이 `mcp_` tool_ids만 오는 경우는 `tool_metas`에서 mcp 워커를 worker.description 기반 임시 `ToolMeta`로 대체한다(생성 실패 방지).
- 함수 40줄 제한: 분기 추가로 초과 시 내부 도구/MCP 해석을 헬퍼로 분리.

### 3-4. `src/config.py`

```python
composer_max_candidates: int = 100   # compose LLM 후보 도구 상한 (초과 절단 + 경고 로그)
```

`.env.example`에 `COMPOSER_MAX_CANDIDATES=100` 추가.

---

## 4. 테스트 설계 (TDD — 구현 전 작성)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/agent_composer/test_compose_policies.py` | drop_unknown_tools(환각 제거·전부 유효·전부 환각), clamp_tool_count(5 초과 절단·이하 통과), clamp_system_prompt(4000 초과 절단), derive_coverage(0워커→none / missing→partial / 그 외 full) |
| `tests/application/agent_composer/test_agent_composer.py` | structured output 파싱(mock LLM), 후보 상한 절단 + 경고 로그, LLM 예외 시 error 로그 + 전파 |
| `tests/application/agent_composer/test_compose_agent_use_case.py` | ① 내부+MCP 혼합 초안 조립 ② `mcp:{srv}:{tool}` 2건 같은 서버 → `mcp_{srv}` 워커 1개 병합 ③ 카탈로그 MCP 0건 → 서버 단위 폴백(D2) + notes ④ 환각 tool_id drop + notes ⑤ coverage=none 시 초안 필드 빈 값 ⑥ llm_model_id 미존재 → ValueError ⑦ repo save 호출 0회(무저장 검증) |
| `tests/api/test_agent_composer_router.py` | 200 정상 초안, 인증 없음 401, user_request 초과 422, ValueError → 422 |
| `tests/application/agent_builder/test_create_agent_use_case_mcp.py` | FR-08: `tool_ids=["mcp_x"]` 생성 성공(레포 mock), 미등록 `mcp_y` → ValueError, 내부 도구 경로 기존 동작 유지 |
| `tests/application/agent_builder/test_create_agent_prompt_prefill.py` | FR-09: system_prompt 제공 시 generator 미호출·그대로 저장, 4001자 → ValueError, None → 기존 자동 생성 |

회귀: 기존 `tests/` agent_builder·interview·run 전체 통과(내부 도구 경로 바이트 무변경 원칙). 참고: memory상 사전 실패(auth DI) 28건은 신규 회귀로 오인하지 않는다.

---

## 5. 구현 순서 (Do 단계 체크리스트)

1. domain: `agent_composer/schemas.py` + `policies.py` (+ 테스트 → Red→Green)
2. application: `composer.py` (+ mock LLM 테스트)
3. application: `compose_agent_use_case.py` (+ 테스트, D2 폴백/매핑/무저장 포함)
4. interfaces: `agent_composer_router.py` (+ 라우터 테스트)
5. 기존 확장: FR-09(schemas + use case Step 3) → FR-08(`mcp_` 분기, async 전환) (+ 테스트)
6. `main.py` DI + `config.py` + `.env.example`
7. `/verify-architecture`, `/verify-logging`, `/verify-tdd` + 전체 pytest(격리 실행 유의)

---

## 6. 검증 기준 (Check 매핑)

Plan §6 성공 기준 1~6을 그대로 사용. 추가로:

- D7 clamp 동작이 에러가 아닌 notes로 표면화되는지.
- compose 응답 `tool_ids`를 그대로 `POST /agents`(system_prompt 포함)에 넣어 201 → run 성공하는 E2E 시나리오 1건(수동 or 통합 테스트).
