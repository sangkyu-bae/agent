"""CitationFinalizePolicy·EvidenceLocator — answer-citation §3.2 (D-06~D-08)."""

from src.domain.answer_citation.models import RegisteredChunk
from src.domain.answer_citation.parser import CitationMarkerParser
from src.domain.answer_citation.policy import CitationFinalizePolicy, EvidenceLocator
from src.domain.hallucination.citation_check import CitationCheck

CHUNKS = {
    n: RegisteredChunk(
        marker=n,
        chunk_id=f"ch-{n}",
        document_id=f"doc-{n}",
        page=n,
        text=f"청크{n} 본문입니다. 근거 문장 {n}번이 여기에 있습니다.",
    )
    for n in range(1, 6)
}


def _finalize(
    text: str, supported: dict[int, str] | None = None, *, judged=True, evidence=None
):
    """supported: marker → evidence. 판정 대상 쌍은 원문 그대로에서 추출한다."""
    norm = CitationMarkerParser.normalize(text)
    pairs = CitationMarkerParser.pairs(norm, set(CHUNKS))
    supported = supported or {}
    checks = tuple(
        CitationCheck(
            p.pair_id,
            p.marker in supported,
            (evidence or {}).get(p.marker, supported.get(p.marker, "")),
        )
        for p in pairs
    )
    return CitationFinalizePolicy.finalize(
        text, chunks=CHUNKS, pairs=pairs, checks=checks, judged=judged
    )


class TestRenumbering:
    def test_rejected_markers_removed_and_rest_renumbered_in_order(self):
        out = _finalize(
            "가는 맞습니다[2][4][5]. 나도 맞습니다[5].",
            {2: "근거 문장 2번", 5: "근거 문장 5번"},
        )
        assert out.text == "가는 맞습니다[1][2]. 나도 맞습니다[2]."
        assert out.status == "verified"
        assert [(c.no, c.marker, c.chunk_id) for c in out.citations] == [
            (1, 2, "ch-2"),
            (2, 5, "ch-5"),
            (2, 5, "ch-5"),
        ]
        assert out.citations[0].page == 2
        assert out.citations[0].sentence == "가는 맞습니다."

    def test_markers_not_in_registry_are_left_as_text(self):
        out = _finalize("참고[9] 사항입니다[1].", {1: "근거 문장 1번"})
        assert out.text == "참고[9] 사항입니다[1]."

    def test_space_before_removed_marker_is_dropped(self):
        out = _finalize("가는 틀립니다 [3]. 나는 맞습니다 [1].", {1: "근거 문장 1번"})
        assert out.text == "가는 틀립니다. 나는 맞습니다 [1]."


class TestStatus:
    def test_no_markers(self):
        out = _finalize("인용 없는 답변입니다.")
        assert (out.status, out.none_reason, out.citations) == (
            "none",
            "no_markers",
            (),
        )

    def test_all_rejected(self):
        out = _finalize("가[1]. 나[2].", {})
        assert (out.status, out.none_reason, out.text) == (
            "none",
            "all_rejected",
            "가. 나.",
        )

    def test_judge_failed_removes_all_known_markers(self):
        out = _finalize("가[1]. 나[2].", {1: "근거 문장 1번"}, judged=False)
        assert (out.status, out.none_reason, out.text) == (
            "none",
            "judge_failed",
            "가. 나.",
        )


class TestEvidence:
    def test_evidence_kept_when_found_in_chunk(self):
        out = _finalize("가[1].", {1: "근거 문장 1번이 여기에"})
        assert out.citations[0].evidence == "근거 문장 1번이 여기에"

    def test_evidence_none_when_not_in_chunk_but_citation_kept(self):
        out = _finalize("가[1].", {1: "청크에 없는 문장"})
        assert out.status == "verified"
        assert out.citations[0].evidence is None


class TestStrippedSentences:
    def test_sentence_removed_after_judging_drops_its_citation(self):
        judged_text = "가는 맞습니다[1]. 나는 지워집니다[2]."
        pairs = CitationMarkerParser.pairs(judged_text, set(CHUNKS))
        checks = tuple(CitationCheck(p.pair_id, True, "") for p in pairs)
        out = CitationFinalizePolicy.finalize(
            "가는 맞습니다[1].", chunks=CHUNKS, pairs=pairs, checks=checks, judged=True
        )
        assert [c.marker for c in out.citations] == [1]
        assert out.text == "가는 맞습니다[1]."


class TestEvidenceLocator:
    def test_ignores_whitespace_fffd_and_width(self):
        chunk = "가계대출 총량\n목표를 경상성장률� 이내로"
        assert EvidenceLocator.find("가계대출 총량 목표를 경상성장률 이내로", chunk)
        assert EvidenceLocator.find("ＡＢＣ", "abc ABC")

    def test_empty_or_missing(self):
        assert not EvidenceLocator.find("", "본문")
        assert not EvidenceLocator.find("없는 문장", "본문")


class TestWrongChunkEvidence:
    """벤치 발견(2026-11-21): 판정기가 다른 청크의 문장을 근거로 대며 supported 라고 답함."""

    def test_evidence_found_only_in_other_chunk_rejects_citation(self):
        out = _finalize("가[3].", {3: "근거 문장 2번이 여기에"})
        assert (out.status, out.none_reason, out.text) == ("none", "all_rejected", "가.")

    def test_evidence_found_nowhere_keeps_citation_without_evidence(self):
        out = _finalize("가[3].", {3: "어느 청크에도 없는 문장"})
        assert out.status == "verified"
        assert out.citations[0].evidence is None
