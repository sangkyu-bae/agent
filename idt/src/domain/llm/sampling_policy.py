"""LLM 샘플링 파라미터 허용 정책 (domain 순수 함수).

Claude Opus 4.7 이후 모델(Opus 4.8·5·5.5, Sonnet 5·5.5, Haiku 5.5, Fable·Mythos)은
temperature를 보내면 400("`temperature` is deprecated for this model")을 반환한다.
2026-11-19 claude-opus-5-5 실호출로 확인.

temperature를 받는 구형 모델(Claude 3.x, 4.0~4.6)만 True를 돌려준다. 이름 형식을
모르는 모델은 False — 보내지 않으면 기본값으로 동작하지만, 보내면 거부될 수 있다.
"""
import re

# claude-3-5-sonnet-20241022, claude-3-opus-20240229 등 3세대
_CLAUDE_3 = re.compile(r"^claude-3[-.]")
# claude-<family>-<major>[-<minor>][-<yyyymmdd>]
_CLAUDE_FAMILY = re.compile(
    r"^claude-(?:opus|sonnet|haiku)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$"
)
_LAST_TEMPERATURE_MINOR_ON_4 = 6  # 4.6까지 허용, 4.7부터 거부


def anthropic_accepts_temperature(model_name: str) -> bool:
    """이 Claude 모델에 temperature를 보내도 되는지."""
    name = (model_name or "").strip()
    if _CLAUDE_3.match(name):
        return True
    match = _CLAUDE_FAMILY.match(name)
    if match is None:
        return False
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major < 4:
        return True
    return major == 4 and minor <= _LAST_TEMPERATURE_MINOR_ON_4


# ── claude-agent-e2e-fixes Design §4.1: 강제 tool_choice 지원 여부 ──────────
# Claude API 문서(2026-11): Opus 5.5·Sonnet 5.5·Fable 5.1/5.2·Mythos 5.1/5.2 는
# tool_choice {type: tool|any} 를 400 으로 거부한다 (2026-11-19 opus-5-5 실호출 확인).
# LangChain with_structured_output 기본(function_calling)이 강제 tool_choice 를 보내므로
# 이 판정이 False 면 LLMFactory 가 json_schema 방식 모델을 만든다.
_FAMILY_VERSION = re.compile(
    r"^claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$"
)
# 계열별로 강제 tool_choice 를 거부하기 시작한 버전 (이 버전 이상은 거부)
_FIRST_REJECTING_VERSION: dict[str, tuple[int, int]] = {
    "opus": (5, 5), "sonnet": (5, 5), "fable": (5, 1), "mythos": (5, 1),
    "haiku": (5, 6),  # haiku 5.5 까지 지원 — 그 이후 신형은 거부로 간주
}


def anthropic_supports_forced_tool_choice(model_name: str) -> bool:
    """이 Claude 모델이 tool_choice {type: tool|any} 를 받는가.

    이름 형식을 모르는 모델(신형·접두사 붙은 이름·빈 값)은 False — json_schema 는
    구형 모델(sonnet-4-6)에서도 동작함을 실측했으므로 보수적 기본값이 안전하다.
    """
    name = (model_name or "").strip()
    if _CLAUDE_3.match(name):
        return True
    match = _FAMILY_VERSION.match(name)
    if match is None:
        return False
    family = match.group(1)
    version = (int(match.group(2)), int(match.group(3) or 0))
    return version < _FIRST_REJECTING_VERSION[family]


# ── claude-agent-e2e-fixes Design §4.1: 출력 한도(max_tokens) 해석 ────────────
# llm_model.max_tokens 는 컨텍스트 크기, max_output_tokens(V092)가 응답 출력 한도다.
MAX_OUTPUT_TOKENS_LIMIT = 128000


def resolve_max_output_tokens(
    provider: str, stored: int | None, anthropic_default: int,
) -> int | None:
    """요청에 보낼 출력 한도.

    저장값 우선, 없으면 Anthropic 만 기본값, 그 외 None(미전달).

    Anthropic 은 max_tokens 가 필수이고 langchain-anthropic 이 모르는 신형 모델
    (claude-opus-5-5)을 4096 으로 두어 thinking 이 출력을 다 쓰는 문제가 있었다
    (2026-11-19 실측: output 4096 전부 reasoning, text 0자).
    """
    if stored is not None:
        return stored
    return anthropic_default if provider == "anthropic" else None
