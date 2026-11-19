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
