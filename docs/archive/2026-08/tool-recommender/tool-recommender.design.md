# tool-recommender Design Document

> **Summary**: 도메인 Port + LLM 구현체 + 얇은 어댑터로 구성된, 실행 경로에 종속되지 않는 도구 선별 모듈.
>
> **Project**: sangplusbot (idt / 백엔드)
> **Version**: 0.4
> **Author**: tkdrb136
> **Date**: 2026-08-13
> **Status**: Draft
> **Planning Doc**: [tool-recommender.plan.md](../../01-plan/features/tool-recommender.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (DB 스키마 변경 없음) |
| Phase 2 | [Coding Conventions](../../../CLAUDE.md) | ✅ (idt/CLAUDE.md §2·§3·§6) |
| Phase 3 | Mockup | N/A (UI 없음) |
| Phase 4 | API Spec | N/A (엔드포인트 없음) |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 전량 바인딩 구조라 도구 수 증가가 곧 추천 품질 저하로 이어진다 (General Chat은 상한 자체가 없음) |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — MCP 서버를 계속 추가하려는 운영자. 부차적으로 General Chat 최종 사용자 |
| **RISK** | 선별이 정답 도구를 누락시켜 기존에 되던 질의가 실패하는 **기능 회귀** |
| **SUCCESS** | 골드셋 Recall ≥ 95% (필수 세트 포함 기준), 평균 바인딩 도구 수 감소, 모듈 제거 시 기존 경로 무변경 동작 |
| **SCOPE** | Phase 1 = 경로 독립 선별 모듈 + 골드셋 테스트 (배선 없음). Phase 2(별건) = 실제 경로 결선 |

---

## 1. Overview

### 1.1 Design Goals

1. **도구 선별 책임의 완전 격리** — 선별 로직이 General Chat·workflow_compiler·LangGraph 어느 것도 알지 못한다.
2. **디렉토리 삭제로 완결되는 탈부착** — `src/domain/tool_selection/`과 `src/infrastructure/tool_selection/`을 지우면 나머지가 그대로 컴파일·테스트를 통과한다.
3. **회귀 불가능성** — 셀렉터가 어떻게 실패하든 필수 세트는 항상 바인딩된다. 예외는 호출부로 전파되지 않는다.
4. **DB·API 계약 무변경** — 스키마 변경 없음(CLAUDE.md §4 준수), 프론트 동기화 불필요.

### 1.2 Design Principles

- **의존성 역전**: 호출부는 `ToolSelectorPort`(domain)만 알고 `LLMToolSelector`(infrastructure)를 모른다.
- **코어의 프레임워크 무지**: domain·infrastructure 코어는 `langchain`을 import하지 않는다. LangChain은 **어댑터에서만** 등장한다 — 기존 `MiddlewareBuilder`가 "langchain v1 클래스 참조는 본 모듈에만 존재한다"(`middleware_builder.py:3`)로 세운 선례를 그대로 따른다.
- **필수 세트는 주입받는다**: 모듈이 `TOOL_REGISTRY`나 `tool_catalog`를 직접 조회하지 않는다. 조회하는 순간 탈부착 계약이 깨진다.
- **폴백은 침묵하지 않는다**: 폴백은 항상 `SelectionResult.reason`과 WARNING 로그에 남는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Middleware 정식 등록 | **Option C: Port + 어댑터** |
|----------|:-:|:-:|:-:|
| **Approach** | infra 클래스 1개, 호출부 직접 필터 | `MiddlewareType.TOOL_SELECTION` 신설 + `wrap_model_call` | domain Port + infra 구현 + 얇은 어댑터 2종 |
| **New Files** | 3 | 5 + DDL 마이그레이션 | 10 (테스트 제외 9) |
| **Modified Files** | 2 | 4 + DB 스키마 | **0** (Phase 1) / 1줄 (Phase 2) |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | Medium | **High** |
| **탈부착성** | 중 (호출부가 구현체 인지) | **하** (DDL 롤백 필요) | **상** |
| **DB 변경** | 없음 | **필요 — CLAUDE.md §4 저촉** | 없음 |
| **Effort** | Low | High | Medium |
| **Risk** | Medium | **High** | **Low** |

**Selected**: **Option C** — **Rationale**: 원 요구가 "결합도는 낮고 응집도는 강하게, 추가·삭제가 용이하게"였다. A는 호출부가 구현체 타입을 직접 참조해 경로가 늘어날 때마다 배선이 반복되고, B는 제거하려면 마이그레이션을 되돌려야 해서 탈부착 요구와 정면 충돌한다. C만이 "디렉토리 삭제 = 기능 제거"를 성립시키며, 어댑터 2종 덕에 결선 스타일(함수형 필터 / 미들웨어)을 **나중에** 고를 수 있다.

### 2.1 Component Diagram

```
┌──────────────────────── 호출부 (Phase 2에서 결선) ────────────────────────┐
│  general_chat/use_case.py:367        workflow_compiler.py (선택)         │
│         │  tools, request.message           │                            │
└─────────┼───────────────────────────────────┼────────────────────────────┘
          │                                   │
          ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  infrastructure/tool_selection/adapters/    ← LangChain을 아는 유일한 층 │
│    LangChainToolFilter        list[BaseTool] ─→ list[BaseTool]          │
│    ToolSelectionMiddleware    wrap_model_call (선택적, 미배선)           │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ ToolCandidate[]  (프레임워크 무관 VO)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  infrastructure/tool_selection/                                          │
│    LLMToolSelector ──implements──▶ ToolSelectorPort                      │
│      ├─ LLMFactoryInterface (기존 domain 포트 재사용)                    │
│      ├─ prompts.py           선별 프롬프트                                │
│      └─ NullSelectionCache ──implements──▶ SelectionCachePort            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  domain/tool_selection/       ← 외부 의존 0. langchain·DB·HTTP 없음      │
│    ToolSelectorPort / SelectionCachePort  (ABC)                          │
│    ToolCandidate / SelectionResult / ToolSource  (VO)                    │
│    ToolSelectionPolicy   top-K · 합집합 · 이름 토큰화 · 화이트리스트      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
query + list[BaseTool]
   │
   ▼ [어댑터] BaseTool → ToolCandidate  (id 해석 + description 보강)
   │
   ▼ [Policy] needs_selection?  ── No(후보 ≤ top_k) ──▶ 전량 통과 (LLM 호출 없음)
   │ Yes
   ▼ [Cache] get(query, candidate_fingerprint)  ── hit ──▶ 캐시 결과 (v1: 항상 miss)
   │ miss
   ▼ [LLM] 경량 모델 1콜 → JSON {"tool_ids": [...]}
   │
   ├─ 예외 / 타임아웃 / 파싱 실패 ──▶ [폴백] required_ids만, fallback=True
   │
   ▼ [Policy] sanitize: 화이트리스트 대조 → 미지 ID 폐기(WARNING)
   │
   ▼ [Policy] merge: required_ids ∪ selected_ids, 후보 원순서로 안정 정렬
   │
   ▼ SelectionResult
   │
   ▼ [어댑터] final_ids → list[BaseTool] 재구성 (원 순서 보존)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `LangChainToolFilter` (adapter) | `ToolSelectorPort`, `BaseTool`, `ToolIdResolver` | BaseTool ↔ ToolCandidate 변환, 결선 진입점 |
| `ToolSelectionMiddleware` (adapter) | `ToolSelectorPort`, `AgentMiddleware` | `wrap_model_call`로 `request.override(tools=...)` |
| `LLMToolSelector` | `ToolSelectorPort`, `LLMFactoryInterface`, `LlmModel`, `SelectionCachePort`, `LoggerInterface` | LLM 1콜 선별 |
| `ToolSelectionPolicy` (domain) | **없음** | 순수 규칙 (top-K, 합집합, 토큰화, 정제) |
| `NullSelectionCache` | `SelectionCachePort` | v1 no-op |

> `LLMFactoryInterface`(`src/domain/llm/interfaces.py:13`)와 `LlmModel`(`src/domain/llm_model/entity.py:12`)은 **기존 도메인 자산을 재사용**한다. `_build_search_pipeline_llm_model()`(`src/api/main.py:2400-2420`)이 세운 "settings → DB 미등록 인라인 `LlmModel`" 패턴을 그대로 따른다.

---

## 3. Data Model

> **DB 스키마 변경 없음.** 아래는 모두 인메모리 VO다.

### 3.1 Entity Definition

```python
# src/domain/tool_selection/schemas.py
from dataclasses import dataclass
from enum import Enum


class ToolSource(str, Enum):
    INTERNAL = "internal"
    MCP = "mcp"


@dataclass(frozen=True)
class ToolCandidate:
    """선별 대상 도구 1건. 실행 프레임워크·DB를 알지 못한다."""

    tool_id: str                    # 카탈로그 표기 (§3.2)
    name: str                       # 모델에 보이는 도구명
    description: str                # 원본 설명 (빈 값·스텁 허용)
    source: ToolSource
    server_name: str | None = None  # MCP 전용, 설명 보강에 사용


@dataclass(frozen=True)
class SelectionResult:
    """선별 결과 + 관측 정보. 실패해도 이 타입으로 돌아온다 (예외 없음)."""

    selected_ids: tuple[str, ...]   # 모델이 고른 것 (정제 후)
    required_ids: tuple[str, ...]   # 호출부가 주입한 필수 세트
    final_ids: tuple[str, ...]      # required ∪ selected, 후보 원순서 정렬
    candidate_count: int
    elapsed_ms: int
    fallback: bool = False
    reason: str | None = None       # "under_threshold" | "llm_error" | ...
    dropped_ids: tuple[str, ...] = ()  # 환각으로 폐기된 ID
```

### 3.2 도구 ID 체계 (모듈 내부 규약)

모듈 내부는 **카탈로그 표기 하나만** 사용한다 (`docs/rules/tool-and-mcp.md:10-15`).

| Source | 모듈 내부 표기 | 예시 |
|--------|---------------|------|
| 내부 도구 | `internal:{tool_id}` | `internal:tavily_search` |
| MCP 도구 (카탈로그) | `mcp:{server_id}:{tool_name}` | `mcp:a1b2:search_blog` |
| MCP 도구 (**런타임 실제**) | `mcp:{server_name}:{tool_name}` | `mcp:naver_mcp:search_blog` |

> ⚠️ **저장·런타임 표기와 다르다.** `create_agent_use_case.py:453-463`의 `_normalize_tool_id`는 MCP를 `mcp_{server_id}`로 정규화하며 **도구명을 버린다**. 모듈은 이 변환을 **하지 않고**, 어댑터의 `ToolIdResolver`가 경계에서 책임진다 (§9.4). 저장 스키마는 건드리지 않는다.

> ✅ **해소됨 (v0.3 — Doc Convert MCP 실측으로 확인).**
> v0.2에서 "카탈로그 `server_id`를 얻으려면 저장소 조회가 필요"하다고 적었으나, 실제로는
> **불필요**하다. `mcp_tool_loader.py:42`가 `MCPServerConfig.name`에 `registration.tool_id`
> (= `mcp_{uuid}`)를 넣기 때문에 **server_id가 이미 들어 있다**. 접두어만 벗기면 된다.
>
> 실측값 (2026-08-13, Doc Convert MCP):
> ```
> registration.name    = "Doc Convert MCP"                          ← DB에만 존재
> server_config.name   = "mcp_6dd5c675-dae8-454d-9cc0-7e8c71f46977" ← 런타임에 오는 값
> adapter.name         = "mcp_6dd5c675_dae8_454d_9cc0_7e8c71f46977_docx_to_html"
> mcp_tool_name        = "docx_to_html"
> ```
> 따라서 `DefaultToolIdResolver`는 카탈로그와 동일한 `mcp:{server_id}:{tool}`을 만든다.
> **module-4의 선결 조건이 사라졌다.**
>
> 다만 **사람이 읽는 서버명(`registration.name`)은 런타임 도구 객체까지 오지 않는다.**
> 그래서 설명 보강(§3.3)에는 서버명을 쓸 수 없다 — 아래 참조.

### 3.3 Description 보강 규칙 (이름 토큰화)

MCP 어댑터는 설명이 없으면 `f"MCP tool: {mcp_tool.name}"`로 채운다(`src/infrastructure/mcp/tool_registry.py:88`). 셀렉터에겐 **정보량 0인 신호**이므로 도메인 정책이 보강한다.

> ⚠️ **이름 대조로는 스텁을 잡을 수 없다 (v0.2에서 교정).**
> `tool_registry.py:83-90`을 보면 두 값이 서로 다른 재료로 만들어진다:
> - 어댑터 `name` = `sanitize(f"{config.name}_{mcp_tool.name}")` → `naver_mcp_search_blog`
> - 스텁 `description` = `f"MCP tool: {mcp_tool.name}"` → `MCP tool: search_blog`
>
> 즉 `description == f"MCP tool: {name}"` 비교는 **실제 데이터에서 절대 참이 되지 않는다**.
> 초안(v0.1)의 의사코드가 이 방식이었고, 그대로 구현하면 스텁을 하나도 탐지하지 못한다.
> 따라서 **패턴 매칭**으로 판별한다.

```python
# src/domain/tool_selection/policies.py
_LOW_SIGNAL_PREFIX = "MCP tool: "
_LOW_SIGNAL_STUB = re.compile(r"^MCP tool:\s*\S+$")
_TOKEN_SPLIT = re.compile(r"[_\-.:/]+")


def is_low_signal(description: str, name: str) -> bool:
    """설명이 비었거나 ``MCP tool: {x}`` 스텁이면 True.

    실제 설명이 우연히 이 형태(접두어 + 공백 없는 토큰 1개)일 확률은 무시할 수 있다.
    접두어로 시작해도 뒤에 실제 문장이 이어지면 스텁이 아니다.
    """
    text = (description or "").strip()
    if not text:
        return True
    if text == f"{_LOW_SIGNAL_PREFIX}{name}":
        return True
    return bool(_LOW_SIGNAL_STUB.match(text))


def tokenize_name(name: str) -> str:
    """search_blog_posts → 'search blog posts'"""
    return " ".join(t for t in _TOKEN_SPLIT.split(name) if t)


def effective_description(c: ToolCandidate) -> str:
    """저신호 설명을 이름 토큰 + 서버명으로 보강한다."""
    if not is_low_signal(c.description, c.name):
        return c.description
    tokens = tokenize_name(c.name)
    if c.server_name:
        return f"{c.server_name} 서버의 '{tokens}' 기능"
    return f"'{tokens}' 기능"
```

추가 의존 없이 즉시 적용되며, 순수 함수라 유닛테스트로 고정된다.

> ⚠️ **서버명 보강은 실제로 발동하지 않는다 (v0.3 실측).**
> 초안의 예시 `"naver_mcp 서버의 'search blog' 기능"`은 **나올 수 없는 형태**였다.
> 런타임에 오는 서버명은 `mcp_6dd5c675-dae8-...`(UUID)이지 사람이 읽는 이름이 아니다.
> 그대로 쓰면 보강 문장이
> `"mcp_6dd5c675-dae8-454d-9cc0-7e8c71f46977 서버의 '...' 기능"`이 되어 **노이즈만 주입**한다.
>
> 따라서 어댑터(`_server_label`)가 UUID 형태를 감지해 `server_name=None`으로 넘긴다.
> 결과: `'docx to html' 기능` — 서버 언급 없이 깨끗하다. 사람이 읽는 서버명을 쓰고 싶다면
> `registration.name`을 런타임까지 실어보내는 별도 작업이 필요하다 (범위 밖).

---

## 4. Module Interface Specification

> 엔드포인트가 없는 내부 모듈이므로, API 명세 대신 **공개 계약**을 정의한다.

### 4.1 ToolSelectorPort (domain)

```python
# src/domain/tool_selection/interfaces/tool_selector_port.py
class ToolSelectorPort(ABC):
    @abstractmethod
    async def select(
        self,
        query: str,
        candidates: Sequence[ToolCandidate],
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> SelectionResult:
        """질의에 맞는 도구를 골라 SelectionResult로 반환한다.

        계약:
          - 어떤 이유로도 예외를 발생시키지 않는다. 실패는 fallback=True로 표현한다.
          - required_ids는 결과에 항상 포함된다 (candidates에 없어도 그대로 통과).
          - final_ids의 순서는 candidates의 원 순서를 따른다 (결정성).
          - final_ids ⊆ candidates ∪ required_ids (§7 권한 경계 불변).
        """
```

**top-K 절단 (v0.2 추가)**: 프롬프트로 "최대 {top_k}개"를 지시해도 모델이 더 반환할 수 있다.
절단하지 않으면 Plan FR-07의 상한이 사실상 무력해지므로, 정제(`sanitize`) 직후
`kept[:top_k]`로 자른다. **LLM 경로와 캐시 히트 경로 양쪽 모두**에 적용한다
(`llm_tool_selector.py:126, 169`).

> 위 4개 계약은 무작위 3000회 속성 검증으로 위반 0을 확인했다 (Analysis §2.6).

### 4.2 SelectionCachePort (domain)

```python
class SelectionCachePort(ABC):
    @abstractmethod
    async def get(self, key: str) -> tuple[str, ...] | None: ...

    @abstractmethod
    async def set(self, key: str, tool_ids: Sequence[str]) -> None: ...
```

v1 구현체 `NullSelectionCache`는 `get`→`None`, `set`→no-op. 캐시 키는 `sha256(query | sorted(candidate_ids))`로 후보 집합 변화 시 자동 무효화된다 — 나중에 TTL 캐시로 교체할 때 무효화 로직을 새로 짤 필요가 없다.

**무효 캐시 처리 (v0.2 추가)**: 캐시가 돌려준 ID가 정제 후 하나도 남지 않으면 히트로 보지
않고 **LLM 선별로 흘려보낸다** (`llm_tool_selector.py:166-167`). 여기서 폴백해버리면 도구
목록이 바뀔 때마다 선별이 죽는다. 키 설계상 정상 상황에서는 발생하지 않지만, 공유 캐시·키
충돌·수동 주입에서 도달 가능하다.

### 4.3 어댑터 계약

```python
# src/infrastructure/tool_selection/adapters/langchain_filter.py
class ToolIdResolver(Protocol):
    """BaseTool → 카탈로그 표기 tool_id. 경로별 구현을 주입한다."""
    def resolve(self, tool: Any) -> str | None: ...


class DefaultToolIdResolver:
    """기본 구현체 (v0.2 추가). 주입하지 않으면 이것이 쓰인다.

    MCPToolAdapter를 import 하지 않고 ``server_config``/``mcp_tool_name`` 속성
    유무만 본다 — import 하는 순간 tool_selection이 mcp 인프라에 묶인다.
    provider 네이티브 dict(``request.tools``는 ``list[BaseTool | dict]``)는
    None을 반환해 §6.1 #8 경로로 보낸다.
    """
    def resolve(self, tool: Any) -> str | None: ...


class LangChainToolFilter:
    async def filter(
        self,
        tools: list,                # list[BaseTool]
        query: str,
        *,
        required_ids: Sequence[str] = (),
        request_id: str = "",
    ) -> list:
        """선별 후 도구 목록 반환. 실패 시 입력을 그대로 돌려준다."""
```

**결선 완료 (v0.4 — module-4).** `general_chat/use_case.py`의 `stream()`에서
도구 빌드 직후:

```python
tools = await self._tool_builder.build(...)
if self._tool_filter is not None:
    tools = await self._tool_filter.filter(
        tools, request.message,
        required_ids=REQUIRED_TOOL_IDS, request_id=request_id,
    )
```

| 요소 | 위치 | 비고 |
|---|---|---|
| 호출부 | `general_chat/use_case.py` `stream()` | `tool_filter=None`이면 건너뜀 (하위호환) |
| 필수 세트 | `general_chat/tools.py` `REQUIRED_TOOL_IDS` | 호출부가 소유 — 모듈은 조회하지 않음 (FR-04) |
| DI | `api/main.py` `_build_tool_filter()` | 킬스위치 off / 조립 실패 시 `None` |
| 킬스위치 | `settings.tool_selector_enabled` | **기본 `False`** — 명시 활성화 전까지 무동작 |

**탈부착 계약은 결선 후에도 유지된다.** `GeneralChatUseCase`는 `tool_selection`을
**import 하지 않고** duck typing(`tool_filter`)으로만 받는다. 모듈 2개 디렉토리를
지웠을 때 실제로 고쳐야 하는 곳은 `api/main.py` **한 곳뿐**이며, application 계층
테스트 81건은 그대로 통과한다(측정 완료). 이 성질은
`test_application_layer_never_imports_the_module`이 CI에서 강제한다.

### 4.4 LLM 프롬프트 계약

```
[System]
당신은 도구 선별기다. 사용자 질의를 수행하는 데 실제로 필요한 도구만 고른다.
- 최대 {top_k}개. 확신이 없으면 적게 고른다.
- 반드시 아래 목록에 있는 id만 출력한다. 새 id를 만들지 않는다.
- 설명 없이 JSON만 출력한다: {"tool_ids": ["...", "..."]}

[User]
질의: {query}

사용 가능한 도구:
- {tool_id} | {name} | {effective_description}
- ...
```

파싱은 관대하게(코드펜스 제거 후 `json.loads`), 검증은 엄격하게(화이트리스트 대조).

**설명 압축 (v0.3 추가)**: 후보 1건 = 1줄이라는 형식은 실제 데이터에서 지켜지지 않는다.
MCP 도구 설명은 `Args:` 블록을 포함한 여러 줄 docstring이라, 압축하지 않으면 도구 13개만으로
프롬프트가 2878자가 된다. `summarize_description`이 시그니처 블록(`Args:`/`Returns:` 등)을
잘라내고 공백을 정규화해 `MAX_DESCRIPTION_CHARS`(200)까지 줄인다.
**실측: 2878자 → 1778자 (38% 감소), 도구 13개 = 13줄.**
선별에 필요한 건 "무엇을 하는가"뿐이고 인자 스키마는 실제 호출 시점에 바인딩된 도구가 알려준다.

**MCP 도구명 정규화 (v0.3 추가)**: `tool.name`은 `sanitize(f"mcp_{uuid}_{tool}")`이라 UUID
40자가 앞에 붙는다. 그대로 넘기면 후보 목록이 UUID로 도배되므로 어댑터가 `mcp_tool_name`
(`docx_to_html`)을 표시명으로 쓴다.

---

## 5. UI/UX Design

**N/A** — 사용자 인터페이스 없음. 프론트엔드 변경 없음 (루트 CLAUDE.md §4-1 API 계약 동기화 해당 없음).

---

## 6. Error Handling

### 6.1 실패 모드와 처리

> 이 모듈에 HTTP 에러 코드는 없다. 모든 실패는 **결과값으로 표현**되며 호출부는 예외를 볼 수 없다.

| # | 실패 상황 | `fallback` | `reason` | 반환 `final_ids` | 로그 레벨 |
|---|----------|:---:|---|---|---|
| 1 | 후보 수 ≤ top_k | False | `under_threshold` | 전체 후보 (LLM 미호출) | DEBUG |
| 2 | 후보 0개 | False | `no_candidates` | `required_ids` | DEBUG |
| 3 | LLM 예외 (네트워크·인증) | **True** | `llm_error` | `required_ids` | WARNING (스택 포함) |
| 4 | LLM 타임아웃 | **True** | `llm_timeout` | `required_ids` | WARNING |
| 5 | JSON 파싱 실패 | **True** | `parse_error` | `required_ids` | WARNING (원문 일부 첨부) |
| 6 | 미지 ID 포함 (환각) | False | `sanitized` | required ∪ 유효분 | WARNING (`dropped_ids`) |
| 7 | 정제 후 선택이 0개 | **True** | `empty_selection` | `required_ids` | WARNING |
| 8 | 어댑터에서 id 해석 실패·중복 | — | — | **입력 도구 전량 그대로** | WARNING |
| 9 | 캐시 히트 (v0.2 추가) | False | `cache_hit` | required ∪ 캐시분 | DEBUG |

**#8이 최후 방어선**이다. 어댑터가 도구를 식별하지 못하면 선별 자체를 포기하고 원본을 반환한다 — 즉 "이 모듈이 있기 전"으로 되돌아간다.

### 6.2 로그 페이로드 (FR-10)

```python
self._logger.info(
    "Tool selection completed",
    request_id=request_id,
    candidate_count=result.candidate_count,
    selected_count=len(result.final_ids),
    fallback=result.fallback,
    reason=result.reason,
    elapsed_ms=result.elapsed_ms,
)
```

`docs/rules/logging.md` 준수 — `print()` 금지, 예외는 `exception=e`로 스택 트레이스 보존.

---

## 7. Security Considerations

- [x] **프롬프트 인젝션 내성** — 유저 질의가 도구 목록과 함께 모델에 들어가지만, **출력은 화이트리스트로 검증**되므로 "모든 도구를 선택하라" 같은 주입이 성공해도 최대 피해는 현재(전량 바인딩)와 동일하다. 목록에 없는 도구를 만들어낼 수는 없다.
- [x] **민감정보 미유출** — 셀렉터에 넘기는 것은 도구 메타데이터(id/name/description)와 현재 유저 메시지뿐. 인증 컨텍스트·문서 본문·대화 이력은 넘기지 않는다.
- [x] **권한 경계 불변** — 선별은 **축소만** 한다. 호출부가 주지 않은 도구를 결과에 추가할 수 없다 (`final_ids ⊆ candidates ∪ required_ids`). 기존 권한 필터링(`auth_ctx`)을 우회할 경로가 없다.
- [x] **가용성** — 셀렉터 장애가 채팅을 중단시키지 않는다 (§6.1).
- N/A — 입력 검증(XSS/SQLi), HTTPS, Rate Limiting: 외부 노출 표면 없음.

---

## 8. Test Plan

> **정의만 여기서.** 테스트 코드는 Do 단계에서 구현과 한 세트로 작성한다 (CLAUDE.md TDD 필수).
> 백엔드 내부 모듈이므로 템플릿의 L1/L2/L3를 **유닛 / 통합 / 골드셋 평가**로 매핑한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| **L1: 유닛** | domain Policy·VO — 순수 함수, 외부 의존 0 | pytest | Do |
| **L2: 통합** | `LLMToolSelector` + 어댑터 — LLM은 스텁 주입 | pytest + fake LLM | Do |
| **L3: 골드셋 평가** | Recall 측정 — 실 LLM 1회 실행 | pytest (`@pytest.mark.llm`, CI 제외) | Do/Check |
| **L4: 아키텍처** | 레이어 의존·탈부착 | `/verify-architecture` + pytest | Check |

### 8.2 L1: 유닛 테스트 시나리오

| # | 대상 | 테스트 | 기대 결과 |
|---|------|-------|----------|
| 1 | `merge` | required ∪ selected | 중복 제거, 후보 원순서 유지 |
| 2 | `merge` | required가 candidates에 없음 | 그래도 결과에 포함 |
| 3 | `sanitize` | 미지 ID 3개 섞임 | 유효분만 남고 `dropped_ids`에 3개 |
| 4 | `needs_selection` | 후보 5개, top_k 8 | False (LLM 미호출) |
| 5 | `is_low_signal` | `"MCP tool: search_blog"` / name=`search_blog` | True |
| 6 | `is_low_signal` | 정상 설명 | False |
| 7 | `tokenize_name` | `search_blog_posts` | `"search blog posts"` |
| 8 | `effective_description` | 스텁 + server_name 있음 | `"naver_mcp 서버의 'search blog' 기능"` |
| 9 | `SelectionResult.final_ids` | 순서 결정성 | 동일 입력 → 동일 순서 |

### 8.3 L2: 통합 테스트 시나리오

| # | 대상 | 상황 | 기대 결과 |
|---|------|-----|----------|
| 1 | `LLMToolSelector` | 정상 JSON 응답 | `final_ids` = required ∪ 응답, `fallback=False` |
| 2 | `LLMToolSelector` | LLM이 `RuntimeError` | `fallback=True`, `reason="llm_error"`, required만, **예외 미전파** |
| 3 | `LLMToolSelector` | 타임아웃 | `reason="llm_timeout"`, required만 |
| 4 | `LLMToolSelector` | `"응답: {잘못된json"` | `reason="parse_error"`, required만 |
| 5 | `LLMToolSelector` | 존재하지 않는 id 반환 | 폐기 + WARNING, `reason="sanitized"` |
| 6 | `LLMToolSelector` | 빈 배열 반환 | `reason="empty_selection"`, required만 |
| 7 | `LLMToolSelector` | 후보 3개 (top_k=8) | **LLM 호출 0회** (스파이로 검증), 전량 통과 |
| 8 | `LangChainToolFilter` | 정상 | 입력 순서 보존한 부분집합 반환 |
| 9 | `LangChainToolFilter` | `ToolIdResolver`가 전부 `None` | **입력 그대로 반환** (§6.1 #8) |
| 10 | `LangChainToolFilter` | selector가 예외를 던지도록 조작 | 입력 그대로 반환, WARNING |
| 11 | `NullSelectionCache` | get/set | 항상 `None` / no-op |

### 8.4 L3: 골드셋 평가 시나리오

| # | 항목 | 방법 | 성공 기준 |
|---|------|-----|----------|
| 1 | **Recall** | 골드셋 20~30건, 실 LLM. 각 케이스 `expected_tool_ids ⊆ final_ids`? | **≥ 95%** (Plan §3.2) |
| 2 | **도구 수 감소율** | 동일 후보 풀 기준 before/after 평균 | 리포트에 기록 (목표 40→8~10) |
| 3 | **MCP 저신호 효과** | 보강 on/off 두 번 실행 | 보강 시 Recall 우세를 수치로 기록 |
| 4 | **지연** | `elapsed_ms` P95 | < 1500ms |

### 8.5 골드셋 데이터 요구사항

| Entity | 최소 개수 | 필수 필드 |
|--------|:--------:|----------|
| 골드셋 케이스 | 20 | `query`, `expected_tool_ids`, `candidate_pool_ref` |
| 후보 도구 풀 | 40+ | `tool_id`, `name`, `description`, `source` (실제 MCP 저신호 케이스 5건 이상 포함) |

**위치**: `tests/fixtures/tool_selection/goldset.json`
**수집**: 실제 General Chat 로그 기반 권장 — 합성 질의만으로는 저신호 MCP 문제가 재현되지 않는다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | 역할 | 이 기능의 위치 |
|-------|------|---------------|
| **domain** | Port, VO, Policy | `src/domain/tool_selection/` |
| **application** | UseCase, 흐름 제어 | **Phase 1에서 변경 없음** |
| **infrastructure** | LLM 호출, 어댑터 | `src/infrastructure/tool_selection/` |
| **interfaces** | FastAPI 라우터 | 해당 없음 |

### 9.2 Dependency Rules

```
   interfaces ──→ application ──→ domain ←── infrastructure
                       │                          │
                       └──→ infrastructure        └─ langchain은 adapters/ 에서만

   규칙: domain은 아무것도 참조하지 않는다 (langchain·DB·HTTP 전부 금지)
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/tool_selection/` | 표준 라이브러리만 | **langchain, DB, HTTP, 다른 도메인 모듈** |
| `infrastructure/tool_selection/` | `domain/tool_selection/`, `domain/llm/`, `domain/llm_model/`, `domain/logging/` | application, interfaces |
| `infrastructure/tool_selection/adapters/` | 위 + `langchain_core`, `langchain` | application, interfaces |
| application (Phase 2) | `domain/tool_selection/` 의 Port만 | 구현체 직접 참조 금지 |

> **핵심 제약**: 코어(`llm_tool_selector.py`)조차 langchain을 import하지 않는다. LLM 인스턴스는 기존 `LLMFactoryInterface`를 통해 받는다.

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ToolSelectorPort` | Domain | `src/domain/tool_selection/interfaces/tool_selector_port.py` |
| `SelectionCachePort` | Domain | `src/domain/tool_selection/interfaces/selection_cache_port.py` |
| `ToolCandidate` / `SelectionResult` / `ToolSource` | Domain | `src/domain/tool_selection/schemas.py` |
| `ToolSelectionPolicy` (+ 토큰화 함수) | Domain | `src/domain/tool_selection/policies.py` |
| `LLMToolSelector` | Infrastructure | `src/infrastructure/tool_selection/llm_tool_selector.py` |
| 프롬프트 템플릿 | Infrastructure | `src/infrastructure/tool_selection/prompts.py` |
| `NullSelectionCache` | Infrastructure | `src/infrastructure/tool_selection/null_cache.py` |
| `LangChainToolFilter` / `ToolIdResolver` | Infrastructure (adapter) | `src/infrastructure/tool_selection/adapters/langchain_filter.py` |
| `ToolSelectionMiddleware` | Infrastructure (adapter) | `src/infrastructure/tool_selection/adapters/selector_middleware.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예시 |
|------|------|------|
| 클래스 | PascalCase | `LLMToolSelector`, `ToolCandidate` |
| 함수/메서드 | snake_case | `select()`, `effective_description()` |
| 상수 | UPPER_SNAKE_CASE | `DEFAULT_TOP_K`, `_LOW_SIGNAL_PREFIX` |
| 모듈 파일 | snake_case.py | `llm_tool_selector.py` |
| 패키지 | snake_case | `tool_selection/` |
| Port 접미사 | `~Port` (신규) | `ToolSelectorPort` |

> 기존 코드베이스는 `~Interface`(`LLMFactoryInterface`)와 `~Port` 두 관례가 혼재한다. 신규 모듈은 **`~Port`로 통일**하고 기존 파일은 건드리지 않는다.

### 10.2 Import Order

```python
# 1. 표준 라이브러리
import json
import re
from dataclasses import dataclass

# 2. 서드파티 (adapters/ 에서만 langchain 허용)
from langchain_core.tools import BaseTool

# 3. 내부 — domain 우선
from src.domain.tool_selection.schemas import ToolCandidate

# 4. 타입 전용
from typing import Protocol, Sequence
```

### 10.3 Environment Variables

| Variable | 목적 | 기본값 | Scope |
|----------|------|-------|-------|
| `TOOL_SELECTOR_PROVIDER` | 셀렉터 provider | `openai` | Server |
| `TOOL_SELECTOR_MODEL_NAME` | 경량 모델명 | `gpt-4o-mini` | Server |
| `TOOL_SELECTOR_TOP_K` | 선별 상한 | `8` | Server |
| `TOOL_SELECTOR_TIMEOUT_SEC` | LLM 타임아웃 | `3.0` | Server |
| `TOOL_SELECTOR_ENABLED` | 킬스위치 | `false` (Phase 2에서 true) | Server |

`src/config.py`의 `settings`에 추가한다 — `search_pipeline_provider` / `search_pipeline_model_name`(`config.py:116`)과 동일한 패턴. CLAUDE.md §3 "config 값 하드코딩 금지" 준수.

### 10.4 This Feature's Conventions

| 항목 | 적용 규약 |
|------|----------|
| 함수 길이 | 40줄 이하 — `select()`는 폴백 분기를 private 헬퍼로 분리 |
| if 중첩 | 2단계 이하 — early return + `match` 활용 |
| 타입 | 전 공개 함수에 명시적 typing, VO는 `@dataclass(frozen=True)` |
| 에러 처리 | 예외 삼키기 금지 → 반드시 WARNING + `exception=e` (스택 보존) |
| 로깅 | `LoggerInterface` 주입, `print()` 금지 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/tool_selection/
│   ├── __init__.py
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── tool_selector_port.py        ToolSelectorPort
│   │   └── selection_cache_port.py      SelectionCachePort
│   ├── schemas.py                       ToolSource, ToolCandidate, SelectionResult
│   └── policies.py                      ToolSelectionPolicy, 토큰화 함수
│
└── infrastructure/tool_selection/
    ├── __init__.py
    ├── llm_tool_selector.py             LLMToolSelector(ToolSelectorPort)
    ├── prompts.py                       SELECTOR_SYSTEM_PROMPT, build_user_prompt()
    ├── null_cache.py                    NullSelectionCache
    └── adapters/
        ├── __init__.py
        ├── langchain_filter.py          LangChainToolFilter, ToolIdResolver
        └── selector_middleware.py       ToolSelectionMiddleware (선택, 미배선)

tests/
├── domain/tool_selection/
│   ├── __init__.py
│   └── test_policies.py                 L1
├── infrastructure/tool_selection/
│   ├── __init__.py
│   ├── test_llm_tool_selector.py        L2
│   ├── test_langchain_filter.py         L2
│   ├── test_selector_middleware.py      L2  (v0.2 추가)
│   ├── test_module_boundaries.py        L4  (v0.2 추가 — 아래)
│   └── test_goldset_recall.py           L3 (@pytest.mark.llm)
└── fixtures/tool_selection/
    └── goldset.json
```

**`test_module_boundaries.py` (v0.2 추가)**: Plan SC "탈부착 검증"을 사람 규율이 아니라
CI로 강제한다. `ast`로 각 파일의 import를 파싱해 도메인 순수성 / 코어의 langchain 무지 /
역방향 참조 금지 / **모듈 밖 소비자 0**을 검사한다. 마지막 항목은 module-4 결선 시
의도적으로 실패하며, 그때가 탈부착 계약을 재검토할 시점이다.

### 11.2 Implementation Order

1. [ ] domain VO·Port 정의 (테스트 먼저 — `test_policies.py` Red)
2. [ ] `ToolSelectionPolicy` 구현 (merge / sanitize / needs_selection / 토큰화) → Green
3. [ ] `SelectionCachePort` + `NullSelectionCache`
4. [ ] `prompts.py` 프롬프트 템플릿
5. [ ] `LLMToolSelector` — 정상 경로 먼저, 폴백 분기 각각 테스트와 세트로
6. [ ] `LangChainToolFilter` + `ToolIdResolver`
7. [ ] `ToolSelectionMiddleware` (선택 어댑터)
8. [ ] `config.py` settings 추가
9. [ ] 골드셋 수집 + Recall 평가 스크립트
10. [ ] `/verify-architecture`, `/verify-tdd`, `/verify-logging` + 탈부착 검증

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | 설명 | 산출물 | 예상 턴 |
|--------|-----------|------|-------|:------:|
| **도메인 계약** | `module-1` | Port 2종, VO 3종, Policy(합집합·정제·토큰화). 외부 의존 0 | `src/domain/tool_selection/**`, `tests/domain/tool_selection/test_policies.py` | 15-20 |
| **LLM 셀렉터** | `module-2` | `LLMToolSelector` + 프롬프트 + 폴백 8종 + `NullSelectionCache` + config | `src/infrastructure/tool_selection/*.py`, `test_llm_tool_selector.py` | 25-35 |
| **어댑터 & 검증** | `module-3` | `LangChainToolFilter`, `ToolSelectionMiddleware`, 골드셋, 아키텍처·탈부착 테스트 | `adapters/**`, `test_langchain_filter.py`, `test_goldset_recall.py`, `goldset.json` | 25-30 |
| **결선** (별건) | `module-4` | `use_case.py:367` 1줄 + DI + 킬스위치. **Plan §2.2 Out of Scope — 별도 PDCA 사이클** | `general_chat/use_case.py`, `api/main.py` | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | 턴 |
|---------|-------|-------|:--:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 40-55 |
| Session 3 | Do | `--scope module-3` | 25-30 |
| Session 4 | Check + Report | 전체 | 30-40 |

> `module-4`(결선)는 이번 사이클 **범위 밖**이다. Plan §2.2에서 Out of Scope로 확정했고, 결선 시 §3.2의 MCP ID 정규화 충돌을 정면으로 다뤄야 하므로 별도 사이클이 적절하다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 최초 작성. Option C 선택 + MCP 이름 토큰화 보강 반영 | tkdrb136 |
| 0.4 | 2026-08-13 | **module-4 결선 완료** — `general_chat/use_case.py` 호출부, `REQUIRED_TOOL_IDS`, `main.py` DI, 킬스위치. 탈부착은 duck typing으로 유지(모듈 제거 시 수정 지점은 main.py 1곳) | tkdrb136 |
| 0.3 | 2026-08-13 | **Doc Convert MCP 실측 반영 (Act-2)** — §3.2 D-4 해소(server_id는 `MCPServerConfig.name`에 이미 포함, 저장소 조회 불필요) / §3.3 서버명 보강이 실제로는 UUID 노이즈를 주입함을 확인해 비활성 / §4.4 설명 압축·도구명 정규화 추가 | tkdrb136 |
| 0.2 | 2026-08-13 | Check 단계 표류 교정 6건 — §3.2 MCP 런타임 ID가 `server_name` 기반임을 명시하고 module-4 선결 과제로 승격 / §3.3 `is_low_signal` 의사코드 오류 교정(이름 대조 → 패턴 매칭) / §4.1 top-K 절단 + 4번째 계약 추가 / §4.2 무효 캐시 처리 명시 / §4.3 `DefaultToolIdResolver` 추가 / §6.1 `cache_hit` 행 추가 / §11.1 테스트 2종 추가 | tkdrb136 |
