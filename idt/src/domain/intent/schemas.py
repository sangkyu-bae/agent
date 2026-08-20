"""의도 분석 도메인 스키마.

Design Ref: §3.1 — 분류 체계(라벨)와 물어볼 축(슬롯)을 호출자가 주입하므로,
이 모듈 어디에도 도메인 어휘를 두지 않는다. label·slot key 는 Enum 이 아니라 str 이다.

**선행 사이클 결정의 폐기 (Design §2.4)**: 이전에는 `IntentResult` 를 LLM
`with_structured_output` 스키마로 겸용했다. 시스템 계산 필드가 1개(degraded)에서
3개(+complete, +missing_slots)로 늘어나면서 방어 코드가 필드 수에 비례해 늘어나는
구조가 되었으므로, LLM 이 채우는 필드만 담은 `IntentDraft` 를 분리한다.

  IntentDraft   → LLM 이 보는 유일한 스키마. 시스템 계산 필드가 **없다**.
  IntentResult  → Draft + Policy 계산 결과. LLM 은 이 타입을 모른다.

**Design 이탈**: Design §3.1 은 LLM 출력 스키마(`_IntentLLMOutput`)를 어댑터에
두었으나, 그러면 domain 의 `IntentResultPolicy.normalize()` 가 infrastructure 타입을
인자로 받게 되어 의존 방향이 뒤집힌다. LLM 채움 필드만 가진 도메인 VO 로 두는 것이
§2.4 의 목적(시스템 필드 격리)을 동일하게 달성하면서 레이어를 지킨다.
부수 효과로 `allow_free_text` 를 LLM 이 아니라 SlotSpec 에서 채우게 되었다.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Turn(BaseModel):
    """대화 이력 1턴.

    모듈은 이력을 보유하지 않는다 — 호출 인자로만 받는다 (Design D7 / Plan R6).
    """

    role: Literal["user", "assistant"]
    content: str


class IntentLabel(BaseModel):
    """호출자가 정의하는 의도 후보 1개.

    모듈은 name 의 의미를 모른다. description 이 곧 프롬프트 품질이므로 필수다.
    """

    name: str = Field(..., min_length=1, description="의도 식별자")
    description: str = Field(..., min_length=1, description="이 의도가 무엇인지 설명")


class SlotSpec(BaseModel):
    """호출자가 선언하는 '물어볼 축' 1개 (Design §3.1).

    되묻기가 LLM 의 재량이 아니라 이 선언의 함수가 되는 것이 이 기능의 존재 이유다.
    모듈은 key 의 의미를 모른다 — description 이 그대로 프롬프트에 실린다.
    """

    key: str = Field(..., min_length=1, description="축 식별자")
    description: str = Field(..., min_length=1, description="이 축이 무엇인지")
    options: list[str] = Field(
        default_factory=list,
        description="선택지 힌트. 고정 목록이 아니라 LLM 앵커링용 예시다.",
    )
    allow_free_text: bool = Field(
        default=True, description="사용자가 선택지 밖 값을 직접 쓸 수 있는지"
    )
    required: bool = Field(
        default=False, description="이 축이 비면 complete 가 될 수 없다"
    )


class SlotAnswer(BaseModel):
    """사용자가 되묻기에 답한 값.

    왕복은 stateless 다 (Plan D4) — 모듈은 라운드 사이에 아무것도 기억하지 않고,
    이전 답변은 매 호출 인자로 에코백된다.
    빈 답변은 '답하지 않음'이므로 애초에 보내지 않는다 (min_length=1).
    """

    slot_key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class SlotValue(BaseModel):
    """LLM 이 채운 축 하나 — `IntentDraft` 전용 (Act-1).

    도메인 VO 는 `dict[str, str]` 를 쓰지만 LLM 스키마는 쓸 수 없다:
    OpenAI structured outputs 의 strict 모드가 **자유 키 dict 를 거부**하기 때문이다
    (M5 실측 — dict 가 하나라도 있으면 400, 판정이 항상 degraded 로 떨어졌다).
    """

    key: str = Field(description="후보 항목 목록에 있는 key")
    value: str = Field(description="메시지에서 확실히 알 수 있는 값")


class SlotSuggestion(BaseModel):
    """못 채운 축 하나에 대한 추천 선택지 — `IntentDraft` 전용 (Act-1)."""

    key: str = Field(description="후보 항목 목록에 있는 key")
    options: list[str] = Field(
        default_factory=list, description="이 요청 맥락에 맞는 선택지"
    )


def _pairs_from_mapping(value: object, value_field: str) -> object:
    """dict 로 오는 구현체도 받아들인다 (입력 관용).

    `method="function_calling"` 등 strict 가 아닌 경로는 dict 를 돌려줄 수 있고,
    호출자가 테스트에서 dict 로 쓰는 편이 읽기 쉽다. **출력 스키마는 언제나
    배열**이므로 이 관용이 strict 호환성을 되돌리지 않는다.
    """
    if isinstance(value, dict):
        return [{"key": k, value_field: v} for k, v in value.items()]
    return value


class SlotQuestionDraft(BaseModel):
    """LLM 이 만드는 되묻기 초안.

    `allow_free_text` 가 **없다** — 그것은 SlotSpec 이 정하는 값이지 LLM 이
    정할 값이 아니다. Policy 가 spec 에서 채워 SlotQuestion 을 완성한다.
    """

    slot_key: str = Field(description="질문 대상 축의 key. 후보 축 목록에 있는 것만.")
    question: str = Field(description="사용자에게 물을 한국어 한 문장")
    options: list[str] = Field(
        default_factory=list, description="이 축의 추천 선택지 2~4개"
    )


class SlotQuestion(BaseModel):
    """미충족 축 1개에 대한 최종 되묻기. 호출자가 그대로 화면에 렌더한다."""

    slot_key: str
    question: str
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class SlotLimits(BaseModel):
    """되묻기 상한 (Design §4.4 / 규약 C3).

    domain 은 env 를 읽지 않는다 — 어댑터가 config 에서 만들어 주입한다.
    기본값은 agent_composer 의 `PlannerPolicy` 와 맞춰 두 모듈이 붙었을 때
    놀라지 않게 한다.
    """

    max_rounds: int = Field(default=2, ge=0)
    max_questions: int = Field(default=3, ge=0)
    max_options_per_slot: int = Field(default=4, ge=0)


class IntentSpec(BaseModel):
    """분류 체계 + 물어볼 축 — 100% 호출자 주입 (Plan D3).

    셋 중 하나의 형태로 쓴다.
      - 분류만: labels ≥ 2
      - 슬롯만: slots ≥ 1        ← 에이전트 생성이 쓰는 형태
      - 둘 다:  위 두 조건 동시
    """

    labels: list[IntentLabel] = Field(default_factory=list)
    slots: list[SlotSpec] = Field(default_factory=list)
    allow_unknown: bool = Field(
        default=True,
        description=(
            "힌트이지 제약이 아니다. False 여도 빈 label 을 거부하지 않는다 — "
            "억지 선택을 강제하면 위키 계약 2(목록 프레이밍 과차단)를 재현한다."
        ),
    )

    @field_validator("slots", mode="before")
    @classmethod
    def _promote_str_slots(cls, value: object) -> object:
        """구형 `list[str]` 입력을 SlotSpec 으로 승격한다 (FR-02 / 규약 C2).

        입력 하위호환만 보장한다 — 읽을 때의 타입은 항상 SlotSpec 이다.
        """
        if not isinstance(value, list):
            return value
        return [
            {"key": item, "description": item} if isinstance(item, str) else item
            for item in value
        ]

    @model_validator(mode="after")
    def _require_labels_or_slots(self) -> "IntentSpec":
        """labels 또는 slots 중 하나는 있어야 한다 (FR-16).

        labels 가 1개인 경우는 슬롯이 있어도 거부한다 — 분류가 성립하지 않는
        분류 체계를 받아 두면 판정 결과가 항상 그 라벨로 쏠린다.
        """
        if len(self.labels) == 1:
            raise ValueError("labels must be empty or have at least 2 entries")
        if not self.labels and not self.slots:
            raise ValueError("either labels or slots must be provided")
        return self


class IntentDraft(BaseModel):
    """LLM 이 채우는 값만 담은 판정 초안 — **LLM 이 보는 유일한 스키마**.

    각 필드의 description 은 그대로 LLM 에게 전달되는 지시문이다.
    시스템이 계산하는 `missing_slots` / `complete` / `degraded` 는 여기 없다.
    """

    label: str | None = Field(
        default=None,
        description=(
            "가장 잘 맞는 후보 의도의 name. "
            "명확히 해당하는 것이 없으면 비워 두세요."
        ),
    )
    confidence: float = Field(default=0.0, description="0.0~1.0 사이의 확신도")
    ambiguous: bool = Field(
        default=False, description="후보가 둘 이상으로 갈리면 true"
    )
    reason: str = Field(default="", description="판단 근거(짧게)")
    filled_slots: list[SlotValue] = Field(
        default_factory=list,
        description=(
            "메시지에서 확실히 알 수 있는 항목만 채우세요. 추측하거나 지어내지 마세요."
        ),
    )
    suggestions: list[SlotSuggestion] = Field(
        default_factory=list,
        description="채우지 못한 항목별 추천 선택지. 이 요청 맥락에 맞게 만드세요.",
    )
    questions: list[SlotQuestionDraft] = Field(
        default_factory=list, description="채우지 못한 항목에 대한 되묻기"
    )

    @field_validator("filled_slots", mode="before")
    @classmethod
    def _accept_mapping_slots(cls, value: object) -> object:
        return _pairs_from_mapping(value, "value")

    @field_validator("suggestions", mode="before")
    @classmethod
    def _accept_mapping_suggestions(cls, value: object) -> object:
        return _pairs_from_mapping(value, "options")


class IntentResult(BaseModel):
    """판정 결과 — LLM 이 채운 값과 시스템이 계산한 값의 합 (Design §3.1).

    **더 이상 LLM 출력 스키마가 아니다.** 하단 3개 필드는 Policy·어댑터만 쓴다.
    """

    # --- LLM 이 채우는 값 ---
    label: str | None = None
    confidence: float = 0.0
    ambiguous: bool = False
    reason: str = ""
    filled_slots: dict[str, str] = Field(default_factory=dict)
    suggestions: dict[str, list[str]] = Field(default_factory=dict)
    questions: list[SlotQuestion] = Field(default_factory=list)
    # --- 시스템이 계산하는 값 (LLM 접근 불가) ---
    missing_slots: list[str] = Field(default_factory=list)
    complete: bool = False
    degraded: bool = False
