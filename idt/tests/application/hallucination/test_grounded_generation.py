"""근거 재작성 루프 — 생성 → 판정 → 재작성 → 상한 초과 시 문장 제거.

Design Ref: draft-grounding-check v0.2 §2.2, §5.1 (G1–G9).
"""
import json
from unittest.mock import MagicMock

import pytest

from src.application.hallucination.grounded_generation import GroundedGenerator
from src.domain.hallucination.grounding import (
    GroundingJudgePort,
    GroundingVerdict,
    UnsupportedClaim,
)

BAD = "안녕하세요. 대표번호 1877-9900 으로 문의하세요. 감사합니다."
GOOD = "안녕하세요. 고객센터로 문의해 주세요. 감사합니다."
SOURCES = "[문의] 추가대출 가능 여부 문의"


def _verdict(*spans, severity="high"):
    return GroundingVerdict(unsupported_claims=tuple(
        UnsupportedClaim(span=s, reason="근거 없음", severity=severity) for s in spans
    ))


class FakeJudge(GroundingJudgePort):
    def __init__(self, verdicts=None, raises=None):
        self.verdicts = list(verdicts or [])
        self.raises = raises
        self.calls: list[dict] = []

    async def judge(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return self.verdicts.pop(0) if self.verdicts else _verdict()


class FakeGenerate:
    def __init__(self, outputs, raise_on=None):
        self.outputs = list(outputs)
        self.feedbacks: list[str] = []
        self.raise_on = raise_on

    async def __call__(self, feedback: str) -> str:
        self.feedbacks.append(feedback)
        if self.raise_on is not None and len(self.feedbacks) == self.raise_on:
            raise RuntimeError("llm down")
        return self.outputs.pop(0)


class RecordingLogger:
    def __init__(self):
        self.records: list[tuple[str, str, dict]] = []

    def __getattr__(self, level):
        def _log(msg, **kw):
            self.records.append((level, msg, kw))
        return _log

    def events(self):
        return [msg for _, msg, _ in self.records]


def _gen(judge, logger=None, enabled=True):
    return GroundedGenerator(judge, logger or RecordingLogger(), enabled=enabled, corpus_max_chars=1000)


async def _run(generator, generate, *, max_retries=2, target="draft", sources=SOURCES):
    return await generator.run(
        generate=generate, question="63116 답변", sources=sources,
        max_retries=max_retries, target=target, request_id="r",
    )


class TestLoop:
    @pytest.mark.asyncio
    async def test_근거_있으면_판정_1회로_끝(self):
        """G1"""
        judge = FakeJudge([_verdict()])
        generate = FakeGenerate([GOOD])
        result = await _run(_gen(judge), generate)
        assert result.text == GOOD and result.attempts == 1 and not result.stripped
        assert len(judge.calls) == 1 and generate.feedbacks == [""]

    @pytest.mark.asyncio
    async def test_근거_없으면_사유를_넣어_재작성(self):
        """G2"""
        judge = FakeJudge([_verdict("1877-9900"), _verdict()])
        generate = FakeGenerate([BAD, GOOD])
        result = await _run(_gen(judge), generate)
        assert result.text == GOOD and result.attempts == 2
        assert '"1877-9900"' in generate.feedbacks[1]
        assert "[직전 글]\n" + BAD in generate.feedbacks[1]

    @pytest.mark.asyncio
    async def test_상한_초과면_문장_제거(self):
        """G3 — draft N=2: 생성 3회 후 제거."""
        judge = FakeJudge([_verdict("1877-9900")] * 3)
        generate = FakeGenerate([BAD, BAD, BAD])
        logger = RecordingLogger()
        result = await _run(_gen(judge, logger), generate, max_retries=2)
        assert len(generate.feedbacks) == 3
        assert result.stripped and "1877-9900" not in result.text
        assert result.text == "안녕하세요. 감사합니다."
        assert "grounding sentences stripped" in logger.events()

    @pytest.mark.asyncio
    async def test_답변은_제거_후_비면_원문_유지(self):
        """G4"""
        judge = FakeJudge([_verdict(BAD), _verdict(BAD)])
        generate = FakeGenerate([BAD, BAD])
        result = await _run(_gen(judge), generate, max_retries=1, target="answer")
        assert result.text == BAD and not result.stripped

    @pytest.mark.asyncio
    async def test_초안은_제거_후_비면_빈_문자열(self):
        judge = FakeJudge([_verdict(BAD)])
        generate = FakeGenerate([BAD])
        result = await _run(_gen(judge), generate, max_retries=0, target="draft")
        assert result.text == "" and result.stripped

    @pytest.mark.asyncio
    async def test_판정_실패는_원문_유지(self):
        """G5 — fail-open."""
        logger = RecordingLogger()
        judge = FakeJudge(raises=RuntimeError("judge down"))
        generate = FakeGenerate([BAD])
        result = await _run(_gen(judge, logger), generate)
        assert result.text == BAD and not result.judged
        assert "grounding judge failed" in logger.events()

    @pytest.mark.asyncio
    async def test_low_만이면_재작성하지_않는다(self):
        """G6"""
        judge = FakeJudge([_verdict("감사합니다", severity="low")])
        generate = FakeGenerate([GOOD])
        result = await _run(_gen(judge), generate)
        assert result.attempts == 1 and generate.feedbacks == [""]

    @pytest.mark.asyncio
    async def test_근거에_글자_그대로_있는_주장은_재작성하지_않는다(self):
        """판정기 오판 보정 — '추가대출 가능 여부' 는 SOURCES 에 그대로 있다."""
        judge = FakeJudge([_verdict("추가대출 가능 여부")])
        generate = FakeGenerate([GOOD])
        result = await _run(_gen(judge), generate)
        assert result.attempts == 1 and generate.feedbacks == [""]
        assert result.text == GOOD and not result.stripped

    @pytest.mark.asyncio
    async def test_재작성_중_생성_실패면_현재_글에서_문장_제거(self):
        judge = FakeJudge([_verdict("1877-9900")])
        generate = FakeGenerate([BAD], raise_on=2)
        result = await _run(_gen(judge), generate)
        assert result.stripped and result.text == "안녕하세요. 감사합니다."


class TestSkip:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sources,enabled,judge", [
        ("", True, "fake"), ("   ", True, "fake"), (SOURCES, False, "fake"), (SOURCES, True, None),
    ])
    async def test_비활성_조건이면_판정_0회(self, sources, enabled, judge):
        """G7 / D-09"""
        fake = FakeJudge()
        generator = GroundedGenerator(
            fake if judge else None, RecordingLogger(), enabled=enabled, corpus_max_chars=1000,
        )
        generate = FakeGenerate([BAD])
        result = await _run(generator, generate, sources=sources)
        assert result.text == BAD and not result.judged
        assert fake.calls == []

    def test_active(self):
        assert _gen(FakeJudge()).active
        assert not _gen(FakeJudge(), enabled=False).active
        assert not GroundedGenerator(None, MagicMock(), enabled=True, corpus_max_chars=10).active


class TestJudgeInputs:
    @pytest.mark.asyncio
    async def test_힌트와_질문을_판정기에_넘긴다(self):
        """G8"""
        judge = FakeJudge([_verdict()])
        await _run(_gen(judge), FakeGenerate([BAD]))
        call = judge.calls[0]
        assert call["hints"] == ["전화번호 1877-9900"]
        assert call["question"] == "63116 답변" and call["generation"] == BAD

    @pytest.mark.asyncio
    async def test_코퍼스는_상한으로_자른다(self):
        judge = FakeJudge([_verdict()])
        generator = GroundedGenerator(judge, RecordingLogger(), enabled=True, corpus_max_chars=5)
        await _run(generator, FakeGenerate([GOOD]), sources="0123456789")
        assert judge.calls[0]["sources"] == "01234"


class TestLogging:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sources,enabled,judge,reason", [
        (SOURCES, False, "fake", "disabled"), (SOURCES, True, None, "no_judge"),
        ("  ", True, "fake", "no_sources"),
    ])
    async def test_skip_로그에_사유(self, sources, enabled, judge, reason):
        """Analysis G-1 / Design §6."""
        logger = RecordingLogger()
        generator = GroundedGenerator(
            FakeJudge() if judge else None, logger, enabled=enabled, corpus_max_chars=1000,
        )
        await _run(generator, FakeGenerate([BAD]), sources=sources)
        skipped = [kw for _, msg, kw in logger.records if msg == "grounding skipped"]
        assert skipped and skipped[0]["reason"] == reason

    @pytest.mark.asyncio
    async def test_판정_실패_로그는_타입과_스택만(self):
        """Analysis G-2 — 파싱 오류 메시지에 판정기 원출력이 실릴 수 있다."""
        logger = RecordingLogger()
        judge = FakeJudge(raises=ValueError('output: {"span": "대표번호 1877-9900"}'))
        await _run(_gen(judge, logger), FakeGenerate([GOOD]))
        failed = [kw for _, msg, kw in logger.records if msg == "grounding judge failed"]
        assert failed[0]["exception_type"] == "ValueError"
        assert failed[0]["stack"]
        dumped = json.dumps(logger.records, ensure_ascii=False, default=str)
        assert "1877-9900" not in dumped

    @pytest.mark.asyncio
    async def test_로그에_원문이_없다(self):
        """G9"""
        logger = RecordingLogger()
        judge = FakeJudge([_verdict("1877-9900")] * 3)
        await _run(_gen(judge, logger), FakeGenerate([BAD, BAD, BAD]))
        dumped = json.dumps(logger.records, ensure_ascii=False, default=str)
        assert "1877-9900" not in dumped
        assert "grounding judged" in logger.events()
        assert "grounding regenerated" in logger.events()
