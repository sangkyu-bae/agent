"""ComposePolicy: 초안 보정·판정 도메인 규칙.

LLM 출력을 신뢰하지 않고 서버가 최종 결정한다(nl-agent-composer D7).
상한값(max_tools 등)은 호출부가 AgentBuilderPolicy 상수를 넘겨 단일 출처를 유지한다.
"""


class ComposePolicy:
    # fix-agent-composer: Fix 채팅 history 절단 상한
    MAX_HISTORY_TURNS = 6
    MAX_HISTORY_TURN_CHARS = 500

    @staticmethod
    def clamp_history(turns: list) -> list[dict]:
        """최근 MAX_HISTORY_TURNS턴만 유지하고 턴당 content를 절단한다.

        입력은 role/content 속성을 가진 객체 목록(duck-typed),
        출력은 LLM messages 호환 {role, content} dict 목록.
        """
        recent = turns[-ComposePolicy.MAX_HISTORY_TURNS:]
        return [
            {
                "role": t.role,
                "content": t.content[: ComposePolicy.MAX_HISTORY_TURN_CHARS],
            }
            for t in recent
        ]

    @staticmethod
    def drop_unknown_tools(
        workers: list, candidate_ids: set[str]
    ) -> tuple[list, list[str]]:
        """후보에 없는 tool_id 워커 제거. (유지 워커, drop된 tool_id) 반환."""
        kept = [w for w in workers if w.tool_id in candidate_ids]
        dropped = [w.tool_id for w in workers if w.tool_id not in candidate_ids]
        return kept, dropped

    @staticmethod
    def clamp_tool_count(
        workers: list, max_tools: int
    ) -> tuple[list, list[str]]:
        """sort_order 오름차순 상위 max_tools 유지. (유지 워커, 잘린 tool_id) 반환."""
        ordered = sorted(workers, key=lambda w: w.sort_order)
        kept = ordered[:max_tools]
        cut = [w.tool_id for w in ordered[max_tools:]]
        return kept, cut

    @staticmethod
    def clamp_system_prompt(prompt: str, max_length: int) -> tuple[str, bool]:
        """max_length 초과 시 절단. (프롬프트, 절단 여부) 반환."""
        if len(prompt) <= max_length:
            return prompt, False
        return prompt[:max_length], True

    @staticmethod
    def derive_coverage(worker_count: int, missing: list) -> str:
        """서버 재산정: 워커 0 → none / missing 있음 → partial / 그 외 full."""
        if worker_count == 0:
            return "none"
        if missing:
            return "partial"
        return "full"
