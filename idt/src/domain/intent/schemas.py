"""의도 분석 도메인 스키마.

Design Ref: §3.1 — 분류 체계(라벨)를 호출자가 주입하므로, 이 모듈 어디에도
도메인 라벨 상수를 두지 않는다. label 은 Enum 이 아니라 str 이다.

IntentResult 는 LLM `with_structured_output` 의 출력 스키마이자 도메인 VO 로
함께 사용한다 (Design §2.4 Option C). 그 대가로 LLM 이 채워선 안 되는 필드
(degraded)가 오염될 수 있으므로, 어댑터와 Policy 가 3층으로 방어한다.
"""
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """대화 이력 1턴.

    모듈은 이력을 보유하지 않는다 — 호출 인자로만 받는다 (Design D7 / Plan R6).
    """

    role: Literal["user", "assistant"]
    content: str


class IntentLabel(BaseModel):
    """호출자가 정의하는 의도 후보 1개.

    모듈은 name 의 의미를 모른다. description 이 곧 프롬프트 품질이므로 필수다
    (Plan R3 — 판정 품질이 호출자 명세에 종속되는 대가).
    """

    name: str = Field(..., min_length=1, description="의도 식별자")
    description: str = Field(..., min_length=1, description="이 의도가 무엇인지 설명")


class IntentSpec(BaseModel):
    """분류 체계 — 100% 호출자 주입 (Plan D3).

    labels 가 2개 미만이면 분류 자체가 성립하지 않으므로 거부한다 (FR-11).
    """

    labels: list[IntentLabel] = Field(..., min_length=2)
    slots: list[str] = Field(
        default_factory=list, description="추출을 희망하는 엔티티 키 목록"
    )
    allow_unknown: bool = Field(
        default=True,
        description=(
            "힌트이지 제약이 아니다. False 여도 빈 label 을 거부하지 않는다 — "
            "억지 선택을 강제하면 위키 계약 2(목록 프레이밍 과차단)를 재현한다."
        ),
    )


class IntentResult(BaseModel):
    """판정 결과. LLM structured output 스키마 겸용 (Design §2.4).

    각 필드의 description 은 그대로 LLM 에게 전달되는 지시문이다.
    """

    label: str | None = Field(
        default=None,
        description=(
            "가장 잘 맞는 후보 의도의 name. "
            "명확히 해당하는 것이 없으면 비워 두세요."
        ),
    )
    confidence: float = Field(default=0.0, description="0.0~1.0 사이의 확신도")
    entities: dict[str, str] = Field(
        default_factory=dict, description="메시지에서 추출한 슬롯 키-값"
    )
    ambiguous: bool = Field(
        default=False, description="후보가 둘 이상으로 갈리면 true"
    )
    missing_slots: list[str] = Field(
        default_factory=list, description="요청된 슬롯 중 값을 찾지 못한 키"
    )
    reason: str = Field(default="", description="판단 근거(짧게)")
    degraded: bool = Field(
        default=False,
        description="시스템이 채우는 필드입니다. 항상 false 로 두세요.",
    )
