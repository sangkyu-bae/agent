"""후보 수집 · 신호 스캔 (design §2.2 ③④, DD11·DD12)."""

from __future__ import annotations

import dataclasses

from src.application.market_analysis.candidates import (
    collect_candidates,
    scan_candidates,
)
from src.domain.market_analysis.round import SignaledCandidate
from src.domain.market_analysis.setting import MarketAnalysisSetting

from .fakes import FakeTools

SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(),
    kis_server_id="kis-1",
    run_as_user_id="7",
    ranking_kinds=("volume", "fluctuation"),
    ranking_limit=30,
    condition_seqs=("0",),
)


def _rank(kind_symbols):
    def respond(args):
        return {
            "kind": args["kind"],
            "entries": [
                {"symbol": s, "name": f"종목{s}", "volume": int(s)}
                for s in kind_symbols[args["kind"]]
            ],
        }

    return respond


async def test_collect_unions_rankings_and_condition_search():
    tools = FakeTools()
    tools.payloads["get_rankings"] = _rank(
        {"volume": ["000010", "000020"], "fluctuation": ["000020", "000030"]}
    )
    tools.payloads["run_condition_search"] = {
        "seq": "0",
        "hits": [{"symbol": "000040", "name": "조건종목", "volume": 7}],
    }
    candidates = await collect_candidates(tools, SETTING, request_id="r")
    assert list(candidates) == ["000010", "000020", "000030", "000040"]
    assert candidates["000040"].name == "조건종목"
    kinds = [c[2]["kind"] for c in tools.calls if c[1] == "get_rankings"]
    assert kinds == ["volume", "fluctuation"]
    assert all(c[2]["limit"] == 30 for c in tools.calls if c[1] == "get_rankings")
    # 순위를 KIS 쪽에서부터 주식으로 채운다 — 거래량 30위 중 ETF·ETN 24 가 필터에서
    # 빠져 6개만 남던 문제 (KIS 대상 제외 조건 실측 2026-11-27)
    assert all(c[2]["stocks_only"] for c in tools.calls if c[1] == "get_rankings")


async def test_collect_survives_a_failed_source():
    tools = FakeTools()
    tools.payloads["get_rankings"] = _rank({"volume": ["000010"], "fluctuation": []})
    tools.fail.add("run_condition_search")
    candidates = await collect_candidates(tools, SETTING, request_id="r")
    assert list(candidates) == ["000010"]


async def test_scan_chunks_by_30_and_groups_signals_per_symbol():
    from src.domain.market_analysis.round import Candidate

    cands = {
        f"{i:06d}": Candidate(symbol=f"{i:06d}", name=f"n{i}", volume=i)
        for i in range(45)
    }
    tools = FakeTools()

    def scan(args):
        syms = args["symbols"]
        return {
            "signals": {
                "volume_spike": [
                    {
                        "symbol": syms[0],
                        "direction": "up",
                        "provisional": False,
                        "values": {"ratio": 3.0},
                    }
                ],
                "gap": [
                    {
                        "symbol": syms[0],
                        "direction": "down",
                        "provisional": True,
                        "values": {"change_pct": -3.1},
                    },
                    {
                        "symbol": syms[1],
                        "direction": "up",
                        "provisional": False,
                        "values": {"change_pct": 2.0},
                    },
                ],
            },
            "errors": [],
            "insufficient": [],
        }

    tools.payloads["scan_signals"] = scan
    signaled = await scan_candidates(tools, SETTING, cands, request_id="r")

    scans = [c[2] for c in tools.calls if c[1] == "scan_signals"]
    assert [len(s["symbols"]) for s in scans] == [30, 15]
    assert scans[0]["rules"] == list(SETTING.signal_rules)
    by = {s.symbol: s for s in signaled}
    assert set(by) == {"000000", "000001", "000030", "000031"}
    first = by["000000"]
    assert isinstance(first, SignaledCandidate) and first.name == "n0"
    assert sorted(s["rule"] for s in first.signals) == ["gap", "volume_spike"]
    assert {
        "rule": "gap",
        "direction": "down",
        "provisional": True,
        "values": {"change_pct": -3.1},
    } in first.signals


async def test_scan_failure_of_one_chunk_skips_only_that_chunk():
    from src.domain.market_analysis.round import Candidate

    cands = {
        f"{i:06d}": Candidate(symbol=f"{i:06d}", name="n", volume=0) for i in range(35)
    }
    tools = FakeTools()
    tools.payloads["scan_signals"] = lambda args: {
        "signals": {"gap": [{"symbol": args["symbols"][0]}]}
    }
    original = tools.call
    seen = {"scan": 0}

    async def first_chunk_fails(**kw):
        # 첫 묶음(000000~000029)만 오류, 두 번째 묶음(000030~)은 정상
        if kw["tool"] == "scan_signals":
            seen["scan"] += 1
            if seen["scan"] == 1:
                tools.fail.add("scan_signals")
                try:
                    return await original(**kw)
                finally:
                    tools.fail.discard("scan_signals")
        return await original(**kw)

    tools.call = first_chunk_fails
    signaled = await scan_candidates(tools, SETTING, cands, request_id="r")
    assert [s.symbol for s in signaled] == ["000030"]


async def test_every_chunk_failing_is_an_error_not_zero_signals():
    """실화면 확인(module-9): 오래된 KIS 컨테이너가 규칙을 모두 거부했는데
    회차가 '신호 0건'으로 끝났다 — 전부 실패면 오류로 올린다."""
    import pytest
    from src.application.market_analysis.candidates import ScanUnavailableError
    from src.domain.market_analysis.round import Candidate

    cands = {
        f"{i:06d}": Candidate(symbol=f"{i:06d}", name="n", volume=0) for i in range(35)
    }
    tools = FakeTools()
    tools.fail.add("scan_signals")
    tools.fail_code = "INVALID_ARGUMENT"
    with pytest.raises(ScanUnavailableError) as e:
        await scan_candidates(tools, SETTING, cands, request_id="r")
    assert e.value.code == "INVALID_ARGUMENT"
    assert await scan_candidates(tools, SETTING, {}, request_id="r") == []


async def test_collect_keeps_only_equities():
    tools = FakeTools()
    tools.payloads["get_rankings"] = {
        "entries": [
            {"symbol": "005930", "name": "삼성전자", "volume": 9, "group": "ST"},
            {
                "symbol": "252670",
                "name": "KODEX 200선물인버스2X",
                "volume": 8,
                "group": "EF",
            },
            {
                "symbol": "Q530107",
                "name": "삼성 인버스 ETN",
                "volume": 7,
                "group": "EN",
            },
            {"symbol": "0099X0", "name": "IBKS제25호스팩", "volume": 6, "group": "ST"},
            {"symbol": "000660", "name": "SK하이닉스", "volume": 5},  # 그룹 모름 → 남김
        ]
    }
    tools.payloads["run_condition_search"] = {
        "hits": [{"symbol": "069500", "name": "KODEX 200", "volume": 1, "group": "EF"}]
    }
    candidates = await collect_candidates(tools, SETTING, request_id="r")
    assert list(candidates) == ["005930", "000660"]
    assert candidates["005930"].group == "ST" and candidates["000660"].group is None
