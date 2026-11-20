"""근거 판정 모델 설정 오류 — 라우터가 code 로 422 를 돌려준다 (Design §4.2)."""

from __future__ import annotations


class GroundingJudgeSettingError(Exception):
    code = "GROUNDING_JUDGE_SETTING_ERROR"


class JudgeModelNotFoundError(GroundingJudgeSettingError):
    code = "JUDGE_MODEL_NOT_FOUND"

    def __init__(self, model_id: str) -> None:
        super().__init__(f"사용할 수 없는 모델입니다(없거나 비활성): {model_id}")


class JudgeModelKindInvalidError(GroundingJudgeSettingError):
    code = "JUDGE_MODEL_KIND_INVALID"

    def __init__(self, model_id: str) -> None:
        super().__init__(f"채팅 모델만 판정 모델로 지정할 수 있습니다: {model_id}")
