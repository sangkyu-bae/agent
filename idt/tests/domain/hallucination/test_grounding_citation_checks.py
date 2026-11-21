"""GroundingVerdict.citation_checks — answer-citation-verification S5."""

from src.domain.hallucination.citation_check import CitationCheck
from src.domain.hallucination.grounding import GroundingVerdict, UnsupportedClaim


def test_default_is_empty_tuple():
    assert GroundingVerdict(unsupported_claims=()).citation_checks == ()


def test_excluding_found_in_keeps_citation_checks():
    checks = (CitationCheck("c1", True, "근거"),)
    verdict = GroundingVerdict(
        unsupported_claims=(UnsupportedClaim("6억 원", "근거 없음", "high"),),
        citation_checks=checks,
    )
    filtered = verdict.excluding_found_in("한도는 6억 원입니다")
    assert filtered.unsupported_claims == ()
    assert filtered.citation_checks == checks
