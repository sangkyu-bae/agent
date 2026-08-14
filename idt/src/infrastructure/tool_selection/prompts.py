"""셀렉터 프롬프트 — Design Ref: §4.4.

파싱은 관대하게, 검증은 엄격하게. 여기서는 프롬프트 조립만 하고
출력 검증(화이트리스트 대조)은 domain policies.sanitize가 담당한다.
"""
import re
from collections.abc import Sequence

from src.domain.tool_selection.policies import effective_description
from src.domain.tool_selection.schemas import ToolCandidate

MAX_DESCRIPTION_CHARS = 200
"""후보 1건당 설명 길이 상한.

선별에 필요한 건 "이 도구가 무엇을 하는가"뿐이고 인자 스키마는 실제 호출 시점에
바인딩된 도구가 알려준다. 실측(Doc Convert MCP) 결과 MCP 설명은 ``Args:`` 블록을
포함한 여러 줄 docstring이라, 자르지 않으면 도구 4개만으로 프롬프트 2천 자를 넘는다.
"""

_SECTION_HEAD = re.compile(r"\n\s*(?:Args?|Arguments|Returns?|Raises|Example)s?\s*:",
                           re.I)
_WHITESPACE = re.compile(r"\s+")


def summarize_description(text: str) -> str:
    """설명을 한 줄로 압축한다 — 도구 1건 = 1줄 형식을 지키기 위함.

    ``Args:``/``Returns:`` 같은 시그니처 블록을 잘라내고, 남은 앞부분을 공백
    정규화해 상한까지 줄인다.
    """
    head = _SECTION_HEAD.split(text or "", maxsplit=1)[0]
    flat = _WHITESPACE.sub(" ", head).strip()
    if len(flat) <= MAX_DESCRIPTION_CHARS:
        return flat
    return flat[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"

SELECTOR_SYSTEM_PROMPT = """\
당신은 도구 선별기다. 사용자 질의를 수행하는 데 실제로 필요한 도구만 고른다.

규칙:
- 최대 {top_k}개까지만 고른다. 확신이 없으면 적게 고른다.
- 반드시 아래 목록에 있는 id만 출력한다. 새로운 id를 만들지 않는다.
- 설명·인사말 없이 JSON만 출력한다.

출력 형식:
{{"tool_ids": ["...", "..."]}}"""


def build_user_prompt(query: str, candidates: Sequence[ToolCandidate]) -> str:
    """질의 + 후보 목록을 프롬프트로 조립한다.

    설명이 저신호(스텁·공백)인 도구는 effective_description이 이름 토큰과
    서버명으로 보강하고(§3.3), 반대로 너무 긴 설명은 summarize_description이
    한 줄로 압축한다. 두 방향 모두 "도구 1건 = 1줄"을 지키기 위함이다.
    """
    lines = [
        f"- {c.tool_id} | {c.name} | "
        f"{summarize_description(effective_description(c))}"
        for c in candidates
    ]
    catalog = "\n".join(lines)
    return f"질의: {query}\n\n사용 가능한 도구:\n{catalog}"
