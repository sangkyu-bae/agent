---
template: design
version: 1.3
feature: intent-slot-elicitation
plan: docs/01-plan/features/intent-slot-elicitation.plan.md
---

# intent-slot-elicitation Design Document

> **Summary**: `domain/intent`를 "라벨 1개 고르기"에서 "선언된 축(슬롯)을 채우고, 미충족 축을 맥락 기반 추천 선택지와 함께 되묻기"까지 확장한다. 선행 사이클의 `IntentResult = LLM 스키마 겸용` 결정을 **폐기**하고 LLM 출력 스키마를 분리해(Option C), 시스템 계산 필드(`complete`/`missing_slots`/`degraded`)를 LLM이 볼 수 없게 만든다.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규 (tkdrb136@gmail.com)
> **Date**: 2026-08-14
> **Status**: Draft
> **Selected Architecture**: **Option C — 실용적 균형**

### Pipeline References

| 항목 | 위치 |
|------|------|
| Plan | `docs/01-plan/features/intent-slot-elicitation.plan.md` |
| 선행 Design | `docs/archive/2026-08/intent-analyzer/intent-analyzer.design.md` |
| 선행 Design | `docs/archive/2026-08/agent-create-entry/agent-create-entry.design.md` |
| 위키 계약 2 | `docs/wiki/backend/patterns/supervisor-graph-contracts.md` ★ §4.3 근거 |
| 코딩 규칙 | `idt/CLAUDE.md`, `idt/docs/rules/logging.md`, `idt/docs/rules/testing.md` |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 채팅형 에이전트 생성에서 되묻기 질문이 체계 없이 LLM 재량으로 생성되어 재현성이 없고, 파악된 의도가 구조화 객체로 남지 않는다 |
| **WHO** | P2(에이전트 소유자) — 채팅으로 에이전트를 만드는 사람. 1차 소비자는 다음 사이클의 `AgentPlanner`(개발자) |
| **RISK** | ① `slots` 타입 승격은 계약 변경 ② 축 목록 프롬프트가 위키 계약 2(목록 프레이밍 과차단)와 맞닿음 ③ 다중 라운드 왕복이 무한 질문이 될 수 있다 |
| **SUCCESS** | required 축 미충족 시 축별 질문 + 맥락 기반 추천 선택지 생성 · 답변 되먹임 1라운드로 `complete=True` 도달 · LLM 실패 3종 모두 `degraded=True` · 기존 파일 변경은 `intent` 모듈 한정 |
| **SCOPE** | `domain/intent` 확장 + 어댑터/UseCase/API + `agent_composer` 축 프리셋. **AgentPlanner 배선·compose 응답 계약·프론트 = 다음 사이클** |

---

## 1. Overview

### 1.1 Design Goals

1. **되묻기가 재현 가능할 것** — 같은 요청 + 같은 spec이면 같은 축이 미충족으로 나온다. 무엇을 물을지는 LLM의 기분이 아니라 `SlotSpec.required` 의 함수다.
2. **시스템 계산 필드를 LLM에게서 격리할 것** — `complete` / `missing_slots` / `degraded` 는 계산 가능한 사실이지 판단이 아니다. LLM이 접근할 수 없는 곳에 둔다.
3. **모듈은 축의 의미를 계속 모를 것** — `domain/intent` 어디에도 "어조"·"데이터소스" 같은 어휘가 없다. 선행 D3(호출자 주입)의 승계.
4. **왕복은 stateless일 것** — 모듈은 라운드 사이에 아무것도 기억하지 않는다. 상태는 전부 호출 인자(`answers`, `round`)에 있다.
5. **되묻기는 반드시 끝날 것** — 라운드 상한이 곧 LLM 호출 상한이다.

### 1.2 Design Principles

| 원칙 | 적용 |
|------|------|
| LLM 출력을 신뢰하지 않는다 | LLM 스키마와 도메인 VO를 분리. 시스템 필드는 Policy/어댑터만 씀 |
| 판정은 조언이다 | 이 모듈은 아무것도 게이팅하지 않는다. 과차단이 발생해도 라우팅을 막지 못한다 (선행 D5 유지) |
| 실패는 조용히 강등한다 | 예외 대신 `degraded=True`. 확장 필드는 빈 값 (선행 D6 유지) |
| 사람이 LLM을 이긴다 | 같은 축에 사용자 답변이 있으면 LLM 추출값을 덮어쓴다 (Plan D6) |
| 순수함수가 규칙을 갖는다 | 정규화·병합·충족 판정은 IO 없는 함수. 분기 100% 테스트 |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| | A. 최소 변경 | B. 완전 분리 | **C. 실용적 균형 (선택)** |
|---|---|---|---|
| LLM 출력 스키마 | `IntentResult` 겸용 유지 | `_IntentLLMOutput` 분리 | **`_IntentLLMOutput` 분리** |
| LLM이 채우는 것 | 전부 (`complete`·`questions` 포함) | 값 추출 + 선택지만 | **값 추출 + 선택지 + 질문 문안** |
| 질문 문안 | LLM | Policy 템플릿(고정) | **LLM (맥락 반영)** |
| Policy 구조 | 1클래스 6책임 | 2클래스 분리 | **1클래스 + 모듈 순수함수 분할** |
| 신규 파일 | 0 | 2 | **0 (도메인), 1 (프리셋)** |
| LLM 오염 방어 부담 | 높음 (필드 4개) | 없음 | **없음** |
| 선행 결정 뒤집기 | 없음 | 있음 | **부분 (§2.4 Option C 폐기)** |
| 공수 | 소 | 대 | **중** |

**선택 이유 (사용자 확정)**

- Plan D5에서 `complete`를 Policy 계산으로 이미 확정했다. A는 LLM이 채울 수 있는 자리에 그 필드를 두고 매번 무시하는 구조 — 선행 사이클이 `degraded` 하나 때문에 쌓은 3층 방어를 4번 반복하게 된다.
- B의 템플릿 질문은 안전하지만 Plan D3("LLM이 요청 맥락에 맞춰 동적 생성")의 취지와 어긋난다. "데이터 분석 에이전트"와 "문서 QA 에이전트"에 같은 문안이 나가면 되묻기 품질이 떨어진다.

### 2.1 Component Diagram

```
┌─ interfaces ──────────────────────────────────────────────┐
│ api/routes/intent_router.py                               │
│   POST /api/v1/intent/analyze                             │
│ interfaces/schemas/intent.py                              │
│   AnalyzeIntentRequest(message, spec, history,            │
│                        answers, round)          ★확장     │
│   AnalyzeIntentResponse = IntentResult                    │
└───────────────────────┬───────────────────────────────────┘
                        ▼
┌─ application ─────────────────────────────────────────────┐
│ application/intent/use_case.py                            │
│   AnalyzeIntentUseCase.execute(..., answers, round) ★확장 │
│ application/intent/node.py                                │
│   create_intent_node()  — 계약 유지, answers 미노출        │
│                                                           │
│ application/agent_composer/build_slots.py         ★신규   │
│   AGENT_BUILD_SLOTS = [tone, task, domain_detail,         │
│                        data_source, output_format]        │
│   └ 이번 사이클엔 정의만. 소비 = 다음 사이클               │
└───────────────────────┬───────────────────────────────────┘
                        ▼ (포트)
┌─ domain/intent ───── 외부 의존 = pydantic 뿐 ─────────────┐
│ schemas.py                                                │
│   Turn, IntentLabel                        (기존)         │
│   SlotSpec, SlotQuestion, SlotAnswer       ★신규          │
│   IntentSpec(labels, slots: list[SlotSpec]) ★타입 승격    │
│   IntentResult(+filled_slots, +suggestions,               │
│                +questions, +complete,                     │
│                −entities)                   ★확장/제거    │
│ interfaces.py                                             │
│   IntentAnalyzerInterface.analyze(..., answers, round)    │
│ policies.py                                               │
│   IntentResultPolicy.normalize(llm_out, spec, answers,    │
│                                round, config)             │
│   + _merge_answers / _resolve_missing / _resolve_complete │
│   + _filter_questions / _clamp_options                    │
└───────────────────────▲───────────────────────────────────┘
                        │ (구현)
┌─ infrastructure ──────┴───────────────────────────────────┐
│ infrastructure/intent/adapter.py                          │
│   _IntentLLMOutput  ★신규 — LLM이 보는 유일한 스키마      │
│   _slots_block / _answers_block / _round_block  ★신규     │
│   LLMIntentAnalyzerAdapter.analyze(...)                   │
│ infrastructure/config/intent_config.py                    │
│   +MAX_CLARIFICATION_ROUNDS/QUESTIONS/OPTIONS  ★확장      │
└───────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**라운드 0 — 최초 판정**

```
호출자 ──▶ analyze(message="데이터 분석해주는 에이전트 만들어줘",
                   spec=IntentSpec(labels=[], slots=AGENT_BUILD_SLOTS),
                   answers=None, round=0)
   │
   ├─ 어댑터: _build_payload()
   │    labels_block  = "(없음)"            ← labels 비었으면 분류 지시 생략
   │    slots_block   = 5축 key/description/options 힌트
   │    answers_block = "(없음)"
   │    round_block   = "" (여유 있음)
   │
   ├─ LLM ──▶ _IntentLLMOutput(
   │            label=None, confidence=0.0,
   │            filled_slots={"task":"데이터 분석"},
   │            suggestions={"data_source":["엑셀 업로드","DB 연결","지식베이스"],
   │                         "tone":["간결한 실무형","친근한 설명형"], ...},
   │            questions=[{slot_key:"data_source",
   │                        question:"분석할 데이터는 어디에 있나요?", ...}, ...])
   │
   └─ Policy.normalize(llm_out, spec, answers=None, round=0, config)
        ① filled_slots: spec에 없는 키 제거 + 빈 문자열 제거
        ② answers 병합 (없음)
        ③ missing_slots = spec.slots − filled_slots        ← 계산
        ④ questions: 이미 채워진 축 제거 → 상한 3개 clamp
        ⑤ suggestions: 축당 상한 4개 clamp + 미지 키 제거
        ⑥ complete = (required 축 ⊆ filled_slots)          ← 계산
                                                             ▼
   IntentResult(filled_slots={"task":...}, missing_slots=[4개],
                questions=[3개], complete=False, degraded=False)
```

**라운드 1 — 답변 되먹임 (stateless)**

```
호출자 ──▶ analyze(message=<동일>, spec=<동일>,
                   answers=[SlotAnswer(slot_key="data_source", value="엑셀 업로드"),
                            SlotAnswer(slot_key="tone",        value="간결한 실무형")],
                   round=1)
   │
   ├─ answers_block = "- data_source: 엑셀 업로드\n- tone: 간결한 실무형"
   │   (모듈은 라운드 0을 기억하지 않는다 — 전부 인자에서 온다)
   │
   └─ Policy.normalize(...)
        ② answers 병합 — **LLM 추출값보다 우선** (Plan D6)
        ⑥ required 축 전부 충족 → complete=True
                                                             ▼
   IntentResult(filled_slots={5축 전부}, missing_slots=[],
                questions=[], complete=True)
```

**라운드 상한 도달**

```
round >= MAX(=2) ──▶ Policy가 questions=[] 강제
                     complete는 사실 그대로 False일 수 있다
                     └ 호출자는 "더 물을 수 없음, 기본값 가정"으로 읽는다
```

### 2.3 Dependencies

| 방향 | 허용 | 비고 |
|------|:----:|------|
| `domain/intent` → 외부 | pydantic만 | LangChain·DB·HTTP·`agent_composer` 전부 금지 |
| `application/intent` → `domain/intent` | ✅ | 포트·VO만 |
| `application/agent_composer/build_slots` → `domain/intent` | ✅ | `SlotSpec` import (단방향) |
| `domain/intent` → `agent_composer` | ❌ | **역참조 금지** — 축의 의미가 코어로 침투하는 경로 |
| `infrastructure/intent` → `domain/intent` | ✅ | 포트 구현 |

### 2.4 선택의 명시적 대가 — 선행 §2.4 결정의 폐기

선행 사이클은 `IntentResult`를 LLM `with_structured_output` 스키마로 **겸용**했다(선행 Design §2.4 Option C). 그 대가로 `degraded` 오염을 3층(스키마 description / Policy 무시 / 어댑터 결정)으로 방어했다.

본 사이클은 그 결정을 **폐기**한다. 이유:

- 시스템 계산 필드가 1개(`degraded`)에서 3개(`+complete`, `+missing_slots`)로 늘어난다. 방어 코드가 필드 수에 비례해 늘어나는 구조는 확장에 실패한다.
- `questions`는 LLM이 채우되 **필터링 대상**이다 — LLM이 이미 채워진 축을 물어도 Policy가 버린다. 겸용 스키마에서는 "LLM이 채워도 되는 필드"와 "채우면 안 되는 필드"가 한 클래스에 섞여 독자가 구분할 수 없다.

**대가**: 어댑터의 `_coerce()`가 `IntentResult` 대신 `_IntentLLMOutput`을 검증하도록 재작성된다. `IntentResult`는 더 이상 LLM 스키마가 아니므로 각 필드 `description`의 "LLM 지시문" 역할이 `_IntentLLMOutput`으로 이관된다.

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/intent/schemas.py — 외부 의존은 pydantic 뿐

class Turn(BaseModel):                                  # 기존, 무변경
    role: Literal["user", "assistant"]
    content: str


class IntentLabel(BaseModel):                           # 기존, 무변경
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class SlotSpec(BaseModel):                              # ★신규
    """호출자가 선언하는 '물어볼 축' 1개.

    모듈은 key 의 의미를 모른다. description 이 곧 프롬프트 품질이다.
    """
    key: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1, description="이 축이 무엇인지")
    options: list[str] = Field(
        default_factory=list,
        description="선택지 힌트. 고정 목록이 아니라 LLM 앵커링용 예시다.",
    )
    allow_free_text: bool = True
    required: bool = False


class SlotAnswer(BaseModel):                            # ★신규
    """사용자가 되묻기에 답한 값. 왕복은 stateless — 요청에 에코백된다."""
    slot_key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class SlotQuestion(BaseModel):                          # ★신규
    """미충족 축 1개에 대한 되묻기."""
    slot_key: str
    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class IntentSpec(BaseModel):
    labels: list[IntentLabel] = Field(default_factory=list)   # ★min_length=2 해제
    slots: list[SlotSpec] = Field(default_factory=list)       # ★list[str] → list[SlotSpec]
    allow_unknown: bool = True

    @field_validator("slots", mode="before")
    @classmethod
    def _promote_str_slots(cls, v):
        """구형 list[str] 입력을 SlotSpec 으로 자동 승격 (Plan FR-02).

        입력 하위호환만 보장한다 — 읽을 때의 타입은 SlotSpec 이다.
        """
        if isinstance(v, list):
            return [
                {"key": s, "description": s} if isinstance(s, str) else s
                for s in v
            ]
        return v

    @model_validator(mode="after")
    def _require_labels_or_slots(self):
        """labels 또는 slots 중 하나는 있어야 한다 (사용자 확정 / FR-16).

        - 분류만: labels ≥ 2
        - 슬롯만: slots ≥ 1        ← 에이전트 생성이 쓰는 형태
        - 둘 다:  위 두 조건 동시
        labels 가 1개인 경우는 분류가 성립하지 않으므로 거부한다.
        """
        if len(self.labels) == 1:
            raise ValueError("labels must be empty or have at least 2 entries")
        if not self.labels and not self.slots:
            raise ValueError("either labels or slots must be provided")
        return self


class IntentResult(BaseModel):
    """판정 결과 — **더 이상 LLM 출력 스키마가 아니다** (§2.4).

    LLM 이 채우는 값과 시스템이 계산한 값이 합쳐진 최종 도메인 VO.
    """
    # LLM 이 채우는 값
    label: str | None = None
    confidence: float = 0.0
    ambiguous: bool = False
    reason: str = ""
    filled_slots: dict[str, str] = Field(default_factory=dict)   # ★entities 대체
    suggestions: dict[str, list[str]] = Field(default_factory=dict)  # ★신규
    questions: list[SlotQuestion] = Field(default_factory=list)      # ★신규
    # 시스템이 계산하는 값 — LLM 은 이 필드들을 볼 수 없다
    missing_slots: list[str] = Field(default_factory=list)
    complete: bool = False                                            # ★신규
    degraded: bool = False
```

> ⚠️ **구현이 이 설계를 두 번 이탈했다. 코드가 진실이다** (SoT 규칙).
> 아래 블록은 **최종 구현 기준으로 갱신된 내용**이다. 원안과 이탈 사유는 §3.1.1 참조.

```python
# src/domain/intent/schemas.py — LLM 이 보는 유일한 스키마

class SlotQuestionDraft(BaseModel):
    slot_key: str = Field(description="질문 대상 축의 key. 후보 축 목록에 있는 것만.")
    question: str = Field(description="사용자에게 물을 한국어 한 문장")
    options: list[str] = Field(
        default_factory=list, description="이 축의 추천 선택지 2~4개"
    )


class SlotValue(BaseModel):        # dict 를 못 쓰는 이유는 §3.1.1 이탈 2
    key: str
    value: str


class SlotSuggestion(BaseModel):
    key: str
    options: list[str] = Field(default_factory=list)


class IntentDraft(BaseModel):
    """`with_structured_output` 대상. 시스템 계산 필드는 **여기에 없다**."""
    label: str | None = Field(None, description="가장 잘 맞는 후보 의도의 name. 없으면 비워 두세요.")
    confidence: float = Field(0.0, description="0.0~1.0 사이의 확신도")
    ambiguous: bool = Field(False, description="후보가 둘 이상으로 갈리면 true")
    reason: str = Field("", description="판단 근거(짧게)")
    filled_slots: list[SlotValue] = Field(
        default_factory=list, description="메시지에서 확실히 알 수 있는 축만 채우세요. 추측하지 마세요."
    )
    suggestions: list[SlotSuggestion] = Field(
        default_factory=list, description="채우지 못한 축별 추천 선택지. 이 요청 맥락에 맞게 만드세요."
    )
    questions: list[SlotQuestionDraft] = Field(
        default_factory=list, description="채우지 못한 축에 대한 되묻기"
    )
    # dict 로 오는 구현체도 수용하는 mode="before" validator 2개 (입력 관용).
    # 출력 스키마는 언제나 배열이므로 strict 호환성이 되돌아가지 않는다.
```

#### 3.1.1 원안 대비 이탈 2건

| # | 원안 | 최종 | 사유 |
|---|------|------|------|
| **1** | `_IntentLLMOutput` / `_SlotQuestionOut` 을 `infrastructure/intent/adapter.py` 에 모듈 프라이빗으로 | `IntentDraft` / `SlotQuestionDraft` 를 **`domain/intent/schemas.py`** 에 공개 VO 로 | 원안대로면 domain 의 `IntentResultPolicy.normalize()` 가 infrastructure 타입을 인자로 받아 **의존 방향이 뒤집힌다**. LLM 채움 필드만 가진 도메인 VO 로 두면 §2.4 의 목적(시스템 필드 격리)을 동일하게 달성하면서 레이어를 지킨다. 부수 이득으로 `allow_free_text` 를 LLM 이 아니라 `SlotSpec` 에서 채우게 되어 불변식이 1개 늘었다 |
| **2** | `filled_slots: dict[str,str]`, `suggestions: dict[str,list[str]]` | `list[SlotValue]`, `list[SlotSuggestion]` | **실 LLM 검증(Analysis §10.1)에서 발견** — OpenAI structured outputs 의 strict 모드가 자유 키 dict 를 거부해 `400 BadRequest` 가 나고 판정이 **항상 `degraded`** 로 떨어졌다. 선행 사이클의 `IntentResult(entities: dict)` 도 같은 이유로 깨져 있었다. **도메인 VO(`IntentResult`)와 API 응답은 dict 를 유지**하며, Policy 가 배열→dict 로 접는다 |

> 이탈 2 는 이탈 1 덕분에 값싸게 고칠 수 있었다. LLM 스키마와 도메인 VO 가 한 클래스였다면
> API 계약과 라우터 테스트 30건까지 번졌을 것이다.

### 3.2 Entity Relationships

```
IntentSpec ─┬─ labels: [IntentLabel]     (분류 체계, 선택)
            └─ slots:  [SlotSpec]        (물어볼 축, 선택)
                          │
                          │ key 로 연결
                          ▼
IntentResult ─┬─ filled_slots: {key: value}     ← 채워진 축
              ├─ missing_slots: [key]           ← 못 채운 축 (계산)
              ├─ suggestions:  {key: [option]}  ← 축별 추천
              ├─ questions:    [SlotQuestion]   ← 미충족 축 되묻기
              └─ complete: bool                 ← required ⊆ filled (계산)
                          ▲
                          │ slot_key 로 병합 (사용자 우선)
SlotAnswer ───────────────┘
```

**불변식** — Policy가 보장한다.

| # | 불변식 |
|---|--------|
| I1 | `filled_slots.keys() ⊆ {s.key for s in spec.slots}` |
| I2 | `missing_slots = [s.key for s in spec.slots if s.key not in filled_slots]` |
| I3 | `questions` 의 `slot_key` 는 전부 `missing_slots` 에 있다 |
| I4 | `complete == all(s.key in filled_slots for s in spec.slots if s.required)` |
| I5 | `round >= MAX_ROUNDS` → `questions == []` |
| I6 | `degraded == True` → 확장 필드 전부 빈 값, `complete == False` |
| I7 | 빈 문자열(`""`) 값은 `filled_slots` 에 들어가지 않는다 (미충족으로 취급) |

### 3.3 Database Schema

**없음.** 마이그레이션 0건. 왕복 상태는 요청 에코백으로만 복원한다 (Plan D4).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | 인증 | 변경 |
|--------|------|:----:|------|
| POST | `/api/v1/intent/analyze` | 필수 | **확장** (신규 엔드포인트 없음) |

### 4.2 Detailed Specification

**Request**

```jsonc
{
  "message": "데이터 분석해주는 에이전트 만들어줘",
  "spec": {
    "labels": [],                          // 슬롯 전용 사용 — 이제 허용
    "slots": [
      {
        "key": "data_source",
        "description": "분석할 데이터가 어디에 있는지",
        "options": ["엑셀 업로드", "DB 연결", "지식베이스"],
        "allow_free_text": true,
        "required": true
      }
    ],
    "allow_unknown": true
  },
  "history": null,
  "answers": [                             // ★신규 — 라운드 1 이상에서
    { "slot_key": "tone", "value": "간결한 실무형" }
  ],
  "round": 1                               // ★신규 — 서버가 clamp
}
```

**Response 200**

```jsonc
{
  "label": null,
  "confidence": 0.0,
  "ambiguous": false,
  "reason": "에이전트 생성 요청으로 판단",
  "filled_slots": { "task": "데이터 분석", "tone": "간결한 실무형" },
  "suggestions": { "data_source": ["엑셀 업로드", "DB 연결", "지식베이스"] },
  "questions": [
    {
      "slot_key": "data_source",
      "question": "분석할 데이터는 어디에 있나요?",
      "options": ["엑셀 업로드", "DB 연결", "지식베이스"],
      "allow_free_text": true
    }
  ],
  "missing_slots": ["data_source", "domain_detail", "output_format"],
  "complete": false,
  "degraded": false
}
```

**상태 코드**

| 코드 | 조건 |
|------|------|
| 200 | 판정 성공. **`degraded=true` 도 200** — 에러가 아니라 '의도 모름' |
| 401 | 인증 실패 (`get_current_user`) |
| 422 | `labels` 가 1개 / `labels`·`slots` 둘 다 비어 있음 / `SlotSpec.description` 누락 / `message` 빈 문자열 / `round` 음수 |

**Breaking Change 고지**

| 항목 | 이전 | 이후 | 대응 |
|------|------|------|------|
| 요청 `spec.slots` | `["기간"]` | `[{key,description,...}]` | 구형 입력도 validator로 승격 수용 |
| 응답 `entities` | 존재 | **제거** | `filled_slots` 로 개명 (사용자 확정). 소비자 0이므로 별칭 없음 |
| 요청 `spec.labels` | 필수 ≥2 | 선택 (0 또는 ≥2) | 완화 방향이라 기존 호출 무영향 |

### 4.3 프롬프트 설계 (Plan R2 완화 — 본 설계의 핵심)

위키 계약 2(목록 프레이밍 과차단, 커밋 08d37cab)는 "할 수 있는 것 목록"을 프롬프트에 주면 목록 밖 요청을 과차단한다는 **실장애 선례**다. 축 목록 + 선택지 목록은 구조가 같다. 방어는 4겹이다.

1. **구조적 방어(1차)** — 이 모듈은 아무것도 게이팅하지 않는다. 판정은 조언이며 라우팅 권한이 없다.
2. **프레이밍 방어(2차)** — 목록을 "권한"이 아니라 "빈칸 채우기 양식"으로 제시한다.
3. **탈출구 방어(3차)** — `allow_free_text` 기본 `True`. 선택지는 항상 "예시"로 명시.
4. **권한 방어(4차)** — 사용자 답변이 LLM 추출값을 이긴다 (I2/Policy 병합 순서).

```python
_SYSTEM = (
    "당신은 사용자 메시지에서 정보를 추출하고, 부족한 정보를 되묻는 분석기입니다. "
    "요청을 수행하지도, 거절하지도, 평가하지도 않습니다.\n\n"
    "{labels_block}"                       # labels 비면 통째로 생략
    "[채워야 할 항목]\n{slots_block}\n\n"
    "규칙:\n"
    "- 메시지에서 **확실히 알 수 있는 항목만** filled_slots 에 채우세요. "
    "추측하거나 지어내지 마세요.\n"
    "- 채우지 못한 항목은 suggestions 에 이 요청에 어울리는 선택지 "
    "2~{max_options}개를 만들고, questions 에 물을 문장을 쓰세요.\n"
    "- 아래 '예시' 는 참고일 뿐입니다. 요청에 더 맞는 선택지가 있으면 "
    "예시를 무시하고 새로 만드세요.\n"
    "- 이 항목 목록은 **빈칸 채우기 양식**이지 허용 범위가 아닙니다. "
    "목록에 없는 주제의 요청도 정상적인 요청입니다.\n"
    "- 사용자가 자유롭게 답할 수 있으므로 선택지는 강제가 아닙니다.\n"
    "{answers_block}{round_block}"
)
_HUMAN = "[이전 대화]\n{history_block}\n\n[현재 메시지]\n{message}"
```

**블록 렌더링**

| 블록 | 조건 | 내용 |
|------|------|------|
| `labels_block` | `spec.labels` 비면 **""** | 기존 분류 지시문 + 후보 목록 (선행 사이클 문안 유지) |
| `slots_block` | 항상 | `- {key}: {description}` + `options` 있으면 `(예: a, b, c)` **+ `required` 면 `[필수]`** |
| `answers_block` | `answers` 있을 때 | `[사용자가 이미 답한 항목]\n- {key}: {value}\n이 값은 확정입니다. 다시 묻지 마세요.` |
| `round_block` | `round >= MAX-1` 일 때 | `- 마지막 라운드입니다. 되묻기보다 지금까지의 정보로 최대한 채우세요.` |

> `round_block`은 **소프트 신호**다. 하드 차단은 Policy(I5)가 한다 — 프롬프트만 믿지 않는다.

### 4.4 모델 · 설정

```python
# src/infrastructure/config/intent_config.py
class IntentConfig(BaseSettings):
    INTENT_ANALYZER_MODEL: str = "gpt-4o-mini"          # 기존
    INTENT_ANALYZER_TEMPERATURE: float = 0.0            # 기존
    INTENT_ANALYZER_TIMEOUT_SEC: float = 10.0           # 기존
    INTENT_ANALYZER_HISTORY_LIMIT: int = 6              # 기존
    INTENT_MAX_CLARIFICATION_ROUNDS: int = 2            # ★신규 (PlannerPolicy 정합)
    INTENT_MAX_QUESTIONS_PER_ROUND: int = 3             # ★신규 (PlannerPolicy 정합)
    INTENT_MAX_OPTIONS_PER_SLOT: int = 4                # ★신규
```

`temperature=0.0` 유지에 대한 판단: 선택지 생성에 다양성이 필요해 보이지만, **되묻기의 재현성이 이 기능의 존재 이유**(§1.1-1)다. 같은 요청에 같은 질문이 나오는 편이 낫다.

**상한 상수의 출처가 두 곳인 이유** — `PlannerPolicy`는 클래스 상수, intent는 env다. `agent_composer`의 상한은 도메인 정책(질문을 몇 개까지 하는 게 옳은가)이고, intent의 상한은 **호출자마다 다를 수 있는 운영값**이다. 기본값만 일치시켜 두 모듈이 붙었을 때 놀라지 않게 한다.

### 4.5 `AGENT_BUILD_SLOTS` 프리셋 (Plan FR-13)

```python
# src/application/agent_composer/build_slots.py — 정의만, 소비는 다음 사이클
AGENT_BUILD_SLOTS: list[SlotSpec] = [
    SlotSpec(
        key="task", required=True,
        description="이 에이전트가 사용자를 위해 해 줄 일",
        options=["데이터 분석", "문서 질의응답", "보고서 작성", "정보 검색"],
    ),
    SlotSpec(
        key="domain_detail", required=True,
        description="그 일을 구체적으로 어떤 범위·방식으로 하는지",
        options=["요약 통계", "추세 분석", "이상 탐지", "비교 분석"],
    ),
    SlotSpec(
        key="data_source", required=True,
        description="에이전트가 다룰 데이터가 어디에 있는지",
        options=["엑셀/CSV 업로드", "지식베이스(KB)", "웹 검색", "DB 연결"],
    ),
    SlotSpec(
        key="output_format", required=False,
        description="결과를 어떤 형태로 받고 싶은지",
        options=["텍스트 요약", "표", "차트", "다운로드 파일"],
    ),
    SlotSpec(
        key="tone", required=False,
        description="답변할 때의 어조와 대상 독자",
        options=["간결한 실무형", "친근한 설명형", "격식 있는 보고형"],
    ),
]
```

**`required` 배분 근거**: 앞 3축은 없으면 초안을 만들 수 없다(도구·프롬프트가 결정 불가). 뒤 2축은 합리적 기본값이 존재한다 — 되묻기 예산(라운드 2 × 질문 3)을 앞 3축에 몰아준다.

---

## 5. UI/UX Design

**해당 없음.** 이번 사이클은 백엔드 모듈 + 독립 API까지다 (Plan D8). 화면단은 사용자가 별도 재작업 예정이며, `idt_front/` 변경 0건이 성공 기준이다.

다만 다음 사이클 화면이 소비할 계약을 여기서 고정해 둔다 — `questions[]`는 그대로 카드 렌더에 쓸 수 있는 형태(`question` + `options` + `allow_free_text`)이며, 기존 `ClarifyQuestionCard`의 props 구조와 동형이다.

---

## 6. Error Handling

### 6.1 오류 분류 및 처리

| # | 상황 | 처리 | 로그 레벨 |
|---|------|------|:---------:|
| E1 | LLM 예외 (API 오류, 네트워크) | `degraded()` 반환 | `error` + `exception=e` |
| E2 | LLM 타임아웃 | `degraded()` 반환 | `warning` + `exception=e` |
| E3 | 스키마 위반 (`_IntentLLMOutput` 검증 실패) | `degraded()` 반환 | `error` + `exception=e` |
| E4 | LLM이 spec에 없는 슬롯 키 반환 | 조용히 제거 (I1) | 없음 (정상 정규화) |
| E5 | LLM이 이미 채워진 축을 질문 | 조용히 제거 (I3) | 없음 |
| E6 | LLM이 빈 문자열 슬롯 값 반환 | 미충족으로 취급 (I7) | 없음 |
| E7 | `answers`에 spec 밖 `slot_key` | 조용히 무시 | 없음 |
| E8 | 라운드 상한 초과 | `questions=[]` 강제 (I5) | `info` (`round_capped=true`) |
| E9 | spec 검증 실패 | pydantic → 422 | FastAPI 기본 |

**`degraded()` 의 확장 필드** — 전부 빈 값이고 `complete=False`다 (I6). 호출자는 "의도 모름 = 기존대로"로 읽는다.

### 6.2 Error Response Format

기존 유지. `degraded=true`는 **200**이며 에러 바디를 쓰지 않는다.

### 6.3 로깅 규약

```python
# 성공
logger.info("intent analyzed", request_id=..., label=..., confidence=...,
            ambiguous=..., degraded=False, latency_ms=...,
            filled_count=len(result.filled_slots),      # ★신규
            missing_count=len(result.missing_slots),    # ★신규
            question_count=len(result.questions),       # ★신규
            complete=result.complete,                   # ★신규
            round=round_)                               # ★신규

# 폴백
logger.error("intent analysis error, fallback=degraded",
             exception=e, request_id=..., latency_ms=...)
```

**슬롯 값 자체는 로그에 남기지 않는다** — 사용자 입력이며 PII가 섞일 수 있다. 개수만 남긴다.

---

## 7. Security Considerations

| 항목 | 처리 |
|------|------|
| 인증 | 기존 `get_current_user` 유지. 비인증 401 |
| 프롬프트 인젝션 | `slots_block`은 **호출자가 선언한 spec**에서만 온다. 사용자 메시지는 `_HUMAN`에만 들어가 지시문과 분리 |
| `answers` 신뢰 | 클라이언트가 보내는 값이지만 **에코백 설계상 조작해도 자기 요청의 슬롯 값만 바뀐다**. 권한 상승 경로 없음 |
| `round` 신뢰 | 클라이언트 신고값을 서버가 clamp (`PlannerPolicy.clamp_round` 선례) |
| PII | 슬롯 값 미로깅 (§6.3). DB 저장 없음 |
| 비용 | 라운드 상한 = LLM 호출 상한. hot path 미배선이라 이번 사이클 실사용 비용 0 |

---

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 대상 | 도구 |
|------|------|------|
| L0 | `IntentResultPolicy` 순수함수 — **분기 100%** | pytest |
| L0 | `IntentSpec` validator (승격·labels/slots 조건) | pytest |
| L0 | `LLMIntentAnalyzerAdapter` — fake chain 주입 | pytest |
| L0 | `AnalyzeIntentUseCase` — fake analyzer | pytest |
| L0 | `AGENT_BUILD_SLOTS` 프리셋 무결성 | pytest |
| L1 | `POST /api/v1/intent/analyze` | FastAPI TestClient |
| — | 아키텍처 회귀 | `/verify-architecture` + grep |

### 8.2 L0: 단위 테스트 시나리오

**Policy — 슬롯 정규화**

| # | 시나리오 | 기대 |
|---|----------|------|
| S1 | LLM이 spec 밖 슬롯 키 반환 | `filled_slots`에서 제거 (I1) |
| S2 | LLM이 빈 문자열 값 반환 | `filled_slots` 미포함, `missing_slots` 포함 (I7) |
| S3 | `missing_slots` 계산 | `spec.slots − filled_slots` 정확히 일치 (I2) |
| S4 | `suggestions` 미지 키 | 제거 |
| S5 | `suggestions` 축당 5개 반환 | 상한 4개로 clamp |
| S6 | `questions` 가 이미 채워진 축을 물음 | 제거 (I3) |
| S7 | `questions` 4개 반환 | 상한 3개로 clamp |

**Policy — 답변 병합 (Plan D6)**

| # | 시나리오 | 기대 |
|---|----------|------|
| S8 | `answers`에만 값 존재 | `filled_slots`에 반영 |
| S9 | `answers`와 LLM 값 충돌 | **`answers` 승리** |
| S10 | `answers`에 spec 밖 `slot_key` | 무시 (E7) |
| S11 | `answers` 값이 빈 문자열 | 미충족 취급 (I7) |

**Policy — 충족·라운드**

| # | 시나리오 | 기대 |
|---|----------|------|
| S12 | required 전부 충족, optional 미충족 | `complete=True` (I4) |
| S13 | required 1개 미충족 | `complete=False` |
| S14 | `spec.slots` 에 required 없음 | `complete=True` (공집합 참) |
| S15 | `round >= MAX` | `questions == []` (I5) |
| S16 | `round == MAX-1` | 질문 생성 정상 |
| S17 | `degraded()` 결과 | 확장 필드 전부 빈 값, `complete=False` (I6) |

**스키마 validator**

| # | 시나리오 | 기대 |
|---|----------|------|
| S18 | `slots=["기간"]` (구형) | `[SlotSpec(key="기간", description="기간")]` 승격 |
| S19 | `slots=[SlotSpec(...)]` (신형) | 그대로 |
| S20 | `labels=[]`, `slots=[1개]` | 통과 (슬롯 전용) |
| S21 | `labels=[2개]`, `slots=[]` | 통과 (분류 전용) |
| S22 | `labels=[1개]` | `ValidationError` |
| S23 | `labels=[]`, `slots=[]` | `ValidationError` |
| S24 | `SlotSpec.description=""` | `ValidationError` |

**어댑터**

| # | 시나리오 | 기대 |
|---|----------|------|
| S25 | 예외 | `degraded=True` (E1) |
| S26 | 타임아웃 | `degraded=True`, `warning` 로그 (E2) |
| S27 | 스키마 위반 dict | `degraded=True` (E3) |
| S28 | `labels=[]` | 프롬프트에 `labels_block` 미포함 |
| S29 | `answers` 전달 | 프롬프트에 `[사용자가 이미 답한 항목]` 포함 |
| S30 | `round >= MAX-1` | 프롬프트에 마지막 라운드 문구 포함 |
| S31 | 성공 로그 | `filled_count`/`missing_count`/`question_count`/`complete`/`round` 포함, **슬롯 값 미포함** |

**프리셋**

| # | 시나리오 | 기대 |
|---|----------|------|
| S32 | `AGENT_BUILD_SLOTS` | key 중복 없음, `description` 전부 비어있지 않음, `required` 3개 |

### 8.3 L1: API 테스트 시나리오

| # | 요청 | 기대 |
|---|------|------|
| S33 | 정상 (슬롯 전용, `labels=[]`) | 200, `filled_slots`/`questions`/`complete` 존재 |
| S34 | `answers` + `round=1` | 200, 답변이 `filled_slots`에 반영 |
| S35 | 미인증 | 401 |
| S36 | `labels=[1개]` | 422 |
| S37 | `labels=[]`, `slots=[]` | 422 |
| S38 | `message=""` | 422 |
| S39 | `round=-1` | 422 |
| S40 | 어댑터 degraded | **200** + `degraded=true` |
| S41 | 응답 바디 | `entities` 키 **부재** 확인 (제거 검증) |

### 8.4 아키텍처 회귀 테스트 (Plan 성공 기준 직결)

| # | 검증 | 방법 |
|---|------|------|
| A1 | `domain/intent`에 도메인 어휘 0건 | `grep -rniE "어조\|tone\|데이터소스\|data_source\|에이전트" src/domain/intent/` → 0 |
| A2 | `domain/intent` → infrastructure/LangChain import 0건 | `/verify-architecture` |
| A3 | `domain/intent` → `agent_composer` 역참조 0건 | `grep -rn "agent_composer" src/domain/intent/` → 0 |
| A4 | `planner.py` / `compose_agent_use_case.py` 무변경 | `git diff --name-only` |
| A5 | `db/migration/` 신규 0건 | `git status` |
| A6 | `idt_front/` 변경 0건 | `git diff --stat idt_front/` |

### 8.5 Seed Data Requirements

없음. 모든 테스트는 fake chain / fake analyzer 주입으로 LLM 없이 돈다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
interfaces  → application → domain ← infrastructure
                                ▲
              agent_composer ────┘  (SlotSpec 단방향 import)
```

### 9.2 Dependency Rules

| 규칙 | 상태 |
|------|:----:|
| `domain`은 아무것도 향하지 않는다 (pydantic 제외) | ✅ |
| `application`은 `domain` 포트에만 의존 | ✅ |
| `infrastructure`가 `domain` 포트를 구현 | ✅ |
| `agent_composer` → `domain/intent` (프리셋이 `SlotSpec` 사용) | ✅ 단방향 |
| `domain/intent` → `agent_composer` | ❌ **금지** (A3로 검증) |

### 9.3 File Import Rules

> ⚠️ **§3.1.1 이탈 1로 원안이 무효화됐다.** 원안은 `_IntentLLMOutput` 을 어댑터 모듈
> 프라이빗(언더스코어 접두 + `__all__` 미노출)으로 막는 규칙이었으나, 그 클래스가
> domain 의 공개 VO `IntentDraft` 가 되면서 적용 대상을 잃었다.

**대체 규칙**: LLM 이 채우는 필드와 시스템이 계산하는 필드를 **타입으로 분리**한다.

| 타입 | 채우는 주체 | 노출 |
|------|-------------|------|
| `IntentDraft` (+ `SlotValue`/`SlotSuggestion`/`SlotQuestionDraft`) | LLM | domain 공개 — 어댑터가 `with_structured_output` 대상으로, Policy 가 인자로 쓴다 |
| `IntentResult` 의 `missing_slots`/`complete`/`degraded` | Policy·어댑터 | LLM 스키마에 **존재하지 않음** |

접근 제어가 아니라 **타입 분리**가 방어선이다 — LLM 이 시스템 필드를 오염시킬 경로가
구조적으로 없다. `IntentDraft` 를 다른 레이어가 import 하는 것은 정상이다.

**추가 제약 (실 LLM 검증에서 도출)**: `IntentDraft` 와 그 하위 타입에 **자유 키
`dict[str, X]` 를 두지 않는다.** OpenAI structured outputs 의 strict 모드가 이를 거부한다.
`tests/domain/intent/test_schemas.py::test_intent_draft_schema_has_no_free_key_dict` 가
스키마를 재귀 탐색해 강제한다.

### 9.4 This Feature's Layer Assignment

| 파일 | 레이어 | 성격 |
|------|--------|------|
| `domain/intent/schemas.py` | domain | 확장 (VO 3개 신설, 2개 변경) |
| `domain/intent/policies.py` | domain | 확장 (순수함수 5개 추가) |
| `domain/intent/interfaces.py` | domain | 확장 (인자 2개 추가) |
| `application/intent/use_case.py` | application | 확장 (인자 전달) |
| `application/intent/node.py` | application | **무변경** (노드는 `answers`를 쓰지 않는다) |
| `application/agent_composer/build_slots.py` | application | **신규** (순수 데이터) |
| `infrastructure/intent/adapter.py` | infrastructure | 확장 (LLM 스키마 분리 + 블록 3종) |
| `infrastructure/config/intent_config.py` | infrastructure | 확장 (env 3개) |
| `interfaces/schemas/intent.py` | interfaces | 확장 (요청 필드 2개) |
| `api/routes/intent_router.py` | interfaces | 확장 (인자 전달) |

> **`node.py` 무변경 근거**: LangGraph state에는 되묻기 왕복이 없다(그래프는 사람을 기다리지 않는다). 노드는 라운드 0 판정만 하며, HITL은 API 소비자의 책임이다.

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예 |
|------|------|-----|
| VO | PascalCase, 접미사 없음 | `SlotSpec`, `SlotAnswer` |
| LLM 출력 스키마 | 언더스코어 접두 (모듈 프라이빗) | `_IntentLLMOutput` |
| Policy 순수함수 | 모듈 레벨, 언더스코어 접두 | `_merge_answers`, `_resolve_complete` |
| 프롬프트 블록 헬퍼 | `_{name}_block` (기존 관례) | `_slots_block`, `_answers_block` |
| 프리셋 상수 | UPPER_SNAKE | `AGENT_BUILD_SLOTS` |

### 10.2 Import Order

기존 유지 — 표준 라이브러리 → 외부 → 내부 절대 임포트(domain → application → infrastructure).

### 10.3 Environment Variables

§4.4 참조. 3개 전부 기본값 보유 → 미설정 환경 무영향.

### 10.4 This Feature's Conventions

| # | 규약 | 이유 |
|---|------|------|
| C1 | **LLM 스키마와 도메인 VO를 분리한다** | 시스템 계산 필드 오염 차단 (§2.4) |
| C2 | 구형 스칼라 입력은 `mode="before"` validator로 승격한다 | 계약 확장 시 하위호환 관례 |
| C3 | 상한은 Policy 인자로 주입한다 (`config` 전달) | domain이 env를 읽지 않게 |
| C4 | 사용자 입력값은 로그에 남기지 않는다 (개수만) | PII |
| C5 | 프롬프트의 소프트 신호와 Policy의 하드 강제를 **둘 다** 둔다 | 프롬프트만 믿지 않는다 (I5) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
├── domain/intent/
│   ├── schemas.py            ★확장  SlotSpec/SlotAnswer/SlotQuestion 신설
│   │                                 IntentSpec 타입 승격 + validator 2개
│   │                                 IntentResult +4필드 −entities
│   ├── interfaces.py         ★확장  analyze(..., answers, round)
│   └── policies.py           ★확장  normalize 재작성 + 순수함수 5개
├── application/
│   ├── intent/
│   │   ├── use_case.py       ★확장  인자 전달
│   │   └── node.py             무변경
│   └── agent_composer/
│       └── build_slots.py    ★신규  AGENT_BUILD_SLOTS
├── infrastructure/
│   ├── intent/adapter.py     ★확장  _IntentLLMOutput + 블록 3종
│   └── config/intent_config.py ★확장 env 3개
├── interfaces/schemas/intent.py ★확장 answers/round
└── api/routes/intent_router.py  ★확장 인자 전달

idt/tests/
├── domain/intent/
│   ├── test_policies.py      ★확장  S1~S17
│   └── test_schemas.py       ★신규  S18~S24
├── application/intent/
│   ├── test_use_case.py      ★확장  인자 전달 검증
│   └── test_node.py            무변경
├── application/agent_composer/
│   └── test_build_slots.py   ★신규  S32
├── infrastructure/intent/
│   └── test_adapter.py       ★확장  S25~S31
└── api/test_intent_router.py ★확장  S33~S41 (line 108 수정 필요)
```

**생성 3 / 수정 10 / 예상 변경량 ~700줄**

### 11.2 Implementation Order

TDD — 각 단계 Red → Green → Refactor.

1. **스키마** (`domain/intent/schemas.py`) — S18~S24 먼저. `SlotSpec`/`SlotAnswer`/`SlotQuestion` + validator 2개 + `IntentResult` 필드 교체
2. **Policy** (`domain/intent/policies.py`) — S1~S17. `normalize` 시그니처를 `(llm_out, spec, answers, round, limits)`로 재작성하고 순수함수 5개 분리
3. **포트** (`domain/intent/interfaces.py`) — 시그니처 확장 (구현 없음)
4. **Config** (`infrastructure/config/intent_config.py`) — env 3개
5. **어댑터** (`infrastructure/intent/adapter.py`) — S25~S31. `_IntentLLMOutput` 신설 → `_coerce` 재작성 → 블록 3종 → 로그 필드
6. **UseCase** (`application/intent/use_case.py`) — 인자 전달
7. **API** (`interfaces/schemas/intent.py`, `api/routes/intent_router.py`) — S33~S41. **`test_intent_router.py:108` 수정**
8. **프리셋** (`application/agent_composer/build_slots.py`) — S32
9. **회귀 검증** — A1~A6 전부

> 순서 근거: 2번(Policy)이 이 기능의 규칙 전부를 갖고 있고 LLM 없이 테스트되므로, 여기서 불변식 I1~I7이 다 잠기면 이후 단계는 배선일 뿐이다.

### 11.3 Session Guide

**Module Map**

| Scope Key | 모듈 | 파일 | 단계 | 의존 |
|-----------|------|------|------|------|
| `module-1` | 도메인 계약 | `schemas.py`, `interfaces.py` + 테스트 | 1, 3 | — |
| `module-2` | 판정 규칙 | `policies.py` + 테스트 | 2 | module-1 |
| `module-3` | LLM 어댑터 | `adapter.py`, `intent_config.py` + 테스트 | 4, 5 | module-2 |
| `module-4` | 배선 · API | `use_case.py`, `schemas/intent.py`, `intent_router.py` + 테스트 | 6, 7 | module-3 |
| `module-5` | 프리셋 · 회귀 | `build_slots.py` + 테스트, A1~A6 | 8, 9 | module-1 |

**Recommended Session Plan**

| 세션 | Scope | 산출물 |
|------|-------|--------|
| 1 | `--scope module-1,module-2` | 도메인 계약 + 불변식 I1~I7 전부 잠김. LLM 없이 테스트 통과 |
| 2 | `--scope module-3,module-4` | LLM 왕복 + API 동작. 수동 시나리오 1회 가능 |
| 3 | `--scope module-5` | 프리셋 + 아키텍처 회귀 검증 |

> `module-5`는 `module-1`만 있으면 되므로 세션 1 직후로 당겨도 된다.

### 11.4 다음 사이클 1차 배선 후보 (Plan R6 · §9 숙제)

이번 사이클의 `AGENT_BUILD_SLOTS`는 소비자가 없다(의도된 것). 다음 사이클의 배선 지점을 여기 고정한다.

**1차 배선 지점**: `src/application/agent_composer/planner.py` → `AgentPlanner.plan()`

| 항목 | 현재 | 배선 후 |
|------|------|---------|
| 질문 생성 | `_PlanOutput.clarifying_questions` — LLM 자유재량 | `IntentResult.questions` — 미충족 축에서 유도 |
| 질문 상한 | `PlannerPolicy.clamp_questions` | 동일 (이중 clamp, 무해) |
| 종료 조건 | `confidence >= 0.8` | `complete == True` 또는 라운드 상한 |
| 답변 왕복 | `ClarificationAnswerDto` 에코백 | `SlotAnswer` 로 매핑 (구조 동형) |

**진입 조건 2개** — 다음 사이클 Plan에서 먼저 확인한다.

1. **R2 실측 재평가** — 축 목록 프롬프트가 과차단을 유발하는지, 이번 사이클의 독립 API로 실제 요청 10건을 돌려 확인한다. §4.3의 4겹 방어가 충분한지가 배선 가부를 가른다.
2. **compose 응답 계약 확정** — `ClarifyingQuestionDto`에 `slot_key`를 추가할지, `IntentResult`를 통째로 노출할지. 화면단 재작업 결과에 종속되므로 그 이후에 결정한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-14 | 초안 — Option C 선택. Plan 확정 항목 5개 해소(entities 제거 / labels 조건 완화 / R2 4겹 방어 문안 / 프리셋 5축 확정 / 질문 문안 LLM 생성) | 배상규 |
| 0.2 | 2026-08-17 | §3.1·§9.3을 구현 기준으로 갱신 (SoT — 코드가 진실). 이탈 2건 기록: ① LLM 스키마를 domain `IntentDraft`로 배치(레이어 방향) ② dict → 배열(OpenAI strict 호환, 실 LLM 검증에서 발견) | 배상규 |
