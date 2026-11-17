"""JevEntityChooser — 엔티티 동일성 판정을 Jev ChoiceQuestion 으로 묻는다.

Design Ref: graph-rag-foundation §7.2 D3 / Plan FR-08. 판정 포트(JudgmentPort)만
의존한다(구현 직접 참조 금지 — tests/infrastructure/judgment 경계 테스트에 등록).
JudgmentError·타임아웃은 그대로 올린다 — 대체(LLM)는 EntityResolver 한 곳에서 한다.
"""

from __future__ import annotations

import asyncio

from src.domain.graph_rag.extraction import Mention
from src.domain.graph_rag.interfaces import EntityChooserPort
from src.domain.graph_rag.resolution import NEW_LABEL, Candidate, ChooserVerdict
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import ChoiceQuestion, JudgmentRequest

QID = "same_entity"
_OUTER_TIMEOUT_MARGIN = 0.5
_INSTRUCTIONS = (
    "문서에 나온 '언급'이 후보 엔티티 중 어느 것과 같은 대상을 가리키는지 고르세요. "
    "표기·띄어쓰기·약칭이 달라도 같은 대상이면 그 후보를 고릅니다. "
    "이름이 비슷해도 다른 대상(다른 상품·다른 규정·다른 기준)이면 NEW 를 고릅니다."
)
_NEW_DESCRIPTION = "후보 중 같은 대상이 없음 — 새 엔티티"


def _describe(c: Candidate) -> str:
    desc = f"{c.name} (타입: {c.type})"
    if c.description:
        desc += f" — {c.description[:200]}"
    return desc


class JevEntityChooser(EntityChooserPort):
    """질문 문구만 바꿔 주제 판정(module-4b)에도 쓴다.

    qid·instructions·new_description 으로 바꾼다.
    """

    def __init__(
        self,
        backend: JudgmentPort,
        *,
        timeout_seconds: float,
        qid: str = QID,
        instructions: str = _INSTRUCTIONS,
        new_description: str = _NEW_DESCRIPTION,
    ) -> None:
        self._backend = backend
        self._timeout = timeout_seconds
        self._qid = qid
        self._instructions = instructions
        self._new_description = new_description

    async def choose(
        self,
        mention: Mention,
        context: str,
        candidates: dict[str, Candidate],
        request_id: str,
    ) -> ChooserVerdict:
        criteria = tuple((label, _describe(c)) for label, c in candidates.items())
        request = JudgmentRequest(
            state={
                "mention": mention.name,
                "mention_type": mention.type,
                "mention_description": mention.description or "",
                "context": context,
            },
            questions={
                self._qid: ChoiceQuestion(
                    instructions=self._instructions,
                    criteria=criteria + ((NEW_LABEL, self._new_description),),
                )
            },
        )
        response = await asyncio.wait_for(
            self._backend.judge(request), self._timeout + _OUTER_TIMEOUT_MARGIN
        )
        answer = response.choice(self._qid)
        return ChooserVerdict(
            label=answer.choice, probabilities=dict(answer.probabilities)
        )
