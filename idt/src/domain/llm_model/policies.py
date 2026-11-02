"""LlmModelPolicy: LLM 모델 레지스트리 도메인 규칙.

LLM-MODEL-REG-001 §4-2 Policy.
외부 호출 없이 순수 검증 함수만 보관한다.

image-generation-tool Design §3.3 / §4.2 / D-05: 모델 종류(model_kind) 규칙 추가.
"""
from src.domain.llm_model.entity import LlmModel

# image-generation-tool: wire 값(프론트·API 계약)이므로 변경 금지.
MODEL_KINDS: tuple[str, ...] = ("chat", "image")


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

    # ── image-generation-tool: 모델 종류 ─────────────────────────────────

    @staticmethod
    def validate_model_kind(kind: str) -> None:
        if kind not in MODEL_KINDS:
            raise ValueError(
                f"model_kind 는 {MODEL_KINDS} 중 하나여야 합니다: {kind!r}"
            )

    @staticmethod
    def require_chat_model(model: LlmModel) -> None:
        """에이전트·비전·서브에이전트 모델 후보는 chat 종류만 (Design §4.2).

        image 만 명시적으로 거부한다 — 구버전 행·테스트 대역(kind 미설정)은 chat 으로 본다.
        """
        if model.model_kind == "image":
            # 접두어는 프론트가 필드 오류로 구분하는 wire 계약 (Design §4.2 / §6.1)
            raise ValueError(
                f"MODEL_KIND_MISMATCH: '{model.display_name}' 은(는) "
                "이미지 생성 모델이라 대화 모델로 쓸 수 없습니다."
            )

    @staticmethod
    def require_image_model(model: LlmModel) -> None:
        """이미지 생성 도구 설정의 모델은 활성 image 종류만 (Design §4.2)."""
        if model.model_kind != "image":
            raise ValueError(
                f"'{model.display_name}' 은(는) 이미지 생성 모델이 아닙니다 "
                f"(model_kind={model.model_kind})."
            )
        if not model.is_active:
            raise ValueError(f"'{model.display_name}' 은(는) 비활성 모델입니다.")

    @staticmethod
    def validate_default_is_chat(model: LlmModel) -> None:
        """기본 모델은 에이전트 기본 연결 대상이므로 chat 만 허용 (D-05)."""
        if model.is_default and model.model_kind == "image":
            raise ValueError("기본 모델은 대화(chat) 종류만 지정할 수 있습니다.")
