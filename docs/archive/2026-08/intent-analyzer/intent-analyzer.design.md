# intent-analyzer Design Document

> **Summary**: 라벨을 호출자가 주입하는 탈착형 의도 분석 모듈. `search_decision` 패턴의 4번째 인스턴스로 구현하되, 판정 대상까지 외부화한다.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-08-13
> **Status**: Draft
> **Planning Doc**: [intent-analyzer.plan.md](../../01-plan/features/intent-analyzer.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A — DB 스키마 변경 없음 |
| Phase 2 | Coding Conventions | ✅ `idt/CLAUDE.md` + `idt/docs/rules/` |
| Phase 3 | Mockup | N/A — UI 없음 |
| Phase 4 | API Spec | 본 문서 §4 |

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 인계 시 전략 맥락 유지용.

| Key | Value |
|-----|-------|
| **WHY** | 의도 판정이 3곳에 중복 산재 — 재사용 가능한 단일 모듈 부재 |
| **WHO** | P2 (에이전트 소유자, 주인공) — 부서별 라벨로 자기 그래프에 꽂는 사람. 1차 소비자는 개발자(백엔드) |
| **RISK** | LLM 전용이라 요청당 비용·지연 발생 / 라벨 목록 프레이밍이 과차단을 유발한 선례(위키 계약 2)와 구조적 긴장 |
| **SUCCESS** | 기존 경로 회귀 0건 · 마이그레이션 0건 · domain→infra import 0건 · LLM 실패 3종 모두 degraded 반환 |
| **SCOPE** | 모듈 + 독립 API만. 기존 supervisor/general_chat/multi_query 배선은 **다음 사이클** |

---

## 1. Overview

### 1.1 Design Goals

1. **탈착 가능**: 주입 안 하면 노드가 그래프에 존재조차 하지 않고, 모듈 4개 디렉토리를 통째로 지워도 `main.py` 등록부 외엔 아무것도 안 깨진다.
2. **라벨 무지(無知)**: 모듈 코드 어디에도 `"search"`, `"여신"` 같은 도메인 라벨 문자열이 없다. 라벨은 100% 호출 인자.
3. **선례 일치**: `search_decision` / `visualization` / `planner`가 확립한 구조를 그대로 따라, 코드베이스에 새 패턴을 도입하지 않는다.
4. **본 흐름 불가침**: 어떤 실패도 예외로 새어 나가지 않는다. 최악의 경우 `degraded=True`를 조용히 반환한다.

### 1.2 Design Principles

- **Thin DDD 준수** — domain은 외부 의존 0, LangChain은 infrastructure에만.
- **순수 함수 우선** — 판정은 LLM이 하되, 검증·정규화는 순수 함수(`IntentResultPolicy`)로 분리해 100% 테스트 가능하게 한다.
- **조언 전용(advice-only)** — 이 모듈은 어떤 분기도 강제하지 않는다. state 키 하나만 쓴다.
- **설정은 주입** — 모델·타임아웃은 `pydantic_settings`로, 라벨은 호출 인자로. 하드코딩 0.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | A: 최소 | B: 클린 | C: 실용 균형 |
|------|:-:|:-:|:-:|
| **접근** | 포트+어댑터+라우터만 | LLM 스키마와 도메인 VO 분리 + 매퍼 | 기존 3개 선례 그대로 복제 |
| **노드 팩토리** | ✗ | ✓ | ✓ |
| **정규화 Policy** | ✗ | ✓ | ✓ |
| **LLM 출력 스키마** | `IntentResult` 겸용 | 별도 `IntentLLMOutput` + 매퍼 | `IntentResult` 겸용 |
| **신규 파일** | 7 | 15 | **12** |
| **테스트 파일** | 3 | 6 | **5** |
| **Plan FR 충족** | ✗ FR-07·08·09·12 미달 | ✓ | ✓ |
| **기존 선례 정합** | 부분 | ✗ 4번째만 다른 모양 | ✓ 완전 일치 |
| **복잡도 / 유지비** | Low / Low | High / Medium | Medium / Low |
| **리스크** | 탈착 이음매 부재 = 요구사항 미달 | 매퍼 계층 유지비 | 도메인 VO가 LLM 출력 제약을 받음 |

**Selected: Option C (실용 균형)** — **Rationale**: Plan의 FR을 전부 충족하는 최소 구조. B의 이점(도메인 VO 순수성)은 `IntentResult`가 이미 평면 스칼라·딕셔너리뿐이라 실익이 작은 반면, 기존 `WebSearchDecision`·`VizDecision` 3개 선례에서 이탈하는 비용은 즉시 발생한다. Option C의 유일한 대가는 §2.4에 명시적으로 격리했다.

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          호출자 (2종)                              │
│                                                                  │
│  (1) HTTP        POST /api/v1/intent/analyze   ← 이번 사이클 유일 소비자│
│  (2) LangGraph   create_intent_node(...)       ← 이음매만 출하, 미배선  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │   AnalyzeIntentUseCase     │  application/intent/use_case.py
              │   흐름 제어만               │
              └──────┬──────────────┬──────┘
                     │              │
      ┌──────────────▼───┐   ┌──────▼─────────────────────┐
      │ IntentAnalyzer   │   │ IntentResultPolicy         │
      │ Interface (포트)  │   │ .normalize(raw, spec)      │
      │ domain/intent    │   │ 순수함수 · domain/intent    │
      └──────────▲───────┘   └────────────────────────────┘
                 │ implements
      ┌──────────┴───────────────────┐
      │ LLMIntentAnalyzerAdapter     │  infrastructure/intent/adapter.py
      │ ChatOpenAI                    │
      │  .with_structured_output(     │
      │      IntentResult)            │
      └───────────────────────────────┘
```

### 2.2 Data Flow

```
message + IntentSpec(+history?)
        │
        ▼
 UseCase.execute()
        │
        ├─ spec 검증 (labels ≥ 2, description 필수)  ── 위반 → ValueError → 422
        │
        ▼
 adapter.analyze()  ─── LLM 1회 호출 (timeout N초)
        │
        ├─ 성공 ──▶ raw: IntentResult (degraded 값은 신뢰하지 않음)
        │
        └─ 예외 / 타임아웃 / 스키마 위반
                  ──▶ IntentResultPolicy.degraded()  → label=None, degraded=True
        │
        ▼
 IntentResultPolicy.normalize(raw, spec)   ← 순수 함수
        │  ① spec 밖 label → None + ambiguous=True
        │  ② confidence 0.0~1.0 clamp
        │  ③ missing_slots ∩ spec.slots
        │  ④ label is None → confidence = 0.0
        │  ⑤ degraded 는 호출측이 정한 값으로 확정 (LLM 값 무시)
        ▼
 IntentResult  ──▶ 구조화 로그 1건 (label / confidence / degraded / latency_ms)
        │
        ▼
 HTTP 200  또는  {state_key: result.model_dump()}
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AnalyzeIntentUseCase` | `IntentAnalyzerInterface`, `IntentResultPolicy`, `LoggerInterface` | 흐름 제어 — 구체 LLM을 모름 |
| `create_intent_node` | `AnalyzeIntentUseCase`(또는 포트), `LoggerInterface` | LangGraph state 어댑팅 |
| `LLMIntentAnalyzerAdapter` | `langchain_openai`, `IntentAnalyzerInterface`, `IntentConfig` | 유일하게 LangChain을 아는 곳 |
| `intent_router` | `AnalyzeIntentUseCase`, `get_current_user` | HTTP 절단면 |
| `IntentResultPolicy` | **없음** (순수 함수) | 검증·정규화 |

### 2.4 Option C의 명시적 대가 — `degraded` 필드 오염 위험

`IntentResult`를 `with_structured_output` 스키마로 겸용하므로, **LLM이 `degraded` 필드를 임의로 채울 수 있다**.

| 방어선 | 내용 |
|--------|------|
| 1차 (프롬프트) | 필드 `description`에 "항상 false로 두세요" 명시 (§4.3) |
| 2차 (어댑터) | 성공 경로에서 파싱 직후 `degraded=False`로 **무조건 덮어쓴다**. LLM 값을 절대 신뢰하지 않는다. |
| 3차 (Policy) | `normalize()`가 `degraded`를 인자로 받아 확정한다 — `raw.degraded`를 읽지 않는다. |
| 테스트 | "LLM이 `degraded=True`를 반환해도 성공 경로면 `False`" 케이스를 필수 테스트로 둔다 |

> 같은 논리가 향후 추가되는 "LLM이 정해선 안 되는 필드" 전부에 적용된다. 그런 필드가 3개를 넘으면 Option B(별도 LLM 스키마 + 매퍼)로 리팩터링할 신호로 본다.

---

## 3. Data Model

> **DB 스키마 변경 없음.** 마이그레이션 파일 0건. 아래는 전부 in-memory VO (pydantic).

### 3.1 Entity Definition

```python
# src/domain/intent/schemas.py — 외부 의존은 pydantic 뿐

class Turn(BaseModel):
    """대화 이력 1턴. 모듈은 이력을 보유하지 않고 인자로만 받는다."""
    role: Literal["user", "assistant"]
    content: str


class IntentLabel(BaseModel):
    """호출자가 정의하는 의도 후보 1개. 모듈은 name의 의미를 모른다."""
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)   # 필수 — 프롬프트 품질의 전부 (Plan R3)


class IntentSpec(BaseModel):
    """분류 체계 — 100% 호출자 주입 (Plan D3)."""
    labels: list[IntentLabel] = Field(..., min_length=2)   # 2개 미만은 판정 불가
    slots: list[str] = Field(default_factory=list)          # 추출 희망 키 (선택)
    allow_unknown: bool = True                              # False여도 강제하지 않음 (§4.3 주의)


class IntentResult(BaseModel):
    """판정 결과. LLM structured output 스키마 겸용 (Option C, §2.4 참조)."""
    label: str | None = Field(
        default=None,
        description="가장 잘 맞는 후보 의도의 name. 명확히 해당하는 것이 없으면 비워 두세요.",
    )
    confidence: float = Field(default=0.0, description="0.0~1.0 확신도")
    entities: dict[str, str] = Field(
        default_factory=dict, description="메시지에서 추출한 슬롯 키-값"
    )
    ambiguous: bool = Field(default=False, description="후보가 둘 이상으로 갈리면 true")
    missing_slots: list[str] = Field(
        default_factory=list, description="요청된 슬롯 중 값을 찾지 못한 키"
    )
    reason: str = Field(default="", description="판단 근거(짧게)")
    degraded: bool = Field(
        default=False, description="시스템이 채우는 필드입니다. 항상 false로 두세요."
    )
```

**필드 확정 근거 (Plan §9 숙제)**

| 필드 | 채택 | 근거 |
|------|:----:|------|
| `label: str \| None` | ✓ | Enum 아님 — 라벨이 호출자 주입이므로 타입을 고정할 수 없다 |
| `confidence` | ✓ | Plan D1. `ambiguous`와 중복 아님 — "확신 낮음"과 "후보가 갈림"은 다른 신호 |
| `entities` / `missing_slots` | ✓ | Plan D1 슬롯 추출. `dict[str, str]` 평면 유지 — 중첩은 LLM 신뢰도가 떨어진다 |
| `ambiguous` | ✓ | Plan R2 완화 장치 — 호출자가 "되묻기" 판단에 쓴다 |
| `reason` | ✓ | 선례(`WebSearchDecision.reason`) 일치. 디버깅·프롬프트 튜닝용 |
| `degraded` | ✓ | Plan D6. 기존 3개 모듈이 폴백을 **침묵**으로 처리해 호출자가 구분 못 했던 문제의 해소 |
| `rewritten_query` | ✗ | Plan §2.2 Out of Scope — `query_rewrite` 모듈의 기존 책임 |

### 3.2 Entity Relationships

```
IntentSpec 1 ──── N IntentLabel     (labels, 최소 2)
IntentSpec 1 ──── N str             (slots, 0 이상)

analyze(message, spec, history) ──▶ IntentResult
                    ▲
                    └── N Turn (optional, 순서 있음)
```

### 3.3 Database Schema

**N/A** — 판정 결과를 저장하지 않는다 (Plan §2.2). `db/migration/` 신규 파일 0건이 성공 기준(Plan §4.1).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|:----:|
| POST | `/api/v1/intent/analyze` | 메시지 의도 판정 | Required |

> prefix `/api/v1/intent` 는 기존 라우터 52개(`app.include_router` 블록, `src/api/main.py` ~4964행)와 **충돌 없음을 확인**했다.

### 4.2 Detailed Specification

#### `POST /api/v1/intent/analyze`

**Request:**
```json
{
  "message": "작년 대비 여신 한도 기준이 어떻게 바뀌었나요?",
  "spec": {
    "labels": [
      { "name": "search",   "description": "근거 문서를 찾아야 답할 수 있는 질문" },
      { "name": "analysis", "description": "이미 가진 데이터를 계산·비교해야 하는 질문" },
      { "name": "chat",     "description": "잡담·인사 등 도구가 필요 없는 대화" }
    ],
    "slots": ["기간", "대상"],
    "allow_unknown": true
  },
  "history": [
    { "role": "user", "content": "여신 규정 알려줘" },
    { "role": "assistant", "content": "어떤 부분을 찾아드릴까요?" }
  ]
}
```

| 필드 | 타입 | 필수 | 비고 |
|------|------|:----:|------|
| `message` | string | ✓ | 빈 문자열 불가 |
| `spec.labels` | IntentLabel[] | ✓ | **2개 이상**, 각각 `name`·`description` 필수 |
| `spec.slots` | string[] | ✗ | 기본 `[]` |
| `spec.allow_unknown` | bool | ✗ | 기본 `true` |
| `history` | Turn[] | ✗ | 없으면 현재 메시지만으로 판정 |

**Response (200 OK):**
```json
{
  "label": "search",
  "confidence": 0.82,
  "entities": { "기간": "작년", "대상": "여신 한도 기준" },
  "ambiguous": false,
  "missing_slots": [],
  "reason": "규정 문서를 찾아야 답할 수 있는 질문",
  "degraded": false
}
```

**Response (200 OK, LLM 실패 시) — 에러가 아니다:**
```json
{
  "label": null,
  "confidence": 0.0,
  "entities": {},
  "ambiguous": false,
  "missing_slots": [],
  "reason": "",
  "degraded": true
}
```

> **설계 결정**: LLM 실패는 **200 + `degraded=true`** 로 응답한다. 5xx가 아니다.
> 이 모듈의 계약은 "본 흐름을 막지 않는다"(Plan D6)이므로, 호출자가 에러 핸들링 없이
> `degraded`만 보고 "의도 모름 = 기존대로"로 진행할 수 있어야 한다.

**Error Responses:**

| Code | 조건 |
|------|------|
| `401 Unauthorized` | 인증 실패 (`Depends(get_current_user)`) |
| `422 Unprocessable Entity` | `labels` 2개 미만 / `description` 누락 / `message` 빈 문자열 (pydantic 검증) |

> **4xx/5xx가 아닌 것**: LLM 예외·타임아웃·스키마 위반 — 전부 200 + `degraded=true`.

### 4.3 프롬프트 설계 (Plan R2 완화 — 본 설계의 핵심)

**위험 재확인**: 위키 계약 2는 "프롬프트에 할 수 있는 것 목록을 주면 LLM이 목록 밖 요청을 전부 거부(과차단)했고, '목록에 없어도 처리하라'류 방어 지시는 목록 프레이밍을 이기지 못한다"를 실장애로 기록했다(커밋 08d37cab). 의도 분석은 **본질적으로 라벨 목록을 프롬프트에 넣는 일**이므로 이 위험을 정면으로 안는다.

**방어 3층 — 구조적 방어가 주(主), 프롬프트 문구는 부(副)**

| 층 | 방어 | 강도 |
|----|------|:----:|
| **1. 구조** | 이 모듈은 **아무것도 게이팅하지 않는다**. 판정은 조언이고, 이번 사이클엔 어디에도 배선되지 않는다. 과차단이 발생해도 막을 것이 없다. | **강** |
| **2. 프레이밍** | 프롬프트를 "권한 목록"이 아니라 **"분류 과제"**로 짠다. "너는 분류기다"와 "너는 거절하지 않는다"를 명시. 목록의 의미론 자체를 권한에서 라벨로 옮긴다. | 중 |
| **3. 탈출구** | `label` 빈 값 허용 + `ambiguous` 플래그. "억지로 고르지 마라"가 성립하려면 고르지 않을 자유가 스키마에 있어야 한다. | 중 |

**System 프롬프트 (초안 — Do 단계에서 상수로 고정)**
```
당신은 사용자 메시지를 분류하는 분석기입니다. 요청을 수행하지도, 거절하지도 않습니다.
오직 아래 후보 중 어느 것에 해당하는지만 판단합니다.

[후보]
{labels_block}

규칙:
- 어느 후보에도 명확히 해당하지 않으면 label을 비워 두세요. 억지로 고르지 마세요.
- 후보에 없는 주제의 메시지도 정상적인 메시지입니다. 이 목록은 권한이 아니라 분류표입니다.
- 후보가 둘 이상으로 갈리면 ambiguous=true 로 표시하세요.
- confidence 는 0.0~1.0 실수입니다.
- degraded 는 시스템이 채웁니다. 항상 false 로 두세요.
{slots_block}
```

- `labels_block` = `- {name}: {description}` 을 줄바꿈으로 연결
- `slots_block` = `spec.slots`가 있을 때만: `- entities 에 다음 키를 가능한 만큼 채우세요: {키 목록}. 값을 찾지 못한 키는 missing_slots 에 넣으세요.`

**Human 프롬프트**
```
[이전 대화]
{history_block}

[현재 메시지]
{message}
```
- `history_block` = `{role}: {content}` 줄바꿈 연결, 없으면 `(없음)`
- 이력은 최근 N턴으로 절단한다 (N은 `INTENT_ANALYZER_HISTORY_LIMIT`, 기본 6)

**`allow_unknown=False` 처리**: 프롬프트 문구만 "가급적 후보 중에서 고르세요"로 바뀔 뿐, **빈 label을 거부하지 않는다**. 강제하면 오분류를 유도해 위키 계약 2의 실패를 재현하기 때문이다. `allow_unknown`은 **힌트이지 제약이 아니다** — 이 비대칭을 필드 docstring에 명시한다.

### 4.4 모델 · 설정

```python
# src/infrastructure/config/intent_config.py
class IntentConfig(BaseSettings):
    INTENT_ANALYZER_MODEL: str = "gpt-4o-mini"
    INTENT_ANALYZER_TEMPERATURE: float = 0.0
    INTENT_ANALYZER_TIMEOUT_SEC: float = 10.0
    INTENT_ANALYZER_HISTORY_LIMIT: int = 6

    model_config = {"env_file": ".env", "extra": "ignore"}
```

| 항목 | 값 | 근거 |
|------|-----|------|
| 모델 | `gpt-4o-mini` | 분류 과제에 충분. `LLMSearchDecisionAdapter` 기본값과 동일하게 맞춰 운영 일관성 확보 |
| temperature | `0.0` | 분류는 결정적이어야 함. 선례 3개 모두 0.0 |
| timeout | `10.0s` | Plan NFR. 초과 시 `degraded=True` |
| history_limit | `6` | 프롬프트 비대 방지. 튜닝 여지를 env로 열어 둠 |

> **전부 기본값을 가진다** → 미설정 환경에서도 동작한다 (기존 배포 무영향, Plan §8.3).

---

## 5. UI/UX Design

**N/A** — 백엔드 전용. 프론트엔드 변경 0건, `idt_front/` 타입 동기화 불필요 (Plan §6.2).
`§5.4 Page UI Checklist` 역시 해당 없음 — Gap 분석 시 UI 축은 평가 대상에서 제외한다.

---

## 6. Error Handling

### 6.1 오류 분류 및 처리

| # | 상황 | 발생 위치 | 처리 | 응답 |
|---|------|-----------|------|------|
| E1 | `labels` 2개 미만 / `description` 누락 | pydantic 검증 | 요청 거부 | `422` |
| E2 | `message` 빈 문자열 | pydantic 검증 | 요청 거부 | `422` |
| E3 | 인증 실패 | `get_current_user` | 요청 거부 | `401` |
| E4 | **LLM 예외** (네트워크·인증·rate limit) | adapter | `logger.error(..., exception=e)` → `degraded()` | `200` + `degraded=true` |
| E5 | **LLM 타임아웃** | adapter (`asyncio.wait_for`) | `logger.warning(..., exception=e)` → `degraded()` | `200` + `degraded=true` |
| E6 | **structured output 스키마 위반** | adapter (pydantic ValidationError) | `logger.error(..., exception=e)` → `degraded()` | `200` + `degraded=true` |
| E7 | LLM이 `spec` 밖 label 반환 | `IntentResultPolicy.normalize` | `label=None` + `ambiguous=True` **강등**. degraded 아님 | `200` |
| E8 | `confidence` 범위 이탈 (음수·1 초과) | `IntentResultPolicy.normalize` | 0.0~1.0 clamp | `200` |
| E9 | LLM이 `degraded=true` 반환 | adapter | 성공 경로면 `False`로 덮어씀 (§2.4) | `200` |

**E4~E6 공통 계약**: 예외를 밖으로 던지지 않는다. `AnalyzeIntentUseCase`도 `intent_router`도 try/except를 갖지 않는다 — 어댑터가 끝낸다.

**E7 vs E4 구분이 중요한 이유**: E7은 LLM이 **정상 동작**했으나 답이 후보 밖인 경우다. `degraded`로 표시하면 호출자가 "시스템 장애"로 오독한다. `degraded`는 **판정을 시도조차 못 한 경우**만 뜻한다.

### 6.2 Error Response Format

기존 `ExceptionHandler` 미들웨어 포맷을 그대로 따른다 (신규 에러 포맷 도입 없음).

```json
{ "detail": "..." }
```

### 6.3 로깅 규약

```python
# 성공
logger.info("intent analyzed", request_id=..., label=..., confidence=...,
            degraded=False, ambiguous=..., latency_ms=...)
# 폴백
logger.error("intent analysis failed, fallback=degraded",
             exception=e, request_id=..., latency_ms=...)
```

- `print()` 금지 (CLAUDE.md §6)
- `exception=e` 로 스택 트레이스 기록 — `error=str(e)` 금지 (위키 `structured-logger-warning-exception`)
- 라벨 목록·메시지 전문은 로그에 남기지 않는다 (§7 참조)

---

## 7. Security Considerations

- [x] **입력 검증** — pydantic. `labels` 개수·`description` 필수·`message` 비어있지 않음. SQL/DB 접근 자체가 없어 injection 표면 없음.
- [x] **인증** — `Depends(get_current_user)`. 미인증 401. 기존 라우터 관례와 동일.
- [x] **프롬프트 인젝션 표면 인지** — `spec.labels[].description`과 `message`가 프롬프트에 삽입된다. 다만 이 모듈은 **도구를 호출하지 않고 구조화 필드만 반환**하므로, 인젝션 성공의 최대 피해는 "라벨을 틀리게 고름"이며 `normalize()`가 spec 밖 라벨을 강등하므로 임의 값 주입도 불가하다. → **완화 불필요, 리스크 수용**.
- [x] **민감정보 로깅 금지** — 사용자 메시지 원문을 로그에 남기지 않는다. `label`·`confidence`·`latency_ms`만 기록.
- [ ] **Rate Limiting** — 별도 도입 없음. 기존 미들웨어 정책을 따른다. (LLM 호출 1회/요청이므로 남용 시 비용 발생 — 배선 사이클에서 재검토, Plan R1)
- [x] **인가(권한) 분기 없음** — 판정은 사용자별 데이터에 접근하지 않는다. 인증만 확인하고 추가 권한 검사는 하지 않는다.

---

## 8. Test Plan

> **원칙**: 여기서는 *무엇을* 테스트할지 정의한다. 테스트 **코드**는 Do 단계에서 구현과 1:1 세트로 작성한다 (TDD Red→Green→Refactor).

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|:-----:|
| **L0: 단위** | domain Policy(순수함수), 노드 팩토리, UseCase(fake analyzer), adapter(fake chain) | pytest | Do |
| **L1: API** | `POST /api/v1/intent/analyze` — 상태코드·응답 형태 | pytest + `TestClient` | Do |
| L2: UI Action | **N/A** — UI 없음 | — | — |
| L3: E2E | **N/A** — UI 없음 | — | — |
| **수동** | 실 LLM 1회 호출 검증 (`OPENAI_API_KEY` 필요) | curl | Do 종료 시 |

### 8.2 L0: 단위 테스트 시나리오

**`IntentResultPolicy.normalize` — 순수 함수, 분기 100% 커버 (Plan §4.2)**

| # | 입력 | 기대 |
|---|------|------|
| 1 | label이 spec.labels 안에 있음 | 그대로 통과 |
| 2 | label이 spec 밖 (`"weather"`) | `label=None`, `ambiguous=True`, `degraded=False` (E7) |
| 3 | `label=None` + `confidence=0.9` | `confidence=0.0` 으로 강제 |
| 4 | `confidence=1.7` | `1.0` clamp |
| 5 | `confidence=-0.3` | `0.0` clamp |
| 6 | `missing_slots=["기간","날씨"]`, `spec.slots=["기간"]` | `["기간"]` 만 남음 |
| 7 | `spec.slots=[]` 인데 `missing_slots` 비어있지 않음 | `[]` 로 필터 |
| 8 | LLM이 `degraded=True` 반환 + 성공 경로 | `degraded=False` (§2.4 / E9) ★ |
| 9 | `IntentResultPolicy.degraded()` | `label=None, confidence=0.0, degraded=True` |

**`LLMIntentAnalyzerAdapter` — fake chain 주입**

| # | 상황 | 기대 |
|---|------|------|
| 10 | chain이 예외 raise | `degraded=True`, 예외 밖으로 안 나감, `logger.error(exception=...)` 호출됨 (E4) |
| 11 | chain이 timeout 초과 | `degraded=True` (E5) |
| 12 | chain이 스키마 위반 값 반환 | `degraded=True` (E6) |
| 13 | 정상 반환 | `degraded=False`, normalize 적용됨 |
| 14 | `history=None` | 프롬프트에 `(없음)` 삽입, 정상 동작 |
| 15 | `history` 20턴 | 최근 6턴만 프롬프트에 포함 |

**`create_intent_node` — 탈착 이음매 (Plan FR-08/09)**

| # | 상황 | 기대 |
|---|------|------|
| 16 | `analyzer=None` | **`None` 반환** — 호출측이 `add_node`를 건너뛸 수 있음 ★ |
| 17 | 정상 노드 실행 | 반환 dict의 키가 `{state_key}` **단 1개** (다른 state 키 미오염) ★ |
| 18 | `state_key="my_intent"` | 그 키로 기록됨 |
| 19 | analyzer가 degraded 반환 | 노드는 예외 없이 `degraded=True` 결과를 state에 기록 |

**`AnalyzeIntentUseCase`**

| # | 상황 | 기대 |
|---|------|------|
| 20 | `labels` 1개 | `ValueError` (→ 라우터에서 422) |
| 21 | `description` 빈 문자열 | `ValueError` |
| 22 | 정상 | analyzer 1회 호출, 로그 1건 |

### 8.3 L1: API 테스트 시나리오

| # | Endpoint | Method | 설명 | 기대 상태 | 기대 응답 |
|---|----------|--------|------|:--------:|-----------|
| 1 | `/api/v1/intent/analyze` | POST | 정상 판정 (fake analyzer) | 200 | `label` 이 요청한 labels 중 하나, `degraded=false` |
| 2 | `/api/v1/intent/analyze` | POST | 미인증 | 401 | — |
| 3 | `/api/v1/intent/analyze` | POST | `labels` 1개 | 422 | 검증 에러 |
| 4 | `/api/v1/intent/analyze` | POST | `description` 누락 | 422 | 검증 에러 |
| 5 | `/api/v1/intent/analyze` | POST | `message` 빈 문자열 | 422 | 검증 에러 |
| 6 | `/api/v1/intent/analyze` | POST | LLM 실패 (fake가 raise) | **200** | `degraded=true`, `label=null` ★ |
| 7 | `/api/v1/intent/analyze` | POST | `history` 생략 | 200 | 정상 동작 |

### 8.4 아키텍처 회귀 테스트 (Plan 성공 기준 직결)

| # | 검증 | 방법 |
|---|------|------|
| A1 | `domain/intent` 가 infrastructure를 import하지 않음 | `/verify-architecture` |
| A2 | `application/intent` 가 `langchain*` 을 import하지 않음 | `/verify-architecture` + grep |
| A3 | 기존 파일 변경이 `src/api/main.py` 1개뿐 | `git diff --name-only` |
| A4 | `db/migration/` 신규 파일 0건 | `ls` |
| A5 | 로깅 규약 준수 (`print()` 0건, `exception=` 사용) | `/verify-logging` |
| A6 | 프로덕션 모듈 대비 테스트 존재 | `/verify-tdd` |
| A7 | **탈착성** — 모듈 4개 디렉토리 삭제 시 `main.py` 등록부 외 컴파일 에러 0 | 수동 (Do 종료 시 1회) |

### 8.5 Seed Data Requirements

**N/A** — DB 미사용. 테스트는 fake analyzer / fake chain 주입으로 충족한다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | 책임 | 위치 |
|-------|------|------|
| **interfaces** | FastAPI 라우터, request/response 스키마 | `src/api/routes/`, `src/interfaces/schemas/` |
| **application** | UseCase, LangGraph 노드 팩토리 — 흐름 제어만 | `src/application/intent/` |
| **domain** | VO, 포트, 정책(순수함수) | `src/domain/intent/` |
| **infrastructure** | LLM 어댑터, 설정 | `src/infrastructure/intent/`, `src/infrastructure/config/` |

### 9.2 Dependency Rules

```
┌────────────────────────────────────────────────────────────┐
│  interfaces ──→ application ──→ domain ←── infrastructure  │
│                                                            │
│  domain 은 아무것도 향하지 않는다 (pydantic 외 의존 0)         │
│  application 은 infrastructure 의 구체 클래스를 모른다         │
│    → 포트(IntentAnalyzerInterface)만 안다                    │
│  DI는 src/api/main.py 단일 컴포지션 루트에서 수행              │
└────────────────────────────────────────────────────────────┘
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `api/routes/intent_router.py` | application, interfaces/schemas, interfaces/dependencies | infrastructure 직접 |
| `application/intent/` | domain | **`langchain*`, `openai`, DB 세션** |
| `domain/intent/` | pydantic, typing | 그 외 전부 |
| `infrastructure/intent/` | domain, langchain, config | application, interfaces |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `Turn`, `IntentLabel`, `IntentSpec`, `IntentResult` | Domain | `src/domain/intent/schemas.py` |
| `IntentAnalyzerInterface` | Domain (포트) | `src/domain/intent/interfaces.py` |
| `IntentResultPolicy` | Domain (순수함수) | `src/domain/intent/policies.py` |
| `AnalyzeIntentUseCase` | Application | `src/application/intent/use_case.py` |
| `create_intent_node` | Application | `src/application/intent/node.py` |
| `LLMIntentAnalyzerAdapter` | Infrastructure | `src/infrastructure/intent/adapter.py` |
| `IntentConfig` | Infrastructure | `src/infrastructure/config/intent_config.py` |
| `AnalyzeIntentRequest/Response` | Interfaces | `src/interfaces/schemas/intent.py` |
| `intent_router` | Interfaces | `src/api/routes/intent_router.py` |
| DI 배선 | Composition Root | `src/api/main.py` (**유일한 수정 파일**) |

---

## 10. Coding Convention Reference

> 근거: `idt/CLAUDE.md` §3, `idt/docs/rules/logging.md`, `idt/docs/rules/testing.md`

### 10.1 Naming Conventions

| 대상 | 규칙 | 예시 |
|------|------|------|
| 클래스 / VO | PascalCase | `IntentResult`, `LLMIntentAnalyzerAdapter` |
| 포트 인터페이스 | `{도메인}Interface` | `IntentAnalyzerInterface` (선례: `SearchDecisionInterface`) |
| 정책 | `{도메인}Policy` | `IntentResultPolicy` (선례: `VisualizationRoutingPolicy`) |
| 어댑터 | `LLM{도메인}Adapter` | `LLMIntentAnalyzerAdapter` (선례: `LLMSearchDecisionAdapter`) |
| 노드 팩토리 | `create_{name}_node` | `create_intent_node` (선례: `create_chart_router_node`) |
| 함수 / 변수 | snake_case | `analyze()`, `request_id` |
| 프롬프트 상수 | `_SYSTEM`, `_HUMAN` (모듈 private) | 선례: `search_decision/adapter.py` |
| 파일 / 폴더 | snake_case | `intent_config.py`, `domain/intent/` |
| 환경변수 | `INTENT_ANALYZER_*` UPPER_SNAKE | `INTENT_ANALYZER_TIMEOUT_SEC` |

### 10.2 Import Order

```python
# 1. 표준 라이브러리
import asyncio
from typing import Literal

# 2. 외부 라이브러리
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# 3. 내부 절대 임포트 (domain → application → infrastructure 순)
from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.schemas import IntentResult, IntentSpec
from src.domain.logging.interfaces.logger_interface import LoggerInterface
```

### 10.3 Environment Variables

| Variable | Purpose | Scope | Default |
|----------|---------|-------|---------|
| `INTENT_ANALYZER_MODEL` | 판정 LLM 모델 | Server | `gpt-4o-mini` |
| `INTENT_ANALYZER_TEMPERATURE` | 샘플링 온도 | Server | `0.0` |
| `INTENT_ANALYZER_TIMEOUT_SEC` | 판정 타임아웃 | Server | `10.0` |
| `INTENT_ANALYZER_HISTORY_LIMIT` | 프롬프트에 넣을 최근 턴 수 | Server | `6` |
| `OPENAI_API_KEY` | 기존 | Server | — |

### 10.4 This Feature's Conventions

| 항목 | 적용 |
|------|------|
| 함수 길이 | 40줄 이내 (CLAUDE.md §3). `normalize()`는 검증 항목별 private 헬퍼로 분해 |
| if 중첩 | 2단계 이내. early return 우선 |
| 타입 | 전 함수 명시 타입. `Any` 사용 금지 |
| 에러 처리 | 어댑터가 전부 흡수. UseCase·라우터에 try/except 없음 |
| 로깅 | `logger.info` / `logger.error(exception=e)`. `print()` 금지 |
| 트랜잭션 | **해당 없음** — DB 미접근. Repository·세션 주입 금지(Plan R6) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/
│   ├── domain/intent/
│   │   ├── __init__.py
│   │   ├── schemas.py            # Turn, IntentLabel, IntentSpec, IntentResult
│   │   ├── interfaces.py         # IntentAnalyzerInterface
│   │   └── policies.py           # IntentResultPolicy (순수함수)
│   │
│   ├── application/intent/
│   │   ├── __init__.py
│   │   ├── use_case.py           # AnalyzeIntentUseCase
│   │   └── node.py               # create_intent_node()  ← 탈착 이음매
│   │
│   ├── infrastructure/
│   │   ├── intent/
│   │   │   ├── __init__.py
│   │   │   └── adapter.py        # LLMIntentAnalyzerAdapter (_SYSTEM/_HUMAN 내장)
│   │   └── config/
│   │       └── intent_config.py  # IntentConfig
│   │
│   ├── interfaces/schemas/
│   │   └── intent.py             # AnalyzeIntentRequest / Response
│   │
│   └── api/
│       ├── routes/intent_router.py
│       └── main.py               # ★ 유일한 수정 파일 (라우터 등록 + DI)
│
└── tests/
    ├── domain/intent/test_policies.py
    ├── application/intent/test_use_case.py
    ├── application/intent/test_node.py
    ├── infrastructure/intent/test_adapter.py
    └── api/test_intent_router.py

신규 12개 · 수정 1개 · 마이그레이션 0개
```

### 11.2 Implementation Order

TDD: 각 항목마다 **테스트 먼저 → 실패 확인 → 구현 → 통과 확인**.

1. [ ] `domain/intent/schemas.py` — VO 4종 (필드 description 포함, LLM 스키마 겸용)
2. [ ] `domain/intent/interfaces.py` — `IntentAnalyzerInterface`
3. [ ] `tests/domain/intent/test_policies.py` (시나리오 1~9) → `domain/intent/policies.py`
4. [ ] `infrastructure/config/intent_config.py`
5. [ ] `tests/infrastructure/intent/test_adapter.py` (10~15) → `infrastructure/intent/adapter.py`
6. [ ] `tests/application/intent/test_use_case.py` (20~22) → `application/intent/use_case.py`
7. [ ] `tests/application/intent/test_node.py` (16~19) → `application/intent/node.py`
8. [ ] `interfaces/schemas/intent.py`
9. [ ] `tests/api/test_intent_router.py` (L1 1~7) → `api/routes/intent_router.py`
10. [ ] `src/api/main.py` — `include_router` + DI 배선 (추가만)
11. [ ] `.env.example` 갱신 (있는 경우)
12. [ ] 회귀 검증 A1~A7 (§8.4) 실행

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | 내용 | 파일 | 예상 턴 |
|--------|-----------|------|:----:|:------:|
| **도메인 코어** | `module-1` | VO 4종 + 포트 + `IntentResultPolicy` + 단위테스트. LLM 없이 완결되는 순수 계층 | 3 + 테스트 1 | 15-20 |
| **LLM 어댑터** | `module-2` | `IntentConfig` + `LLMIntentAnalyzerAdapter` + 프롬프트 상수 + fake chain 테스트. §4.3 프롬프트 문안 확정 | 3 + 테스트 1 | 20-25 |
| **응용·API 표면** | `module-3` | UseCase + 노드 팩토리 + 라우터 + 스키마 + `main.py` DI + API 테스트 + 회귀 검증 A1~A7 | 5 + 테스트 3 | 25-30 |

의존 순서: `module-1` → `module-2` → `module-3` (역방향 의존 없음).

#### Recommended Session Plan

| Session | Phase | Scope | 예상 턴 |
|---------|-------|-------|:------:|
| Session 1 (완료) | Plan + Design | 전체 | — |
| Session 2 | Do | `--scope module-1,module-2` | 35-45 |
| Session 3 | Do | `--scope module-3` | 25-30 |
| Session 4 | Check + Report | 전체 | 25-35 |

> 규모가 작아 `module-1`+`module-2`를 한 세션에 묶는 것을 권장한다. 단 `module-3`은
> `main.py` 수정과 회귀 검증(A1~A7)이 걸려 있어 별도 세션으로 분리하는 편이 안전하다.

### 11.4 다음 사이클 1차 배선 후보 (Plan R4 · §9 숙제)

이번 사이클은 미배선으로 끝나므로, 후속 사이클의 진입점을 여기서 못 박는다.

**후보: Supervisor 그래프의 pre-node — 단, 2단계로 나눈다.**

| 단계 | 내용 | 목적 |
|:----:|------|------|
| **1단계 — 관측 전용(shadow)** | `intent` 노드를 supervisor **앞에** 두되, 결과를 `state["intent"]`에 기록만 하고 **supervisor 프롬프트에 주입하지 않는다**. 로그로 라벨 분포·`degraded` 비율·지연을 수집. | 실트래픽에서 정확도와 비용을 측정. 프롬프트를 건드리지 않으므로 위키 계약 2 위험 **0** |
| **2단계 — 조언 주입** | 1단계 데이터로 정확도가 납득되면 supervisor 프롬프트에 참고 정보로 주입. | 이 시점에 Plan R2(과차단) 재평가가 **필수 진입 조건** |

**후보 선정 근거**: general_chat은 이미 차트·메모리 배선이 얽혀 있어 변경 표면이 넓고, multi_query는 기존 `MultiQueryPolicy.classify`를 대체하게 되어 검색 품질 회귀 위험을 진다. supervisor pre-node는 state 키 1개만 추가하는 최소 표면이며, 사용자의 원 동기("요청이 들어왔을 때 의도를 분석")와 직결된다.

**1단계 진입 전 확인 사항**: 위키 계약 1(워커 산출물 = `AIMessage(name)` 1건) — intent 노드는 워커가 아니므로 메시지를 생성하지 않아야 한다. `{state_key}` 외 키를 반환하지 않는 §8.2 시나리오 17이 이를 강제한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 초안 — Option C 선택. 프롬프트 문안·모델 등급·필드 확정·인증·1차 배선 후보 4건 확정 | 배상규 |
