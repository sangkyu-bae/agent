# prompt-depth Design Document

> **Summary**: `PromptSections`를 4→7섹션으로 확장하고 `assemble()`을 마크다운 헤딩 조립으로 전환한다. 구조가 값을 하는 곳(Context·Workflow)만 전용 VO를 신설하고, Identity·Style은 평문으로 둔다.
>
> **Project**: sangplusbot (`idt` 백엔드 + `idt_front` 프론트엔드)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft
> **Planning Doc**: [prompt-depth.plan.md](../../01-plan/features/prompt-depth.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| PM (PRD) | `docs/00-pm/prompt-depth.prd.md` | ❌ 없음 — Plan에서 직행 (사용자 결정 8건이 Plan에 기록됨) |
| 선행 사이클 | `docs/archive/2026-08/prompt-composer/` | ✅ |
| 직전 사이클 | `docs/02-design/features/agent-create-wizard.design.md` | ✅ |

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 인계에서 전략 맥락이 유실되지 않게 한다.

| Key | Value |
|-----|-------|
| **WHY** | 생성되는 시스템 프롬프트가 얕아 에이전트가 기대만큼 동작하지 않는다. 원인은 질문 부족이 아니라 출력 스키마가 4필드로 고정된 것 |
| **WHO** | P2 — 에이전트 소유자. 특히 도메인 규칙·금지사항이 명확한 업무(분석·심사·상담)에 에이전트를 쓰려는 실무자 |
| **RISK** | ① LLM 출력 스키마 확장 → strict 모드 위반·생성 실패·지연 증가 ② 마크다운 전환으로 기존 저장 프롬프트와 표기 이원화 ③ 프롬프트 8000자는 에이전트 **호출마다** 실리는 고정 토큰 비용 |
| **SUCCESS** | "데이터 분석 에이전트 만들어줘" 1문장 → 7섹션이 모두 채워진 프롬프트가 생성되고 8000자 이내로 저장된다. 기존 경로 회귀 0 |
| **SCOPE** | prompt_composer 스키마·조립 + intent 스펙 2축 + 길이 상한 + 프론트 정합. **기존 에이전트 재생성·Fix 탭은 범위 밖** |

---

## 1. Overview

### 1.1 Design Goals

1. **그릇을 넓히되 결정성을 잃지 않는다** — 섹션이 7개가 되어도 `assemble()`은 순수 함수로 남아 동일 입력이 바이트 동일 출력을 낸다 (SC-5/FR-08).
2. **strict 스키마를 깨지 않는다** — `_PromptDraft`의 모든 신규 필드는 고정 필드·배열·중첩 BaseModel뿐이며 `dict[str, X]`가 0건이다 (R-01).
3. **신규 정보가 실제로 프롬프트에 도달한다** — intent 2축이 슬롯에만 남고 프롬프트에 안 실리면 이 사이클은 아무것도 바꾸지 못한다 (§3.5가 이 사이클의 숨은 핵심 변경이다).
4. **기존 5경로 물리적 무변경** — `agent_composer`·`auto_agent_builder`는 diff 0줄.

### 1.2 Design Principles

- **구조는 값을 할 때만 만든다** — `situation`+`steps[]`처럼 조립 규칙이 구조를 실제로 쓰는 곳만 VO. 나머지는 평문.
- **계산 필드는 LLM이 도달할 수 없는 곳에** — `degraded`/`dropped_tool_ids`/`unknown_tool_ids`/`elapsed_ms`는 신규 섹션 추가 후에도 `_PromptDraft`에 없다 (FR-06).
- **프롬프트 지시는 2차 방어선** — 도구 환각 차단은 여전히 `drop_hallucinated`가 한다.
- **domain은 env를 모른다** — 라운드 상한 단일 출처는 `IntentConfig`.

### 1.3 코드 실측으로 확정된 사실 (Plan §7.3 사전 판정)

| Plan 질문 | 실측 결과 | 결론 |
|---|---|---|
| **A-7** 신규 2축 전달 경로 | `use_case.py:250-254`가 `intent.model_dump()` 전체를 넘기지만, `prompts.intent_block()`(`prompts.py:67-81`)은 `label`/`reason`만 읽고 `filled_slots`를 **버린다** | `intent_block()` 확장이 **FR-19의 실제 변경 지점**. 이것 없이는 2축 추가가 프롬프트에 아무 영향도 주지 않는다 |
| **A-8** 타임아웃 상향 | `PROMPT_COMPOSER_TIMEOUT_SEC`은 `PromptComposerConfig`의 env 단일 출처 | 코드 변경 불필요. 실측 후 `.env`로만 조정 |
| **R-07** `schema_version` 분기 | `repository.py`에 역방향 파서(`_sections_from_json`)가 존재하지 않고, 조회는 `assembled` 텍스트만 사용 (`repository.py:223` 주석) | `schema_version=2` 승격 안전. 분기 코드 불필요 |
| **R-08** 8000자 지점 | `application/agent_builder/schemas.py:104,132` / `domain/agent_create_pipeline/policies.py:35` / `interfaces/schemas/prompt_composer.py:22` / `idt_front/src/types/agentPipeline.ts:188` — **총 5곳** | `agent_composer/schemas.py:13`의 4000은 **건드리지 않는다** (Fix 탭 = 범위 밖) |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 신규 4섹션 전부 평문 str/tuple | 4섹션 모두 전용 VO | 구조가 값을 하는 2곳만 VO |
| **신규 도메인 VO** | 0 | 4 (Identity/Context/Workflow/Style) | **2 (ContextSection/WorkflowSection)** |
| **신규 `_PromptDraft` 서브모델** | 0 | 4 | **2** |
| **New Files** | 0 | 0 | 0 (기존 모듈 확장) |
| **Modified Files** | 11 | 11 | **11** |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (Workflow 절차가 문장 나열로 뭉개짐) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | FR-03 미달 | R-02(섹션별 얕아짐)·지연 최대 | 균형 |
| **Recommendation** | — | — | **Selected** |

**Selected**: **Option C — Pragmatic** — **Rationale**: 사용자 선택. `WorkflowSection(situation, steps[])`은 조립이 `### {situation}` + 번호 목록으로 실제 구조를 소비하므로 VO 값이 있다. 반면 `identity`/`style`은 조립이 문단 하나로 흘려보낼 뿐이라 VO로 쪼개면 LLM 스키마 필드만 늘고(R-02) 얻는 것이 없다.

### 2.1 Component Diagram

```
[프론트 위저드]
      │ POST /api/v1/agent-create/pipeline
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ AgentCreatePipelineUseCase (application)                         │
│   intent → tools → prompt → create → bind                        │
│     │                        │                                    │
│     │ build_agent_create_spec()  ← ★ constraints/decision_priority │
│     ▼                        ▼                                    │
│  AnalyzeIntentUseCase    ComposePromptUseCase                     │
└──────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼──────────────────────────┐
        ▼                       ▼                          ▼
 ToolCatalogMetaReader   LLMPromptGeneratorAdapter   PromptRepository
   (infrastructure)         (infrastructure)          (infrastructure)
                                │  ★ _PromptDraft 7섹션
                                │  ★ prompts.SYSTEM 지침
                                │  ★ prompts.intent_block(filled_slots)
                                ▼
                     PromptAssemblyPolicy (domain, 순수)
                       ★ assemble() 마크다운
                       ★ clamp_sections 확대
                       ★ fallback_sections 7섹션
                                │
                                ▼
                        assembled: str  ──→ clamp_prompt(8000) ──→ system_prompt
```

★ = 이 사이클의 변경 지점.

### 2.2 Data Flow

```
사용자 1문장
  → intent(6축, 최대 3라운드, 신규 2축 optional)
  → filled_slots{purpose, target_users, data_sources, tone, constraints, decision_priority}
  → intent_block()이 filled_slots를 프롬프트 재료로 렌더  ★신규
  → LLM이 _PromptDraft(7섹션) 생성
  → _to_sections(): Draft → PromptSections VO + clamp_sections
  → drop_hallucinated(): 후보 밖 tool_id 폐기
  → assemble(): 마크다운 조립 (빈 섹션 헤더째 생략)
  → clamp_prompt(8000) → CreateAgentRequest.system_prompt
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `PromptAssemblyPolicy` | `prompt_composer.schemas` VO만 | 순수 조립 규칙 (외부 의존 0) |
| `LLMPromptGeneratorAdapter` | `PromptAssemblyPolicy`, `prompts`, `PromptComposerConfig` | Draft→VO 매핑, 폴백 |
| `prompts.intent_block()` | 없음 (dict 입력) | intent 스냅샷 → 프롬프트 텍스트 |
| `build_agent_create_spec()` | `domain.intent.schemas` | 슬롯 스펙 (env 미참조) |

---

## 3. Data Model

### 3.1 도메인 VO — `domain/prompt_composer/schemas.py`

```python
@dataclass(frozen=True)
class ContextSection:
    """FR-02 — 에이전트가 지켜야 할 제약과 알아야 할 배경.

    constraints 는 intent 의 `constraints` 축과 이름이 같지만 같은 값이 아니다.
    LLM 이 목적·도구로부터 도출한 제약도 함께 들어온다.
    """
    constraints: tuple[str, ...] = ()
    background: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSection:
    """FR-03 — 상황 1건에 대한 처리 절차.

    구조를 두는 이유: 조립이 `### {situation}` + 번호 목록으로 실제 소비한다.
    평문이면 "일반 요청일 때 / 모호할 때"의 경계가 사라진다.
    """
    situation: str
    steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptSections:
    """LLM 이 생성하는 7개 섹션 (기존 4 + 신규 3필드).

    Design §2.4 P2(선행 사이클) 승계 — 계산 필드를 두지 않는다.
    신규 필드는 전부 기본값을 가진다: 기존 생성자 호출부가 깨지지 않는다.
    """
    purpose: str
    identity: str = ""                                  # 신규 (평문)
    context: ContextSection | None = None               # 신규
    roles: tuple[RoleSection, ...] = ()
    tool_guides: tuple[ToolGuide, ...] = ()
    workflows: tuple[WorkflowSection, ...] = ()         # 신규
    style: str = ""                                     # 신규 (평문)
    principles: tuple[str, ...] = ()
```

> **필드 순서 = 조립 순서**로 맞춘다. 읽는 사람이 VO만 보고 출력 순서를 안다.
> `context`가 `| None`인 이유: 빈 `ContextSection()`과 "없음"을 구분해야 폴백/생략 규칙이 명확해진다.

### 3.2 LLM 스키마 — `infrastructure/prompt_composer/adapter.py`

```python
class _ContextDraft(BaseModel):
    constraints: list[str] = Field(default_factory=list,
        description="반드시 지켜야 할 것과 하지 말아야 할 것")
    background: list[str] = Field(default_factory=list,
        description="이 에이전트가 알아야 할 배경·전제")


class _WorkflowDraft(BaseModel):
    situation: str = Field(description="이 절차가 적용되는 상황")
    steps: list[str] = Field(default_factory=list, description="순서대로 수행할 단계")


class _PromptDraft(BaseModel):
    purpose: str = Field(description="이 에이전트가 무엇을 하는지 1~2문장")
    identity: str = Field(default="", description="어떤 성격·전문성을 가진 존재인지, 누구를 위해 일하는지")
    context: _ContextDraft | None = None
    roles: list[_RoleDraft] = Field(default_factory=list)
    tool_guides: list[_GuideDraft] = Field(default_factory=list)
    workflows: list[_WorkflowDraft] = Field(default_factory=list)
    style: str = Field(default="", description="응답 말투·형식·구조")
    principles: list[str] = Field(default_factory=list, description="동작 원칙")
```

**strict 불변식 (FR-05 / QC-5)**: 이 스키마의 재귀 전개에 `dict`·`Any`·`Union[str, X]`가 0건이다. 기존 strict 테스트가 `_PromptDraft`를 재귀 탐색하도록 확장한다 (§8.1 T-S1).

**도메인 VO ↔ Draft 대응은 1:1**이다. 이름·필드가 같으므로 `_to_sections()` 매핑이 기계적이고, 세 곳(§3.3의 JSON 포함) 중 하나가 빠지면 테스트가 잡는다.

### 3.3 영속 JSON — `_sections_to_json`

```json
{
  "purpose": "...",
  "identity": "...",
  "context": {"constraints": ["..."], "background": ["..."]},
  "roles": [{"title": "...", "detail": "..."}],
  "tool_guides": [{"tool_id": "...", "name": "...", "when": "...", "how": "...", "caution": "..."}],
  "workflows": [{"situation": "...", "steps": ["..."]}],
  "style": "...",
  "principles": ["..."]
}
```

- `context`가 `None`이면 JSON에서 `null`. 키 자체는 항상 존재한다 (필드 집합 동등성 테스트가 키로 비교하므로).
- `_SCHEMA_VERSION = 2` (FR-12). 마이그레이션 없음 — V062가 이미 컬럼을 갖고 있고 역방향 파서가 없어 과거 행 해석 코드가 존재하지 않는다.

### 3.4 필드 집합 동등성 (§6.3 검증 항목의 구조적 보장)

`PromptSections` / `_PromptDraft` / `_sections_to_json` / `SectionsOut` **4곳**의 최상위 키 집합이 같아야 한다. 한 곳이라도 누락되면 값이 조용히 유실된다 — 테스트로 강제한다 (§8.1 T-S2).

### 3.5 intent 슬롯 스펙 — `domain/agent_create_pipeline/spec.py`

```python
SlotSpec(
    key="constraints",
    description="반드시 지켜야 할 규칙이나 하지 말아야 할 것",
    options=["출처 명시 필수", "추측 금지", "개인정보 미출력"],
),
SlotSpec(
    key="decision_priority",
    description="판단이 충돌할 때 무엇을 우선할지",
    options=["정확성 우선", "속도 우선", "안전성 우선"],
),
```

둘 다 `required=False` (FR-15/FR-16). `purpose`만 required이므로 상세히 쓴 1문장은 여전히 되묻기 없이 통과한다 — `decide_after_intent()`가 `result.complete`를 required 기준으로만 계산하기 때문이다 (`policies.py:56`, 무변경).

**옵션을 3개로 두는 이유**: `INTENT_MAX_OPTIONS_PER_SLOT=4` 이내이면서, 자유 서술을 유도하되 사용자가 빠르게 고를 선택지를 준다.

---

## 4. API Specification

### 4.1 계약 변경 요약 (엔드포인트 신설 없음)

| Method | Path | 변경 |
|--------|------|------|
| POST | `/api/v1/agent-create/pipeline` | 응답 `assembled_prompt` 포맷이 마크다운으로. **스키마 무변경** (문자열 계약) |
| POST | `/api/v1/prompts/compose` | 응답 `sections`에 필드 3개 additive 추가 |
| GET | `/api/v1/prompts/sessions/{id}` | 무변경 (`VersionSummaryOut`은 `sections`를 싣지 않음) |
| POST | `/api/v1/prompts/sessions/{id}/versions` | `assembled` max_length 4000 → **8000** |
| POST | `/api/v1/agents` | `system_prompt` max_length 4000 → **8000** |
| PATCH | `/api/v1/agents/{id}` | 동상 |

### 4.2 `SectionsOut` 확장 (additive)

```python
class ContextOut(BaseModel):
    constraints: list[str] = []
    background: list[str] = []

class WorkflowOut(BaseModel):
    situation: str
    steps: list[str] = []

class SectionsOut(BaseModel):
    purpose: str
    identity: str = ""                       # 신규
    context: ContextOut | None = None        # 신규
    roles: list[RoleOut]
    tool_guides: list[ToolGuideOut]
    workflows: list[WorkflowOut] = []        # 신규
    style: str = ""                          # 신규
    principles: list[str]
```

신규 필드 전부 기본값을 가진다 → `additive-contract-extension` 규약 충족. 구형 프론트는 무시하면 되고, 응답 파싱이 깨지지 않는다.

### 4.3 조립 출력 계약 (FR-07 / A-3·A-4 판정)

**번호 없음 · 에이전트 이름 제목 없음** (사용자 선택). `purpose`는 헤더 없는 리드 문단으로 남긴다 — 기존 조립과 같은 위치이므로 이 부분만은 계약이 이어진다.

```
{purpose}

## Role and Identity
{identity}

## Context
- {constraint}
- {constraint}

배경:
- {background}

## Core Responsibilities
- {title}: {detail}

## Tool Guidelines
- {name} ({tool_id}): {when} / {how}
  주의: {caution}

## Workflow
### {situation}
1. {step}
2. {step}

## Communication Style
{style}

## Important Notes
- {principle}
```

**불변식**
1. 빈 섹션은 **헤더째 생략** (FR-07). `context`의 `constraints`/`background`도 각각 비면 해당 줄 묶음만 생략하고, 둘 다 비면 `## Context`가 통째로 사라진다.
2. 블록 구분자는 `"\n\n"`, 끝은 `rstrip()` — 기존 `assemble()` 규약 승계.
3. 시간·UUID·랜덤 없음 (FR-08).
4. **A-5 판정**: 도구 0개면 `## Tool Guidelines`를 생략한다 (현행 계약 유지). "사용 가능한 도구 없음"을 쓰지 않는 이유는 §5.1의 degraded 규칙과 충돌하지 않게 하기 위해서다 — 도구 0개는 실패가 아니라 정상 구성이므로 조용히 빠지는 편이 맞다.

### 4.4 `intent_block()` 확장 (FR-19 — 이 사이클의 숨은 핵심)

현행은 `label`/`reason`만 싣는다. 확장 후:

```
[사전 분석된 사용자 의도]
- 분류: {label}
- 근거: {reason}
- 대상 사용자: {target_users}
- 참조 자료: {data_sources}
- 말투/형식: {tone}
- 지켜야 할 제약: {constraints}
- 판단 우선순위: {decision_priority}
이 판정은 참고용입니다. 요청 본문과 충돌하면 요청이 우선입니다.
```

**설계 규칙**
- 렌더 대상 키와 한글 라벨은 **모듈 상수 화이트리스트**로 고정한다. `filled_slots`를 통째로 순회하지 않는다 — intent 모듈이 축을 늘릴 때마다 프롬프트가 조용히 바뀌면 생성 품질이 관측 없이 흔들린다 (`IntentSnapshot`의 `extra="allow"`가 통과 저장은 허용하되 **해석은 하지 않는다**는 §3.4 원칙의 연장).
- 값이 빈 축은 줄째 생략.
- `degraded` 판정은 여전히 블록 자체를 붙이지 않는다 (FR-13 승계). `_usable_intent()`가 이미 상류에서 걸러낸다.
- 이 블록에는 계산 필드(`complete`/`missing_slots`/`confidence`)를 싣지 않는다 — 프롬프트 재료가 아니다.

---

## 5. 조립·폴백 규칙 상세 (domain/prompt_composer/policies.py)

### 5.1 `fallback_sections()` — degraded 경로 (FR-10 / A-6 판정)

**사용자 선택: 고정 문구로 7섹션 전부 채운다.**

```python
_FALLBACK_IDENTITY = "사용자의 요청을 처리하는 범용 에이전트입니다."
_FALLBACK_CONTEXT = ContextSection(
    constraints=("제공된 제약 조건이 없으므로 일반적인 안전 기준을 따른다",),
    background=(),
)
_FALLBACK_WORKFLOW = WorkflowSection(
    situation="일반 요청",
    steps=("요청 내용을 확인한다", "필요하면 도구를 사용한다", "결과를 정리해 답한다"),
)
_FALLBACK_STYLE = "한국어로 간결하게 답한다."
_FALLBACK_PRINCIPLES = (...)  # 기존 3개 유지
```

**폴백 관측 가능성이 죽지 않는 이유**: 기존 주석의 "요청과 무관하게 같은 값이어야 폴백임이 드러난다"는 원칙은 **값이 상수라는 것**이지 섹션이 비어 있다는 뜻이 아니다. 위 전부가 모듈 상수이므로 출력만 봐도 폴백을 식별할 수 있고, `degraded=true` + `reason` + `steps.prompt=DEGRADED`라는 1차 신호는 그대로다. 단위 테스트가 "폴백 출력 == 상수 조합"을 단언한다 (§8.1 T-P4).

`tool_guides`는 기존대로 `metas`에서 만든다. 도구가 0개면 §4.3-4에 따라 해당 섹션만 생략된다 — 폴백이라도 없는 도구를 지어내지 않는다.

### 5.2 `clamp_sections()` 확대 (FR-09)

| 상수 | 값 | 근거 |
|------|---:|------|
| `MAX_ROLES` | 6 | 기존 |
| `MAX_TOOL_GUIDES` | 50 | 기존 (`MAX_TOOL_IDS`와 동일) |
| `MAX_PRINCIPLES` | 10 | 기존 |
| `MAX_CONSTRAINTS` | 10 | 신규 |
| `MAX_BACKGROUND` | 5 | 신규 |
| `MAX_WORKFLOWS` | 5 | 신규 — 상황 5개면 충분, 초과분은 8000자를 잠식 |
| `MAX_WORKFLOW_STEPS` | 8 | 신규 — 절차당 |
| `MAX_IDENTITY_CHARS` | 500 | 신규 — 평문이라 항목 수가 아닌 길이로 자른다 |
| `MAX_STYLE_CHARS` | 500 | 신규 |

**상한 총합 검산**: 최악의 경우에도 조립 결과가 8000자를 크게 넘지 않아야 `clamp_prompt`의 절단이 상시 발생하지 않는다. roles 6×~120 + guides 50×~150 + constraints 10×~80 + workflows 5×(제목+8단계) + principles 10×~60 ≈ 11,000자 → **도구가 많은 경우 여전히 절단 가능**. 이는 기존에도 동일한 성질이며(guides 50개만으로 7500자), 절단 사유는 `steps.create.reason`으로 관측된다. 본 사이클은 상한을 낮추지 않는다 — R-03(토큰 비용) 관측 후 후속 판단.

### 5.3 `drop_hallucinated` / `_replace_guides` (FR-11)

`_replace_guides()`가 필드를 하나씩 나열해 `PromptSections`를 재구성하고 있어 **신규 3필드를 그대로 떨어뜨린다** (Plan §6.2 "Needs verification"의 실체). `dataclasses.replace()`로 교체한다:

```python
def _replace_guides(sections, guides):
    return replace(sections, tool_guides=guides)
```

`clamp_sections()`도 동일하게 `replace()` 기반으로 바꾸면 향후 필드 추가에서 같은 사고가 재발하지 않는다. 이 전환 자체가 회귀 방지 설계다.

---

## 6. Error Handling

### 6.1 실패 경로 (기존 계약 승계)

| 상황 | 처리 | 관측 |
|------|------|------|
| LLM 타임아웃 | `_degrade(_REASON_TIMEOUT)` → 7섹션 폴백 | `warning`, `degraded=true` |
| strict 스키마 위반 | `_degrade(_REASON_SCHEMA)` | `error`, `reason="schema"` |
| `purpose` 빈 값 | `_degrade(_REASON_EMPTY)` | `warning` |
| 신규 섹션만 빈 값 | **degrade 아님** — 해당 섹션 생략 후 정상 반환 | 로그에 섹션별 count |
| 조립 결과 > 8000자 | `clamp_prompt()` 절단 + 사유 | `steps.create.reason` |
| `assembled` > 8000 (사람 편집 저장) | 422 | 프론트가 사전 차단 (FR-23) |

**신규 섹션 미충족을 degraded로 올리지 않는 이유**: `degradation-vs-failure-boundary` 위키 기준은 "쓸 수 있는 결과가 존재하는가"다. `identity`가 비어도 프롬프트는 쓸 수 있다. 여기서 degrade를 올리면 정상 생성물이 "실패"로 칠해져 화면이 거짓말을 한다.

### 6.2 관측 강화 (R-02 대응)

`_log_success()`에 섹션별 카운트를 추가한다 — 어떤 섹션이 상습적으로 비는지 실측 없이는 프롬프트 지침을 고칠 수 없다.

```python
identity_len=len(sections.identity),
constraint_count=len(sections.context.constraints) if sections.context else 0,
workflow_count=len(sections.workflows),
style_len=len(sections.style),
assembled_chars=...,   # R-03 토큰 비용 실측 근거
```

본문은 여전히 남기지 않는다 (PII).

---

## 7. Security Considerations

- [x] 사용자 입력이 프롬프트에 실린다 — 기존과 동일한 경로이며 신규 표면 없음. 로그에 본문 미기록 유지.
- [x] `intent_block()` 화이트리스트 — `extra="allow"`로 들어온 임의 키가 프롬프트에 주입되지 않는다 (§4.4). **이것이 없으면 클라이언트 에코백을 통한 프롬프트 인젝션 경로가 열린다.**
- [x] 에코백 슬롯값은 `SLOT_VALUE_MAX_CHARS=200`으로 clamp (`reuse_intent`, 무변경). 신규 2축도 `spec.slots` 기반 화이트리스트에 자동 포함된다.
- [x] 길이 상한 8000은 DB `Text` 범위 내 — DoS 표면 변화 없음.
- [ ] N/A: 인증·권한·암호화 변경 없음.

---

## 8. Test Plan

> 여기서는 **무엇을** 검증할지 정의한다. 테스트 코드는 Do 단계에서 구현과 한 세트로 작성한다 (TDD, SC-8).

### 8.1 단위 테스트 (pytest)

| # | ID | 대상 | 검증 내용 | FR |
|---|---|------|-----------|---|
| 1 | T-S1 | `_PromptDraft` | 재귀 전개에 `dict`/`Any` 0건 | FR-05, QC-5 |
| 2 | T-S2 | 4곳 필드 집합 | VO / Draft / JSON / `SectionsOut` 최상위 키 동일 | §3.4 |
| 3 | T-P1 | `assemble()` | 7섹션 전부 채운 입력 → 헤딩 순서·형식 정확 일치 | FR-07 |
| 4 | T-P2 | `assemble()` | 빈 섹션은 헤더째 생략 (섹션별 개별 케이스 + 전부 빈 케이스) | FR-07, SC-5 |
| 5 | T-P3 | `assemble()` | 동일 입력 100회 호출 → 바이트 동일 | FR-08 |
| 6 | T-P4 | `fallback_sections()` | 출력이 모듈 상수 조합과 정확히 일치, 7섹션 존재 | FR-10, SC-7 |
| 7 | T-P5 | `clamp_sections()` | 신규 상한 5종 각각 초과 입력 → 앞쪽 유지 절단 | FR-09 |
| 8 | T-P6 | `drop_hallucinated()` | 폐기 후에도 `identity`/`context`/`workflows`/`style` **보존** | FR-11 |
| 9 | T-A1 | `_to_sections()` | Draft 7섹션 → VO 매핑 누락 0 | FR-05 |
| 10 | T-A2 | `intent_block()` | 화이트리스트 키만 렌더, 미지 키 무시, 빈 값 줄 생략 | FR-19, §7 |
| 11 | T-A3 | `intent_block()` | `degraded=true` → 빈 문자열 | FR-13 승계 |
| 12 | T-R1 | `_sections_to_json()` | 신규 3필드 직렬화, `context=None` → `null` | FR-12 |
| 13 | T-R2 | `_insert_version()` | `schema_version == 2` | FR-12 |
| 14 | T-I1 | `build_agent_create_spec()` | 슬롯 6개, 신규 2축 `required=False` | FR-14/15 |
| 15 | T-I2 | `PipelinePolicy.reuse_intent()` | 신규 2축 에코백이 허용 키로 통과 | §6.2 |
| 16 | T-C1 | `clamp_prompt()` | 8000/8001 경계 | FR-21, R-08 |

### 8.2 L1: API 테스트

| # | Endpoint | Method | 검증 | 기대 |
|---|----------|--------|------|------|
| 1 | `/api/v1/prompts/compose` | POST | fake 체인 7섹션 → `sections`에 신규 3필드 존재 | 200 |
| 2 | `/api/v1/prompts/sessions/{id}/versions` | POST | `assembled` 8000자 | 201 |
| 3 | 〃 | POST | `assembled` 8001자 | 422 |
| 4 | `/api/v1/agents` | POST | `system_prompt` 8000자 | 201 |
| 5 | `/api/v1/agent-create/pipeline` | POST | 상세 1문장 → 되묻기 없이 `tools_proposed` | 200, SC-4 |
| 6 | 〃 | POST | 모호한 요청 → `needs_clarification`, 질문에 신규 축 포함 가능 | 200 |
| 7 | `GET /api/v1/prompts/sessions/{id}` | GET | `schema_version=1` 과거 행 조회 정상 | 200, R-07 |

### 8.3 실 LLM 검증 (SC-6 — 이 사이클의 게이트)

`tests/.../test_real_llm.py` 갱신. `OPENAI_API_KEY` 없으면 skip(사유 명시).

| # | 검증 | 기대 |
|---|------|------|
| 1 | 확장 `_PromptDraft`로 실제 호출 | strict 400 없음, `degraded=false` |
| 2 | 7섹션 충족률 | `purpose`·`identity`·`roles`·`workflows`·`style`·`principles` 모두 비어 있지 않음 |
| 3 | 지연 | `elapsed_ms < PROMPT_COMPOSER_TIMEOUT_SEC×1000`, 실측값 기록 |
| 4 | 길이 | `len(assembled)` 기록 → R-03 근거 |

> **fake만으로 이 사이클을 닫지 않는다.** R-01의 실사례(strict 위반이 3개월 은폐)가 정확히 "fake로만 검증했다"에서 나왔다.

### 8.4 L2/L3: 프론트 · E2E

| # | 대상 | 검증 |
|---|------|------|
| 1 | `PromptStep` | 카운터가 `x / 8000` 표기, 8001자에서 초과 경고·저장 차단 |
| 2 | `IntentStep` | "남은 라운드" 표기가 3 기준 |
| 3 | `PromptStep` | 3000자 마크다운 본문에서 textarea 스크롤 가능·높이 확보 (FR-25) |
| 4 | 실서버 E2E | "데이터 분석 에이전트 만들어줘" → 7섹션 프롬프트 생성 → 저장 → `GET /agents/{id}` 확인 (SC-1/2) |
| 5 | 실서버 E2E | 되묻기에서 제약·우선순위 질문 등장 → 답변이 `## Context`/`## Important Notes`에 반영 (SC-3) |

### 8.5 회귀 기준 (QC-3/QC-4, `false-green-quality-gates`)

- 백엔드: 전체 스위트 실행 후 **정렬된 `FAILED` 목록**을 baseline(58건)과 diff. 건수 비교 금지.
- 프론트: `npm run test` FAILED 목록이 직전 커밋과 동일.
- `git diff --stat`에 `agent_composer`·`auto_agent_builder` 0줄 (§1.1-4).

---

## 9. Clean Architecture

### 9.1 이 기능의 레이어 배치

| Component | Layer | Location | 규칙 |
|-----------|-------|----------|------|
| `ContextSection`/`WorkflowSection`/`PromptSections` | Domain | `domain/prompt_composer/schemas.py` | 외부 import 0, frozen dataclass |
| `PromptAssemblyPolicy` (조립·절단·폴백) | Domain | `domain/prompt_composer/policies.py` | 순수 함수, 시간·랜덤 금지 |
| `build_agent_create_spec()` | Domain | `domain/agent_create_pipeline/spec.py` | env 미참조 |
| `PipelinePolicy.PROMPT_MAX_CHARS` | Domain | `domain/agent_create_pipeline/policies.py` | 상수 |
| `ComposePromptUseCase` | Application | `application/prompt_composer/` | **무변경** |
| `_PromptDraft` 계열 | Infrastructure | `infrastructure/prompt_composer/adapter.py` | 도메인은 이 타입을 모른다 |
| `prompts.SYSTEM` / `intent_block()` | Infrastructure | `infrastructure/prompt_composer/prompts.py` | — |
| `_sections_to_json` / `_SCHEMA_VERSION` | Infrastructure | `infrastructure/prompt_composer/repository.py` | commit/rollback 금지 |
| `IntentConfig` | Infrastructure | `infrastructure/config/intent_config.py` | 라운드 상한 **단일 출처** |
| `SectionsOut` 계열 | Interfaces | `interfaces/schemas/prompt_composer.py` | 로직 금지 |
| `MAX_ASSEMBLED_CHARS` / `MAX_CLARIFY_ROUNDS` | 프론트 | `types/agentPipeline.ts` / `AgentCreateEntryPage/index.tsx` | 상수 export는 `types/`에 |

### 9.2 이 사이클에서 지켜야 할 의존 방향

```
interfaces ──→ application ──→ domain ←── infrastructure

금지: domain/prompt_composer → infrastructure (LLM 스키마 참조)
금지: domain/prompt_composer → domain/agent_composer (선행 사이클 Q3)
금지: domain → os.environ / pydantic_settings
```

**`MAX_CLARIFY_ROUNDS`는 프론트 하드코딩 상수로 남는다** — 서버가 라운드 상한을 응답으로 내려주지 않기 때문이다. 값을 3으로 맞추되, 이 이원화 자체는 본 사이클의 범위 밖으로 두고 §6.2 검증 항목("3곳 일치")으로 방어한다.

---

## 10. Coding Convention Reference

| 항목 | 적용 |
|------|------|
| 함수 길이 | 40줄 이내 — `assemble()`이 7섹션을 다루므로 **블록 헬퍼 함수로 분리**한다 (`_identity_block`, `_context_block`, `_workflow_block`, `_style_block`). 기존 `_role_block`/`_tool_block` 패턴 답습 |
| if 중첩 | 2단 이내 — 각 블록 헬퍼는 `if not x: return ""` 조기 반환 |
| 타입 | 전 필드 명시. `tuple[...]` (도메인) / `list[...]` (pydantic) 구분 유지 |
| config | 하드코딩 금지 — 라운드·타임아웃은 env, 조립 상한은 Policy 클래스 상수 |
| 로깅 | `print()` 금지, 본문 미기록 |
| DDL 주석 | **N/A** — 마이그레이션 없음 (§8.4 Plan) |
| 프론트 상수 | 런타임 상수는 컴포넌트 파일에서 export 금지 → `src/types/*.ts` |
| 커밋 | 테스트 선행 커밋 → 구현 커밋 (SC-8) |

---

## 11. Implementation Guide

### 11.1 변경 파일 (신규 파일 0)

```
idt/src/
├── domain/prompt_composer/
│   ├── schemas.py          ★ ContextSection, WorkflowSection, PromptSections +3
│   └── policies.py         ★ assemble 마크다운, clamp 확대, fallback 7섹션, replace() 전환
├── infrastructure/prompt_composer/
│   ├── adapter.py          ★ _ContextDraft, _WorkflowDraft, _PromptDraft +3, _to_sections, 로그
│   ├── prompts.py          ★ SYSTEM 섹션 지침, intent_block 화이트리스트
│   └── repository.py       ★ _sections_to_json +3, _SCHEMA_VERSION = 2
├── interfaces/schemas/
│   └── prompt_composer.py  ★ ContextOut/WorkflowOut/SectionsOut, MAX_ASSEMBLED_CHARS 8000
├── domain/agent_create_pipeline/
│   ├── spec.py             ★ 슬롯 2축
│   └── policies.py         ★ PROMPT_MAX_CHARS 8000
├── infrastructure/config/
│   └── intent_config.py    ★ INTENT_MAX_CLARIFICATION_ROUNDS 3
└── application/agent_builder/
    └── schemas.py          ★ system_prompt 8000 (104, 132행)

idt_front/src/
├── types/agentPipeline.ts  ★ MAX_ASSEMBLED_CHARS 8000
└── pages/AgentCreateEntryPage/index.tsx  ★ MAX_CLARIFY_ROUNDS 3
```

### 11.2 구현 순서

1. [ ] **T-S1/T-S2 먼저** — strict·필드 동등성 테스트를 red 상태로 세운다. 이 두 개가 이후 모든 필드 누락을 잡는 그물이다.
2. [ ] 도메인 VO 확장 → `replace()` 기반 헬퍼 전환 → 기존 테스트 green 확인
3. [ ] `assemble()` 마크다운 + 블록 헬퍼 (T-P1~P3)
4. [ ] `clamp_sections` / `fallback_sections` (T-P4/P5)
5. [ ] `_PromptDraft` + `_to_sections` (T-A1)
6. [ ] `prompts.SYSTEM` 지침 + `intent_block()` 화이트리스트 (T-A2/A3)
7. [ ] `repository` 직렬화 + `schema_version=2` (T-R1/R2)
8. [ ] `SectionsOut` 확장 (L1-1)
9. [ ] intent 2축 + 라운드 3 (T-I1/I2)
10. [ ] 길이 상한 5곳 (T-C1, L1-2~4)
11. [ ] 프론트 정합 2곳 + textarea 확인
12. [ ] **실 LLM 검증** (SC-6) → 실측값으로 프롬프트 지침·타임아웃 조정
13. [ ] 실서버 E2E — 생성된 프롬프트 전문을 사용자와 함께 확인 (Plan §9-5)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 도메인 스키마·조립 | `module-1` | VO 3필드 + `assemble()` 마크다운 + clamp/fallback + `replace()` 전환. 구현 순서 1~4 | 40-50 |
| LLM 스키마·프롬프트·영속 | `module-2` | `_PromptDraft`, `SYSTEM` 지침, `intent_block()`, 직렬화, `schema_version=2`, **실 LLM 검증**. 순서 5~7 + 12 | 40-50 |
| intent 2축 · API 스키마 | `module-3` | 슬롯 2축, 라운드 3, `SectionsOut`. 순서 8~9 | 25-35 |
| 길이 상한 · 프론트 | `module-4` | 8000자 5곳 + 프론트 2곳 + textarea. 순서 10~11 | 25-35 |

**의존**: module-1 → module-2 (VO 확정 후 Draft 매핑). module-3·4는 module-1과 독립이나, 최종 E2E(13)는 전부 끝난 뒤.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 40-50 |
| Session 3 | Do | `--scope module-2` | 40-50 |
| Session 4 | Do | `--scope module-3,module-4` | 40-60 |
| Session 5 | Check + QA + Report | 전체 (실서버 E2E 포함) | 30-40 |

> **선행 조건 (R-09) — 해소됨**: Plan 작성 시점에는 `agent-create-wizard`가 check에서 멈춰 있었으나, 실측 결과 `docs/03-analysis/agent-create-wizard.analysis.md`와 `docs/04-report/agent-create-wizard.report.md`가 모두 존재하고 `pdca-status.json`의 해당 항목이 `phase: completed / matchRate: 95`다. **R-09는 더 이상 module-1 착수를 막지 않는다** (세션 시작 배너의 `check` 표시는 오래된 값). 남은 정리는 `/pdca archive agent-create-wizard`뿐이며 본 사이클과 독립이다.

---

## 12. Plan FR → Design 절 매핑 (Plan §9-3)

| FR | Design 절 | FR | Design 절 |
|----|-----------|----|-----------|
| FR-01 identity | §3.1, §4.3 | FR-14 constraints 축 | §3.5 |
| FR-02 context | §3.1, §4.3 | FR-15 decision_priority 축 | §3.5 |
| FR-03 workflows | §3.1(구조 근거), §4.3 | FR-16 purpose만 required | §3.5 |
| FR-04 style | §3.1, §4.3 | FR-17 라운드 3 단일 출처 | §9.1, §11.1 |
| FR-05 strict 호환 | §3.2, T-S1 | FR-18 회당 질문 3 유지 | 무변경 (`INTENT_MAX_QUESTIONS_PER_ROUND`) |
| FR-06 계산 필드 제외 | §1.2, §3.2 | FR-19 2축 → 프롬프트 | **§4.4** (핵심) |
| FR-07 마크다운 조립 | §4.3 | FR-20 system_prompt 8000 | §11.1 |
| FR-08 결정성 | §4.3-3, T-P3 | FR-21 PROMPT_MAX_CHARS | §11.1, T-C1 |
| FR-09 clamp 확대 | §5.2 | FR-22 assembled 8000 | §4.1, L1-2/3 |
| FR-10 폴백 7섹션 | §5.1 | FR-23 프론트 8000 | §8.4-1 |
| FR-11 환각 폐기 보존 | §5.3, T-P6 | FR-24 프론트 라운드 3 | §8.4-2, §9.2 |
| FR-12 schema_version 2 | §3.3, T-R2 | FR-25 textarea | §8.4-3 |
| FR-13 SYSTEM 지침 | §11.2-6 | FR-26 기존 경로 무변경 | §8.5 |

---

## 13. Open Items (Do 단계 실측 후 확정)

| # | 항목 | 판단 시점 |
|---|------|-----------|
| O-1 | `PROMPT_COMPOSER_TIMEOUT_SEC` 상향 여부 | module-2 실 LLM 계측 후 (§8.3-3) |
| O-2 | `prompts.SYSTEM` 섹션별 지침 문구 조정 | module-2 실제 출력 확인 후 (R-02) |
| O-3 | 조립 상한 하향 여부 | R-03 토큰 비용 실측 후 — 본 사이클에서는 조정하지 않음 (§5.2) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — Option C 선택, A-1~A-8 전항 판정, FR→절 매핑 포함 | 배상규 |
