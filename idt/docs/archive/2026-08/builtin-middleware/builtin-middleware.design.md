# Builtin Middleware Design Document

> **Summary**: 미들웨어 제어의 런타임 SoT는 `middleware_catalog`(V056 — 4종 시드, 관리자가
> `is_builtin`/`is_enforced`/`default_config` 편집)이며, 에이전트별 적용 여부는
> `agent_middleware` 스냅샷(행 존재=적용, config는 1차 NULL — 설정값은 카탈로그 단일 소스)로
> 기록한다(D2/D5). 실행 시 `WorkflowCompiler`와 General Chat이 **스냅샷 ∪ enforced**를
> `MiddlewareBuilder`(langchain v1 격리 지점)로 인스턴스화해 `create_agent(middleware=...)`로
> 조립하고(D6/D7), 개별 조립 실패는 해당 미들웨어만 제외+경고로 격하한다(D8).
> create_react_agent → create_agent 전환은 "미들웨어 0개 동등성 게이트"를 선행한다(D0).
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-04
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/builtin-middleware.plan.md`

---

## 1. Design Overview

```
[관리자]                              [에이전트 생성자/사용자]
AdminMiddlewarePage (신규)              AgentBuilderPage (폼/Fix 채팅)
  │ PATCH /middleware-catalog/{type}      │ POST /agents
  ▼   (builtin/enforced/config)           │   exclude_builtin_middleware_types (폼 수동 해제만)
middleware_catalog  ◄─ V056 시드 4종      ▼
  is_builtin / is_enforced /           CreateAgentUseCase
  default_config(단일 소스)               └ Step 2.8  빌트인 스냅샷 → agent_middleware 저장
  │                                              (행 존재=적용, config=NULL)
  │ 실행 시 조회 (compile당 1회)
  ▼
WorkflowCompiler.compile / GeneralChat._create_agent
  applied = snapshot(agent_middleware) ∪ enforced(catalog)   ← type 기준 dedupe
  instances = MiddlewareBuilder.build(applied, catalog.default_config)
  worker = create_agent(model=llm, tools=[...], name=worker_id,
                        system_prompt=..., middleware=instances)
```

- **A→B 전환 용이성**: langchain v1 클래스(`ModelRetryMiddleware` 등) 참조는
  `MiddlewareBuilder` 한 모듈에만 존재. 도메인·카탈로그·API·프론트는
  `middleware_type` 문자열 + config dict만 다룬다. B안(커스텀 훅) 전환 시 빌더 구현만 교체.
- supervisor·search 파이프라인·analysis 노드는 **무변경** — react 워커와 General Chat만 전환.

---

## 2. D0 — create_agent 전환 무회귀 게이트 (선행)

### 2.1 의존성 (S1)

- `pyproject.toml`: `"langchain>=1.0"` 추가. 설치 후 스모크:
  `from langchain.agents import create_agent` + 미들웨어 4종 import 성공 확인.
- **시그니처 검증 항목** (langchain-middleware 스킬 문서는 alpha 기준 — 설치 버전으로 확정):
  - 시스템 프롬프트 파라미터: v1 stable은 `system_prompt=`(문자열) — alpha 문서의
    `prompt=`와 다를 수 있으므로 S1 스모크 테스트에서 `inspect.signature`로 단언.
  - `name=` 파라미터 존재 (워커 name 규약에 필수). 부재 시 컴파일된 그래프에
    `.name` 부여 또는 `create_react_agent` 병행 유지로 폴백 — **이 경우 설계 재검토 후 진행**.
- langchain-classic 1.0.3 공존 확인: 전체 테스트 격리 실행(Windows 관례)로 회귀 검증.
  충돌 시 B안 폴백(빌더 추상화 유지, plan 리스크 대응).

### 2.2 동등성 게이트 (FR-07)

전환 커밋 **이전에** 특성(characterization) 테스트로 현행 계약을 고정한다:

| 계약 | 테스트 |
|------|--------|
| 워커 산출물 = AIMessage(name=worker_id) 1건 (worker-toolmessage-leak-fix 규약) | FakeModel 워커 실행 후 supervisor state 메시지 검사 |
| supervisor 라우팅/품질 게이트 동작 불변 | 기존 workflow_compiler 테스트 전체 통과 |
| General Chat astream_events v2 토큰 스트리밍 (on_chat_model_stream 이벤트) | FakeStreamingModel로 TOKEN 이벤트 수신 단언 |
| 고아 tool 메시지 400 방어 (`_is_tool_message` 필터) | 기존 테스트 통과 |

미들웨어 0개일 때 `create_agent` 결과가 위 계약을 전부 만족해야 전환 확정.
**단일 경로 원칙**: 미들웨어 유무와 무관하게 항상 `create_agent` 사용
(빈 리스트 전달) — create_react_agent 병행 유지로 인한 이중 경로 표류 방지.

---

## 3. D1 — 도메인 모듈 신설 + v2 실험 경로 격리

신규 `src/domain/middleware/` 모듈을 만든다. 기존 `middleware_agent`(v2, `/api/v2/agents`)는
**수정하지 않는다** — enum 구성이 다르고(`model_retry` 부재, summarization/pii 포함)
소유 모델도 다르다(에이전트가 config 전체 소유 vs 카탈로그 단일 소스).
v2 모듈 docstring에 "실험 경로 — builtin-middleware가 본 채택, 후속 정리 대상" 주석만 추가.

```python
# src/domain/middleware/entities.py
class MiddlewareType(str, Enum):
    MODEL_RETRY = "model_retry"
    TOOL_RETRY = "tool_retry"
    MODEL_FALLBACK = "model_fallback"
    MODEL_CALL_LIMIT = "model_call_limit"

@dataclass
class MiddlewareCatalogEntry:
    id: str
    middleware_type: MiddlewareType
    name: str
    description: str
    is_builtin: bool
    is_enforced: bool
    default_config: dict
    is_active: bool
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

@dataclass(frozen=True)
class AppliedMiddleware:
    """실행 조립용 VO — 스냅샷∪enforced 병합 결과."""
    middleware_type: MiddlewareType
    config: dict          # 1차: 카탈로그 default_config 해석 결과
    sort_order: int

# src/domain/middleware/interfaces.py
class MiddlewareCatalogRepositoryInterface(ABC):
    async def list_all(request_id) -> list[MiddlewareCatalogEntry]
    async def find_by_type(middleware_type, request_id) -> MiddlewareCatalogEntry | None
    async def update_flags(middleware_type, *, is_builtin=None, is_enforced=None,
                           default_config=None, request_id) -> MiddlewareCatalogEntry | None
    async def list_builtin(request_id) -> list[MiddlewareCatalogEntry]   # builtin AND active
    # enforced 목록은 별도 메서드 없이 list_all 결과를 MiddlewareMergePolicy가 필터
    # (조회 1회로 충분 — 구현 반영, Check G7)

class AgentMiddlewareRepositoryInterface(ABC):
    async def list_by_agent(agent_id, request_id) -> list[AgentMiddlewareRecord]
    # 저장/교체는 agent 저장 트랜잭션에 동승 (D5 — 세션 공유, commit 금지 규칙)
```

병합 정책은 domain policy로:

```python
# src/domain/middleware/policies.py
class MiddlewareMergePolicy:
    @staticmethod
    def merge(snapshot_types: list[MiddlewareType],
              enforced: list[MiddlewareCatalogEntry],
              catalog: list[MiddlewareCatalogEntry]) -> list[AppliedMiddleware]:
        """스냅샷 ∪ enforced, type 기준 dedupe(중복 1회), catalog.sort_order 정렬.
        config는 카탈로그 default_config 단일 소스. 카탈로그에 없거나 inactive인
        스냅샷 타입은 제외(카탈로그가 게이트)."""
```

---

## 4. D2 — V056 마이그레이션

```sql
-- builtin-middleware D2: 미들웨어 카탈로그 — 빌트인/강제 플래그와 기본 설정의 런타임 SoT.
-- 시드는 본 마이그레이션의 INSERT가 유일한 공급원 (부팅 sync 없음 — D3).
CREATE TABLE middleware_catalog (
    id              VARCHAR(36)  NOT NULL COMMENT 'PK (UUID)',
    middleware_type VARCHAR(50)  NOT NULL COMMENT '미들웨어 유형 식별자 (model_retry/tool_retry/model_fallback/model_call_limit)',
    name            VARCHAR(100) NOT NULL COMMENT '표시 이름 (폼·관리자 화면)',
    description     VARCHAR(500) NOT NULL COMMENT '설명 — 폼 안내 문구 (예: LLM 호출 실패 시 지수 백오프로 자동 재시도)',
    is_builtin      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '빌트인 여부 — 에이전트 생성 시 기본 적용(사용자 해제 가능), 관리자 토글',
    is_enforced     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '강제 여부 — 실행 시 에이전트 스냅샷과 무관하게 병합 적용(사용자 해제 불가), 관리자 토글',
    default_config  JSON         NOT NULL COMMENT '기본 설정값 (관리자 편집) — 런타임 설정 단일 소스, 1차는 에이전트별 오버라이드 없음',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '활성 여부 — 비활성 시 빌트인/강제 판정에서 제외',
    sort_order      INT          NOT NULL DEFAULT 0 COMMENT '적용 순서 (미들웨어 체인 순서)',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_middleware_catalog_type (middleware_type)
) ENGINE=InnoDB COMMENT='미들웨어 카탈로그 — 빌트인/강제/기본 설정의 런타임 SoT (관리자 관리)';

-- builtin-middleware D5: 에이전트별 적용 미들웨어 스냅샷 (행 존재 = 적용).
CREATE TABLE agent_middleware (
    id              VARCHAR(36) NOT NULL COMMENT 'PK (UUID)',
    agent_id        VARCHAR(36) NOT NULL COMMENT '에이전트 FK (agent_definition.id)',
    middleware_type VARCHAR(50) NOT NULL COMMENT '적용 미들웨어 유형 (middleware_catalog.middleware_type 참조값)',
    config          JSON        NULL COMMENT '에이전트별 설정 오버라이드 — 1차 미사용(NULL), 후속 확장 예약',
    sort_order      INT         NOT NULL DEFAULT 0 COMMENT '적용 순서 (스냅샷 시점 카탈로그 순서)',
    created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_middleware (agent_id, middleware_type),
    CONSTRAINT fk_agent_middleware_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='에이전트별 적용 미들웨어 스냅샷 — 생성 시 빌트인 주입, 폼 수정 시 전체 교체';

-- 시드: 4종 (초기 빌트인 = model_retry + tool_retry, enforced 전부 off)
INSERT INTO middleware_catalog
    (id, middleware_type, name, description, is_builtin, is_enforced, default_config, sort_order)
VALUES
    (UUID(), 'model_retry',      'LLM 재시도',     'LLM 호출 실패 시 지수 백오프로 자동 재시도합니다. 네트워크 불안정 환경에 적합합니다.', 1, 0, '{"max_retries": 3, "backoff_factor": 2.0, "initial_delay": 1.0}', 10),
    (UUID(), 'tool_retry',       '도구 재시도',    '도구(내부/MCP) 호출 실패 시 지수 백오프로 자동 재시도합니다.',                     1, 0, '{"max_retries": 2, "backoff_factor": 2.0, "initial_delay": 1.0}', 20),
    (UUID(), 'model_fallback',   '모델 폴백',      '주 모델 실패 시 대체 모델로 자동 전환합니다. 대체 모델을 설정해야 동작합니다.',      0, 0, '{"fallback_models": []}', 30),
    (UUID(), 'model_call_limit', '모델 호출 상한', 'run당 LLM 호출 횟수를 제한해 무한 루프와 비용 폭주를 방지합니다.',                  0, 0, '{"run_limit": 10, "exit_behavior": "end"}', 40);
```

- **FK 규칙**: `agent_definition` 참조 — CHARSET/COLLATE 명시 금지, ENGINE=InnoDB만
  (MySQL errno 3780 선례, V037 주석). `agent_id` 컬럼 타입은 기존 `agent_tool.agent_id`
  정의와 동일하게 맞춘다(구현 시 실물 확인).
- `tests/db/test_migration_ddl_comments.py`가 V054+를 검사 — 전 컬럼·테이블 COMMENT 필수.
- SQLAlchemy 모델(`src/infrastructure/middleware/models.py`)에도 동일 `comment=` 반영.

---

## 5. D3 — 시드 단순화 (builtin-tools와의 차이)

tool_catalog와 달리 **부팅 sync가 없다** — 카탈로그 행의 유일한 공급원은 마이그레이션
INSERT다. 따라서:

| 시나리오 | 결과 |
|----------|------|
| 기존 DB | V056이 테이블+시드 동시 생성 ✓ |
| 프레시 DB | 동일 (Flyway가 앱 기동 전 실행) ✓ |
| 관리자 토글 후 재부팅 | 덮어쓸 주체가 없어 자연 보존 ✓ (보존 테스트 불요) |
| 신규 미들웨어 추가 (후속) | 새 마이그레이션 INSERT + MiddlewareBuilder 분기 추가 |

builtin-tools의 D1(시드 이원화)/D2(sync 보존) 복잡도가 통째로 불필요 — 이것이
`middleware_catalog`를 `tool_catalog` 컬럼 확장이 아닌 독립 테이블로 두는 이유이기도 하다.

---

## 6. D4 — 관리자 API

```
GET   /api/v1/middleware-catalog                      (로그인 필수 — 폼·관리자 공용)
200:  { "middlewares": [ { "middleware_type": "model_retry", "name": "...",
        "description": "...", "is_builtin": true, "is_enforced": false,
        "default_config": {...}, "is_active": true, "sort_order": 10 }, ... ] }

PATCH /api/v1/middleware-catalog/{middleware_type}    (require_role("admin"))
Body: { "is_builtin"?: bool, "is_enforced"?: bool, "default_config"?: object }  # 부분 갱신
200:  갱신된 항목 (GET 항목과 동일 스키마)
404:  미존재 middleware_type
400:  config 검증 실패 (아래 규칙)
403:  비관리자 (require_role 기존 동작)
```

- `middleware_type`은 enum 값(콜론 없음)이라 **path 파라미터 적합** — tool_catalog가
  body로 받은 이유(`mcp:{uuid}:{tool}` 콜론 문제)가 여기엔 없다.
- **config 검증** (application 스키마, 타입별 pydantic 모델):
  - `model_retry`/`tool_retry`: `max_retries` int 0~10, `backoff_factor` float ≥1.0,
    `initial_delay` float ≥0
  - `model_call_limit`: `run_limit` int 1~50, `exit_behavior` ∈ {"end", "error"}
  - `model_fallback`: `fallback_models`는 **llm_model 테이블 등록·활성 모델명**만 허용
    — `LlmModelRepositoryInterface`로 존재 검증, 미등록 모델 포함 시 400 (plan 리스크 대응)
- 구성: `ListMiddlewareCatalogUseCase` + `SetMiddlewareFlagsUseCase`
  (`src/application/middleware/`), 라우터 `src/api/routes/middleware_catalog_router.py`
  (DI 플레이스홀더 + main.py override — tool_catalog_router 선례 그대로).

---

## 7. D5 — 생성 시 빌트인 스냅샷 + 수정 경로

### 7.1 생성 (CreateAgentUseCase — Step 2.8, builtin-tools Step 2.7 바로 뒤)

```python
# 신규 optional 의존성: middleware_catalog_repo (미주입 시 스냅샷 생략 — 무회귀)
builtins = await self._middleware_catalog_repo.list_builtin(request_id)
exclude = set(request.exclude_builtin_middleware_types or [])
snapshot = [b.middleware_type for b in builtins if b.middleware_type.value not in exclude]
# → AgentDefinition.middleware_types 에 실려 repository.save가 agent_middleware 영속
```

- `CreateAgentRequest.exclude_builtin_middleware_types: list[str] | None = None`
  — **폼 전용 필드**. Fix 에이전트(채팅 초안)·auto_agent_builder 경로는 이 필드를
  만들지 않으므로 LLM이 빌트인 미들웨어를 뺄 수 없다(builtin-tools D5 구조 대칭).
- 미지 타입/비활성 타입은 exclude에 있어도 무해(빌트인 목록과의 교집합만 의미).
- 저장은 agent 저장과 **동일 세션·동일 트랜잭션** — repository `save()`에
  `_sync_middleware` 추가 (Repository 내 commit 금지 규칙 준수).

### 7.2 수정 (UpdateAgentUseCase — "4곳 세트" 규칙 준수)

`agent-repo-update-column-whitelist` 교훈: 스키마 + apply_update + repo update + DI 네 곳.

| 위치 | 변경 |
|------|------|
| `UpdateAgentRequest` | `middleware_types: list[str] | None = None` — None=미변경, 값 제공 시 **전체 교체** (chunking-profile PUT 전체교체 프리필 패턴) |
| `AgentDefinition.apply_update` | `middleware_types` 반영 |
| `repository.update` | `_sync_middleware` (기존 `_sync_workers` 대칭 — 삭제 후 재삽입) |
| DI/main.py | 카탈로그 repo 주입 (검증용) |

- 검증: 제공된 타입이 카탈로그에 존재(비활성 포함 허용 — 실행 시 active 필터가 방어)
  하지 않으면 400. dedupe 후 저장.
- enforced는 스냅샷과 무관하게 실행 시 병합되므로 수정 화면에서 빼도 적용됨(의도).

### 7.3 조회

`GET /agents/{id}` 응답(및 목록 detail)에 `middleware_types: list[str]` 노출 —
수정 폼 프리필용 (api-contract-sync 대상).

---

## 8. D6 — 실행 시 조립 (WorkflowCompiler)

### 8.1 DI (optional — 기존 패턴)

```python
WorkflowCompiler.__init__(..., middleware_provider=None)
# middleware_provider: MiddlewareProvider | None — 미주입 시 미들웨어 0개 = 현행 동작
```

`MiddlewareProvider`(application 신규)가 조회·병합·빌드를 캡슐화:

```python
class MiddlewareProvider:
    """compile당 1회 prepare(조회·병합·config 해석) → 워커별 instantiate."""
    def __init__(self, catalog_repo, agent_middleware_repo, builder, llm_model_repo, llm_factory, logger): ...

    async def prepare(self, agent_id: str | None, request_id: str,
                      *, default_builtin: bool = True) -> MiddlewarePlan:
        catalog = await self._catalog_repo.list_all(request_id)
        snapshot = (await self._agent_mw_repo.list_by_agent(agent_id, request_id)
                    if agent_id else [])
        # agent_id=None: default_builtin=True(General Chat)면 빌트인 ∪ enforced,
        # False(컴파일러 agent_id 미상)면 enforced만 — 사용자 opt-out 무시 방지
        applied = MiddlewareMergePolicy.merge([s.middleware_type for s in snapshot], catalog)
        return MiddlewarePlan(applied, fallback_models, builder, request_id)

# MiddlewarePlan.instantiate() -> list — 호출마다 새 인스턴스 (실패 격하는 D8)
```

> 구현 반영(Check G10): 설계 초안의 `build_for_agent()` 단일 메서드를
> `prepare()`+`MiddlewarePlan.instantiate()`로 분리 — §8.2 "워커별 인스턴스 분리"를
> 타입 수준에서 강제하는 우수한 이탈.

### 8.2 워커 조립 변경 (react 워커만)

```python
# 현행: create_react_agent(llm, tools=[tool], name=worker_def.worker_id)
# 변경:
worker_agent = create_agent(
    model=llm, tools=[tool], name=worker_def.worker_id,
    middleware=_instantiate(middleware_plan),   # plan은 compile 초입 1회, 인스턴스는 워커별
)
# wiki 워커: system_prompt=wiki_toc_block + instruction 로 동일 전환
```

- plan은 `compile()` 초입(depth 0)에서 `await provider.prepare(agent_id, request_id,
  default_builtin=False)` 1회 준비. sub_agent 재귀 컴파일에는 **미전달**
  (agent_id 미전달 관례와 정렬 — 최상위 에이전트 기준 1회).
- search 파이프라인·analysis·supervisor·chart 노드 무변경.
- 인스턴스 공유 주의: langchain 미들웨어가 상태를 가지면 워커 간 공유가 오염될 수
  있으므로 **워커마다 `plan.instantiate()`를 재호출해 인스턴스 분리** — prepare는
  config 해석까지, 인스턴스화는 워커별 수행(빌더 호출 비용은 미미).

### 8.3 성능

- 추가 DB 조회: compile당 카탈로그 1회 + 스냅샷 1회 (행 수 ~수십) — 수용.
  병목 확인 시 wiki-tree-performance 선례(get_wiki_vector_stack DI 싱글턴 캐시) 적용.

---

## 9. D7 — General Chat 적용

```python
# use_case.py _create_agent — 시그니처에 middlewares 추가 (조립은 stream()에서 1회)
def _create_agent(self, tools, auth_ctx=None, memory_block="", middlewares=None):
    llm = self._llm_factory.create(self._llm_model, temperature=0)
    prompt = render_user_context_block(auth_ctx) + memory_block + _SYSTEM_PROMPT
    return create_agent(model=llm, tools=tools, system_prompt=prompt,
                        middleware=middlewares or [])
```

- `GeneralChatUseCase.__init__`에 `middleware_provider=None` optional 추가 —
  미주입 시 빈 리스트(무회귀). 주입 시 `prepare(None, request_id)` (default_builtin=True) —
  **빌트인 ∪ enforced 전부 적용** (에이전트 정의가 없으므로 사용자 opt-out 없음, plan 결정).
- 스트리밍: `astream_events(version="v2")` 유지 — create_agent도 compiled langgraph라
  `on_chat_model_stream` 이벤트 동일 발화. D0 게이트의 스트리밍 특성 테스트가 보증.
- prompt는 이미 문자열이라 `system_prompt=` 매핑 직결 (조사 확인 완료).

---

## 10. D8 — 조립 격하 규칙 (MiddlewareBuilder)

`src/application/middleware/middleware_builder.py` — langchain v1 격리 지점.

```python
class MiddlewareBuilder:
    def build(self, applied: list[AppliedMiddleware], request_id: str) -> list:
        instances = []
        for a in applied:
            try:
                instances.append(self._build_one(a))
                # logger.info("Middleware applied", middleware_type=..., request_id=...)
            except Exception as e:      # FR-12 관측 + 실행 계속
                self._logger.warning("Middleware build skipped",
                                     middleware_type=a.middleware_type.value,
                                     request_id=request_id, exception=e)
        return instances
```

| 유형 | 인스턴스화 | 격하 조건 |
|------|-----------|----------|
| model_retry | `ModelRetryMiddleware(max_retries, backoff_factor, initial_delay)` | import 실패/설정 오류 |
| tool_retry | `ToolRetryMiddleware(max_retries, backoff_factor, initial_delay)` | 〃 |
| model_call_limit | `ModelCallLimitMiddleware(run_limit, exit_behavior)` (thread_limit 미사용 — checkpointer 없음) | 〃 |
| model_fallback | `fallback_models`를 `llm_model` repo에서 조회 → `llm_factory.create()`로 **BaseChatModel 해석 후** `ModelFallbackMiddleware(*models)` — 문자열 전달 금지(커스텀 base_url/ollama 모델은 init_chat_model이 못 푼다) | 빈 목록/모델 미해석 → 제외+경고 |

- `on_failure`/`jitter` 등 나머지 파라미터는 라이브러리 기본값 사용 — `model_retry`
  재시도 소진 시 기본 동작이 예외 전파라면 현행(미들웨어 없음=즉시 실패)보다 나쁘지
  않음. "실패를 성공으로 위장"(`continue`류)은 채택하지 않는다.
- 격하 로그는 request_id 포함 warning — 재시도/폴백 발생 자체는 langchain 내부
  로그 + LangSmith 트레이스로 관측(FR-12), 필요 시 후속에서 커스텀 콜백 확장.

---

## 11. D9 — model_call_limit × supervisor 상호작용

- `exit_behavior="end"`(기본 시드): 워커 react 루프가 한계 도달 시 **정상 종료** —
  마지막 AIMessage가 워커 산출물로 supervisor에 전달된다. supervisor 재위임은 기존
  `IterationLimitPolicy`(agent_definition.max_iterations, V045)가 상한 —
  무한 재위임 루프 없음.
- `"error"`는 run 전체 실패(현행 미들웨어 없는 실패와 동일 UX)라 기본 채택하지 않되,
  관리자가 config로 선택 가능(검증 허용값에 포함).
- 시나리오 테스트: run_limit=1 + 도구 호출을 유도하는 FakeModel → 워커가 조기
  종료해도 name 규약 1건 산출 + supervisor가 종료로 수렴하는지 단언.

---

## 12. D10 — 프론트엔드

### 12.1 타입/서비스/훅 (api-contract-sync)

- `src/types/middleware.ts`: `MiddlewareCatalogItem`, `SetMiddlewareFlagsRequest`
- `src/constants/api.ts`: `MIDDLEWARE_CATALOG` 엔드포인트 상수
- `src/services/middlewareService.ts`: `getMiddlewareCatalog()`, `setMiddlewareFlags()`
- `src/hooks/useMiddlewareCatalog.ts`: query + mutation —
  **queryKeys 신규 네임스페이스 `queryKeys.middlewareCatalog`** (eval-hub queryKeys 충돌 교훈)
- 에이전트 타입: `AgentDetail.middleware_types: string[]`,
  생성 요청에 `exclude_builtin_middleware_types?: string[]`,
  수정 요청에 `middleware_types?: string[]`

### 12.2 생성/수정 폼 — 미들웨어 섹션

- 카탈로그 조회 → `is_active` 항목을 카드/체크 목록으로 표시 (name + description).
- **빌트인**: 기본 체크 + "기본" 배지. 해제 시 `exclude_builtin_middleware_types`에 수집
  (builtin-tools의 `excludedBuiltinTools` 전용 폼 상태 패턴 — Fix 채팅 경로엔 이 상태가
  없어 구조적 우회 불가).
- **enforced**: 체크 고정 + 잠금 아이콘 + 툴팁("관리자가 항상 적용으로 설정한 항목입니다").
- 비빌트인·비강제 항목: 기본 해제, 체크 시 생성 요청에 포함?
  → **1차 아님** — 생성 시 스냅샷은 빌트인에서만 출발(plan 스코프). 비빌트인 선택은
  수정 폼의 `middleware_types` 전체 교체로만 가능하게 해 스키마를 단순화한다.
  (생성 폼에는 빌트인+enforced만 노출)
- 수정 폼: `middleware_types` 프리필(agent detail) → 체크 토글 → 전체 교체 저장.
  카탈로그 전 항목 노출(비빌트인 포함), enforced는 동일 잠금 표시.
- 설정값: 각 항목에 `default_config` 요약을 **읽기 전용**으로 표시 (1차 열람만).

### 12.3 관리자 화면

- 관리자 네비 4그룹(admin-nav-restructure) 중 도구/카탈로그 그룹에
  "미들웨어 관리" 2차 탭 추가 — `/admin/middleware`.
- 목록 테이블: name/description + `is_builtin`·`is_enforced` 토글 스위치 2개
  + 설정 편집(타입별 필드 폼 — JSON 원문 편집 대신 숫자/선택 입력, model_fallback은
  등록 모델 멀티 셀렉트). 적용순서는 행 정렬(sort_order 순)로 표현 — 별도 컬럼 없음
  (구현 반영, Check G4).
- ADMIN 역할에만 라우트·메뉴 노출 (기존 관리자 가드 재사용).
- 설정 저장 mutation은 `LoadingButton`(mutation-pending-guard 선례), 토글 2종은
  행·스위치 단위 pending 가드(연타 방지 — 구현 반영, Check G6).

### 12.4 테스트 (Windows 관례: vitest --pool=threads, MSW per-file listen)

- 폼: 빌트인 기본 체크+배지, 해제 시 exclude 페이로드, enforced 잠금(클릭 무효)
- 수정 폼: 프리필·전체 교체 페이로드
- 관리자: 토글 mutation 페이로드, 비관리자 메뉴 미노출

---

## 13. 구현 순서 (TDD)

```
0. D0-a  특성 테스트로 현행 계약 고정 (워커 name 규약·스트리밍·supervisor 라우팅)
1. S1    langchain>=1.0 설치 + import/시그니처 스모크 + 전체 테스트 격리 실행   [커밋 1]
2. D0-b  create_agent 전환 (workflow_compiler + general_chat) — 미들웨어 빈 리스트,
         특성 테스트 전부 통과 = 동등성 게이트                                  [커밋 2]
3. D1/D2 domain/middleware + V056 + infrastructure(models/repository)          [커밋 3]
4. D4    카탈로그 목록/토글 UseCase + 라우터(ADMIN) + config 검증               [커밋 4]
5. D5    생성 스냅샷 + exclude + 수정 4곳 세트 + agent detail 노출              [커밋 5]
6. D6~D9 MiddlewareBuilder + MergePolicy + Provider + 컴파일러/General Chat 배선
         + call_limit 시나리오                                                  [커밋 6]
7. D10   프론트 — 타입/서비스/훅 → 폼 섹션 → 관리자 화면                        [커밋 7]
8. 회귀  pytest 격리 실행 + vitest --pool=threads, verify-architecture/tdd     [마무리]
```

### 테스트 목록 (백엔드 핵심)

| 대상 | 케이스 |
|------|--------|
| D0 특성 | 워커 산출물 AIMessage(name) 1건 / TOKEN 스트리밍 / 고아 tool 필터 |
| MergePolicy | 스냅샷∪enforced dedupe / inactive 제외 / 카탈로그 순서 정렬 |
| MiddlewareBuilder | 4종 인스턴스화 / 개별 실패 격하(경고+계속) / fallback 모델 해석 실패 격하 |
| SetMiddlewareFlags | 토글 갱신 / 404 / config 검증 400 (범위·미등록 폴백 모델) |
| 라우터 | 비관리자 403 / 부분 갱신 |
| CreateAgent | 빌트인 스냅샷 저장 / exclude 제외 / repo 미주입 시 생략(무회귀) |
| UpdateAgent | middleware_types 전체 교체 / None 미변경 / 미지 타입 400 |
| Compile | provider 미주입=미들웨어 0 / 주입 시 워커에 middleware 전달 / 워커별 인스턴스 분리 |
| call_limit | run_limit 도달 시 워커 정상 종료 + supervisor 수렴 |
| General Chat | 카탈로그 적용 + 스트리밍 유지 |

---

## 14. 영향 범위 / 주의사항

- **배포 필수**: V056 적용 + `pip install -U langchain`(v1) — 미적용 시 카탈로그 조회
  실패·create_agent ImportError. `.venv` 인터프리터 기동 관례 유지.
- create_agent 전환은 **모든 에이전트 실행 경로**에 닿는다 — D0 게이트 통과 전
  다른 커밋과 섞지 않는다(전환 커밋 단독 revert 가능하게).
- enforced는 기존 에이전트에도 즉시 적용(런타임 병합) — 관리자 화면에 명시 문구.
- v2 `/api/v2/agents` 경로는 무변경(실험 표기만) — langchain 설치로 우연히 "살아나는"
  경로임을 인지 (후속 정리 과제).
- 대화 메모리 정책·Parent/Child 문서 구조·DB 스키마 기존 테이블 무변경 (금지 규칙 준수).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-04 | Initial draft — D0 동등성 게이트 선행, 카탈로그 단일 소스(config NULL 스냅샷), 시드(빌트인=model_retry+tool_retry), call_limit exit_behavior="end"×IterationLimitPolicy, fallback 모델 BaseChatModel 해석 규칙 확정 | 배상규 |
