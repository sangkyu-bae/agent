"""PlaceholderStreamRestorer 단위 테스트 — Design §4.5 (FR-09)."""

from langchain_core.messages import HumanMessage
from src.application.pii_masking.stream_restorer import PlaceholderStreamRestorer

from tests.application.pii_masking._support import make_masker, make_service

PHONE = "010-1234-5678"


def _restorer(mode: str = "on"):
    masker = make_masker(mode)
    scope = masker.new_scope()
    masker.mask_messages([HumanMessage(content=f"{PHONE} hong@example.com")], scope)
    return PlaceholderStreamRestorer(make_service(mode), scope)


def test_restore_whole_text_restores_and_redacts_orphan():
    restorer = _restorer()
    assert restorer.restore("[PHONE_1] 와 [EMAIL_9]") == f"{PHONE} 와 [REDACTED_EMAIL]"


def test_restore_shadow_returns_text_unchanged():
    assert _restorer(mode="shadow").restore("[PHONE_1]") == "[PHONE_1]"


def _replay(restorer, chunks, key="run-1"):
    out = [restorer.feed(key, chunk) for chunk in chunks]
    out.append(restorer.flush(key))
    return out


def test_feed_split_placeholder_never_emits_fragment():
    out = _replay(
        _restorer(), ["", "[PH", "ONE", "_1]", " 로 ", "전송했", "습니다", ""]
    )
    assert "".join(out) == f"{PHONE} 로 전송했습니다"
    assert not any("[" in piece or "PH" in piece for piece in out)


def test_feed_one_character_chunks_restores_exactly():
    text = "연락처 [PHONE_1], 메일 [EMAIL_1] 입니다"
    out = _replay(_restorer(), list(text))
    assert "".join(out) == f"연락처 {PHONE}, 메일 hong@example.com 입니다"
    assert not any("[" in piece for piece in out)


def test_feed_parallel_runs_buffers_are_independent():
    restorer = _restorer()
    a1 = restorer.feed("a", "A [PHO")
    b1 = restorer.feed("b", "B [EMA")
    a2 = restorer.feed("a", "NE_1]")
    b2 = restorer.feed("b", "IL_1]")
    assert (a1 + a2, b1 + b2) == (f"A {PHONE}", "B hong@example.com")


def test_feed_non_placeholder_bracket_emitted_without_delay():
    restorer = _restorer()
    assert restorer.feed("r", "참고 [1] 문서") == "참고 [1] 문서"


def test_flush_incomplete_tail_emitted_as_is():
    restorer = _restorer()
    assert restorer.feed("r", "끝 [PHO") == "끝 "
    assert restorer.flush("r") == "[PHO"


def test_flush_unknown_key_returns_empty():
    assert _restorer().flush("missing") == ""


def test_feed_orphan_placeholder_redacted():
    out = _replay(_restorer(), ["값 [PHONE", "_9] 끝"])
    assert "".join(out) == "값 [REDACTED_PHONE] 끝"


def test_feed_shadow_mode_passes_chunks_through():
    restorer = _restorer(mode="shadow")
    assert restorer.feed("r", "[PH") == "[PH"
    assert restorer.flush("r") == ""
