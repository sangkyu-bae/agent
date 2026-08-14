"""tool-recommender Design §8.4 — L3 골드셋 Recall 평가 (실 LLM).

**CI 제외.** 실제 LLM을 호출하므로 `-m llm`으로 명시 실행한다:

    pytest -m llm tests/infrastructure/tool_selection/test_goldset_recall.py -s

측정 항목 (Plan §3.2 / §4.1):
  - Recall  : 정답 도구가 최종 집합에서 누락되지 않는 비율. 목표 ≥ 95%
  - 감소율   : 후보 수 대비 최종 바인딩 도구 수
  - 지연     : elapsed_ms P95. 목표 < 1.5s

골드셋은 실측 데이터다 — Doc Convert MCP의 `list_tools` 응답 4건 + `TOOL_REGISTRY` 9건.
"""
import json
import os
import pathlib

import pytest
from dotenv import load_dotenv
from src.application.general_chat.tools import REQUIRED_TOOL_IDS
from src.config import settings
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_selection.schemas import ToolCandidate, ToolSource
from src.infrastructure.llm.llm_factory import LLMFactory
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.tool_selection.llm_tool_selector import LLMToolSelector

pytestmark = pytest.mark.llm

_GOLDSET = (
    pathlib.Path(__file__).resolve().parents[2]
    / "fixtures" / "tool_selection" / "goldset.json"
)
RECALL_TARGET = 0.95
LATENCY_P95_TARGET_MS = 1500


def _load() -> dict:
    return json.loads(_GOLDSET.read_text(encoding="utf-8"))


def _candidates(pool: list[dict]) -> list[ToolCandidate]:
    return [
        ToolCandidate(
            tool_id=p["tool_id"],
            name=p["name"],
            description=p["description"],
            source=ToolSource(p["source"]),
            server_name=p.get("server_name"),
        )
        for p in pool
    ]


def _ensure_api_key() -> bool:
    """프로덕션과 동일하게 .env를 os.environ에 로드한다.

    `LLMFactory._resolve_api_key`는 **환경변수**를 읽는데, pydantic-settings는
    `.env`를 읽어도 os.environ에 넣지 않는다. 실행 경로에서는 `api/main.py:20`의
    `load_dotenv()`가 이 역할을 한다 — 테스트도 같은 전제를 갖춰야 한다.
    """
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") and getattr(settings, "openai_api_key", ""):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    return bool(os.getenv("OPENAI_API_KEY"))


def _selector(top_k: int) -> LLMToolSelector:
    from datetime import datetime

    now = datetime.now()
    return LLMToolSelector(
        llm_factory=LLMFactory(),
        llm_model=LlmModel(
            id="tool-selector-eval",
            provider=settings.tool_selector_provider,
            model_name=settings.tool_selector_model_name,
            display_name="Tool Selector (eval)",
            description=None,
            api_key_env="OPENAI_API_KEY",
            max_tokens=None,
            is_active=True,
            is_default=False,
            created_at=now,
            updated_at=now,
        ),
        logger=StructuredLogger(name="goldset-eval", level=40),
        top_k=top_k,
        timeout_sec=max(settings.tool_selector_timeout_sec, 10.0),
    )


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((len(ordered) - 1) * pct)))
    return ordered[idx]


async def test_goldset_recall_and_reduction(capsys):
    if not _ensure_api_key():
        pytest.skip("OPENAI_API_KEY 미설정")
    doc = _load()
    pool = doc["candidate_pool"]
    cases = doc["cases"]
    candidates = _candidates(pool)
    selector = _selector(settings.tool_selector_top_k)

    misses: list[dict] = []
    selected_counts: list[int] = []
    latencies: list[int] = []
    fallbacks = 0

    for case in cases:
        result = await selector.select(
            case["query"], candidates,
            required_ids=REQUIRED_TOOL_IDS, request_id="goldset",
        )
        final = set(result.final_ids)
        missing = [t for t in case["expected_tool_ids"] if t not in final]
        selected_counts.append(len(result.final_ids))
        latencies.append(result.elapsed_ms)
        if result.fallback:
            fallbacks += 1
        if missing:
            misses.append({
                "query": case["query"],
                "missing": missing,
                "got": sorted(final),
                "reason": result.reason,
            })

    total_expected = sum(len(c["expected_tool_ids"]) for c in cases)
    total_missing = sum(len(m["missing"]) for m in misses)
    recall = (total_expected - total_missing) / total_expected
    avg_selected = sum(selected_counts) / len(selected_counts)

    with capsys.disabled():
        print(f"\n{'=' * 66}")
        print("골드셋 Recall 평가 (실 LLM)")
        print(f"{'=' * 66}")
        print(f"  모델          : {settings.tool_selector_model_name}")
        print(f"  후보 풀       : {len(candidates)}개")
        print(f"  케이스        : {len(cases)}건 (정답 도구 {total_expected}개)")
        print(f"  top_k         : {settings.tool_selector_top_k}")
        print("-" * 66)
        print(f"  Recall        : {recall:.1%}  (목표 {RECALL_TARGET:.0%})")
        print(f"  누락          : {total_missing}개 / {total_expected}개")
        print(f"  평균 바인딩   : {avg_selected:.1f}개  "
              f"({len(candidates)} → {avg_selected:.1f}, "
              f"{1 - avg_selected / len(candidates):.0%} 감소)")
        warm = latencies[1:] or latencies  # 첫 콜은 클라이언트 초기화 포함
        print(f"  지연 P95      : {_percentile(latencies, 0.95)}ms  "
              f"(목표 <{LATENCY_P95_TARGET_MS}ms)")
        print(f"    · 최초 콜   : {latencies[0]}ms (콜드스타트)")
        print(f"    · 중앙값    : {_percentile(latencies, 0.5)}ms")
        print(f"    · 평균      : {sum(latencies) // len(latencies)}ms")
        print(f"    · 최대      : {max(latencies)}ms")
        print(f"    · P95(웜)   : {_percentile(warm, 0.95)}ms")
        print(f"  폴백          : {fallbacks}건")
        if misses:
            print("-" * 66)
            print("  누락 상세:")
            for miss in misses:
                print(f"   · {miss['query']}")
                print(f"     기대: {miss['missing']}")
                print(f"     선택: {miss['got']}")
        print(f"{'=' * 66}\n")

    assert recall >= RECALL_TARGET, (
        f"Recall {recall:.1%} < 목표 {RECALL_TARGET:.0%} — 누락 {misses}"
    )
