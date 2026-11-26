"""리포트 도메인 — 섹션별 근거 표 · 머리 사실 · 상태 규칙 (design §2.3, §3.3, §10)."""

from datetime import date

from src.domain.market_analysis.report import (
    SECTION_EVIDENCE,
    SECTION_TITLES,
    EvidenceKey,
    ReportStatus,
    ReportStatusPolicy,
    SectionStatus,
    header_facts_from_quote,
)
from src.domain.market_analysis.value_objects import AgentRole


def test_every_section_has_evidence_and_title():
    assert set(SECTION_EVIDENCE) == set(AgentRole.section_roles())
    assert set(SECTION_TITLES) >= set(AgentRole.section_roles())
    assert SECTION_EVIDENCE[AgentRole.SECTION_TECHNICAL] == (
        EvidenceKey.QUOTE,
        EvidenceKey.DAILY,
        EvidenceKey.INDICATORS,
    )
    assert EvidenceKey.INVESTOR in SECTION_EVIDENCE[AgentRole.SECTION_FLOW]
    assert EvidenceKey.DART_FINANCIALS in SECTION_EVIDENCE[AgentRole.SECTION_FINANCIAL]
    assert EvidenceKey.RESEARCH in SECTION_EVIDENCE[AgentRole.SECTION_COMPANY]
    assert EvidenceKey.NEWS in SECTION_EVIDENCE[AgentRole.SECTION_NEWS]


def test_header_facts_come_from_quote_payload_only():
    quote = {
        "symbol": "005930",
        "price": "70000",
        "change": "-500",
        "change_rate": "-0.71",
        "volume": 12345678,
        "as_of": "2026-11-26T02:00:00",
    }
    signals = ({"rule": "volume_spike", "values": {"ratio": 3.1}},)
    h = header_facts_from_quote(
        symbol="005930",
        name="삼성전자",
        quote=quote,
        signals=signals,
        provisional=True,
        trade_date=date(2026, 11, 26),
    )
    assert (h.price, h.change, h.change_rate, h.volume) == (
        "70000",
        "-500",
        "-0.71",
        12345678,
    )
    assert h.provisional is True and h.signals == signals
    d = h.to_dict()
    assert d["price"] == "70000" and d["trade_date"] == "2026-11-26"
    text = h.render()
    assert "삼성전자(005930)" in text and "70000" in text and "미확정" in text


def test_header_facts_missing_price_is_none():
    for bad in (None, {}, {"price": ""}, "text"):
        assert (
            header_facts_from_quote(
                symbol="1",
                name="x",
                quote=bad,
                signals=(),
                provisional=False,
                trade_date=date(2026, 11, 26),
            )
            is None
        )


def _sections(*statuses):
    return dict(zip(AgentRole.section_roles(), statuses, strict=False))


def test_status_policy():
    all_done = _sections(*[SectionStatus.DONE] * 6)
    assert (
        ReportStatusPolicy.decide(
            quote_ok=True, sections=all_done, strategy_ok=True, summary_ok=True
        )
        is ReportStatus.DONE
    )
    one_failed = {**all_done, AgentRole.SECTION_NEWS: SectionStatus.FAILED}
    assert (
        ReportStatusPolicy.decide(
            quote_ok=True, sections=one_failed, strategy_ok=True, summary_ok=True
        )
        is ReportStatus.PARTIAL
    )
    assert (
        ReportStatusPolicy.decide(
            quote_ok=True, sections=all_done, strategy_ok=False, summary_ok=True
        )
        is ReportStatus.PARTIAL
    )
    assert (
        ReportStatusPolicy.decide(
            quote_ok=False, sections={}, strategy_ok=False, summary_ok=False
        )
        is ReportStatus.FAILED
    )


def test_complete_report_means_strategy_and_summary_exist():
    assert ReportStatusPolicy.ready_for_judgement(ReportStatus.DONE, strategy_ok=True)
    assert ReportStatusPolicy.ready_for_judgement(
        ReportStatus.PARTIAL, strategy_ok=True
    )
    assert not ReportStatusPolicy.ready_for_judgement(
        ReportStatus.PARTIAL, strategy_ok=False
    )
    assert not ReportStatusPolicy.ready_for_judgement(
        ReportStatus.FAILED, strategy_ok=True
    )
