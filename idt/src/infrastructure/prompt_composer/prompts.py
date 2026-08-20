"""시스템 프롬프트 생성용 LLM 프롬프트 템플릿.

Design Ref: §4.4.

────────────────────────────────────────────────────────────────────────
§10.3 AgentComposer 와의 섹션 대조 (Plan R1 — 두 모듈이 벌어지는지 볼 기준)
비교 대상: `application/agent_composer/composer.py:_SYSTEM_PROMPT:97-102`

| 섹션      | AgentComposer            | 여기                        |
|-----------|--------------------------|-----------------------------|
| 목적      | 에이전트 목적 1~2문장     | purpose (동일)              |
| 역할      | 각 워커의 역할·사용 시점  | roles[] — **워커 비종속**   |
| 도구 지침 | 시점·호출법·주의사항      | tool_guides{when,how,caution}|
| 동작 원칙 | 실행 순서·언어·주의사항   | principles[] — 순서 제외    |
| 산출 형태 | 문자열 1개                | 구조 + 서버 조립            |

차이 2건(역할의 워커 비종속 / 원칙의 실행 순서 제외)은 **의도된 것**이다.
이 모듈은 워커·flow 개념을 모른다 (Design Q1).
────────────────────────────────────────────────────────────────────────

프롬프트의 "목록 밖 도구 금지" 지시는 **2차 방어선일 뿐**이다. 1차 방어는
`PromptAssemblyPolicy.drop_hallucinated` 가 후보 밖 tool_id 를 실제로 폐기하는
것이다 — 프롬프트만 믿지 않는다 (intent 어댑터 `_round_block` 관례).
"""

SYSTEM = (
    "당신은 AI 에이전트의 시스템 프롬프트를 설계하는 전문가입니다.\n"
    "아래 재료만으로 에이전트 프롬프트의 각 섹션을 작성하세요.\n\n"
    "{tools_block}"
    "{intent_block}"
    "[규칙]\n"
    "- purpose: 이 에이전트가 무엇을 하는지 1~2문장.\n"
    "- roles: 에이전트가 수행하는 역할. 최대 6개. "
    "도구가 없어도 작성합니다.\n"
    "- tool_guides: **위 도구 목록에 있는 tool_id 만** 사용하세요. "
    "목록에 없는 도구를 지어내지 마세요. 각 항목에 when(언제) / "
    "how(어떤 입력으로) / caution(주의)을 씁니다.\n"
    "- principles: 응답 언어·거절 조건·환각 금지 등 동작 원칙. 최대 10개.\n"
    "- 전부 한국어로 작성합니다.\n"
)

HUMAN = "{history_block}[현재 요청]\n{user_request}"

_TOOLS_TEMPLATE = "[사용 가능한 도구]\n{lines}\n\n"
_INTENT_TEMPLATE = (
    "[사전 분석된 사용자 의도]\n"
    "- 분류: {label}\n"
    "{extra}"
    "이 판정은 참고용입니다. 요청 본문과 충돌하면 요청이 우선입니다.\n\n"
)
_HISTORY_TEMPLATE = "[이전 대화]\n{lines}\n\n"


def tools_block(metas) -> str:
    """도구 목록 블록. 도구가 없으면 블록 자체를 싣지 않는다 (Design §4.4)."""
    if not metas:
        return ""
    lines = "\n".join(_tool_line(meta) for meta in metas)
    return _TOOLS_TEMPLATE.format(lines=lines)


def _tool_line(meta) -> str:
    origin = f" [{meta.server_name}]" if meta.server_name else ""
    return f"- {meta.tool_id}{origin}: {meta.name} — {meta.description}"


def intent_block(intent: dict | None) -> str:
    """의도 블록.

    FR-13 — intent 가 없거나 `degraded=true` 면 **부착하지 않는다.**
    판정 실패는 "의도 모름"이지 "의도 없음"이 아니며, 오염된 판정을 프롬프트에
    실으면 프롬프트가 왜곡된다.
    """
    if not intent or intent.get("degraded"):
        return ""
    label = str(intent.get("label") or "").strip()
    if not label:
        return ""
    reason = str(intent.get("reason") or "").strip()
    extra = f"- 근거: {reason}\n" if reason else ""
    return _INTENT_TEMPLATE.format(label=label, extra=extra)


def history_block(history: list[dict]) -> str:
    if not history:
        return ""
    lines = "\n".join(
        f"{turn.get('role', '')}: {turn.get('content', '')}" for turn in history
    )
    return _HISTORY_TEMPLATE.format(lines=lines)
