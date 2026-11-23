"""CitationRegistry — answer-citation-verification D-01·D-02."""

from src.application.answer_citation.registry import CitationRegistry


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _assign(reg, run, chunk, text="본문"):
    return reg.assign(run, chunk_id=chunk, document_id="d", page=3, text=text)


def test_numbers_start_at_one_and_same_chunk_keeps_number():
    reg = CitationRegistry()
    assert _assign(reg, "r1", "a") == 1
    assert _assign(reg, "r1", "b") == 2
    assert _assign(reg, "r1", "a") == 1
    chunks = reg.chunks("r1")
    assert sorted(chunks) == [1, 2]
    assert (chunks[1].chunk_id, chunks[1].page, chunks[1].text) == ("a", 3, "본문")


def test_runs_are_independent():
    reg = CitationRegistry()
    _assign(reg, "r1", "a")
    assert _assign(reg, "r2", "x") == 1
    assert reg.chunks("unknown") == {}


def test_missing_chunk_id_is_keyed_by_text():
    reg = CitationRegistry()
    assert reg.assign("r1", chunk_id=None, document_id=None, page=None, text="t1") == 1
    assert reg.assign("r1", chunk_id=None, document_id=None, page=None, text="t1") == 1
    assert reg.assign("r1", chunk_id=None, document_id=None, page=None, text="t2") == 2


def test_expired_runs_are_dropped():
    clock = _Clock()
    reg = CitationRegistry(ttl_seconds=10, clock=clock)
    _assign(reg, "r1", "a")
    clock.now = 11
    assert reg.chunks("r1") == {}


def test_oldest_runs_evicted_beyond_max():
    reg = CitationRegistry(max_runs=2)
    _assign(reg, "r1", "a")
    _assign(reg, "r2", "a")
    _assign(reg, "r3", "a")
    assert reg.chunks("r1") == {}
    assert reg.chunks("r3") != {}


def test_discard_and_returned_copy_is_detached():
    reg = CitationRegistry()
    _assign(reg, "r1", "a")
    reg.chunks("r1").clear()
    assert reg.chunks("r1") != {}
    reg.discard("r1")
    assert reg.chunks("r1") == {}
