"""LlmModelPolicy: LLM 모델 레지스트리 도메인 규칙.

LLM-MODEL-REG-001 §4-2 Policy.
외부 호출 없이 순수 검증 함수만 보관한다.
"""
from src.domain.llm_model.entity import LlmModel


class LlmModelPolicy:
    """LLM 모델 등록/수정 시 강제 규칙."""

    @staticmethod
    def validate_single_default(models: list[LlmModel]) -> None:
        """is_default=True 모델은 전체에서 1개만 허용."""
        defaults = [m for m in models if m.is_default]
        if len(defaults) > 1:
            raise ValueError(
                f"기본 모델은 1개만 허용됩니다. 현재 {len(defaults)}개 지정됨."
            )

    @staticmethod
    def validate_model_name_not_empty(model_name: str) -> None:
        """model_name 빈 문자열/공백 불가."""
        if not model_name or not model_name.strip():
            raise ValueError("model_name은 빈 문자열일 수 없습니다.")
