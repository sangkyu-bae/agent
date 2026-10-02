"""게이트 워커 안내·카테고리 승격 규칙.

Design Ref: approval-gate-run-termination §3.3, §3.5 (B7, B8) + Act-1.
Act-1 실측(2026-09-30): 접두만으로는 도구 원문 "승인 전에 호출하지 마십시오" 를
이기지 못했다 → 설명 뒤 접미 + supervisor 규칙 블록을 더한다.
"""
import pytest

from src.domain.agent_builder.policies import GatedCategoryPolicy, GatedWorkerHintPolicy


class TestGatedWorkerHint:
    def test_게이트_워커는_앞뒤로_승인_안내를_붙인다(self):
        """B7 — 모델이 마지막에 읽는 문장이 도구의 금지 문구가 되지 않게 한다."""
        described = GatedWorkerHintPolicy.describe("승인 전에 호출하지 마십시오", gated=True)
        assert described.startswith("[승인 필요] 호출하면 즉시 실행되지 않고 담당자 승인함에 등록됩니다.")
        assert "승인 전에 호출하지 마십시오" in described
        assert described.endswith(GatedWorkerHintPolicy.SUFFIX)

    def test_비게이트_워커는_바이트_동일(self):
        assert GatedWorkerHintPolicy.describe("조회합니다", gated=False) == "조회합니다"

    def test_규칙_블록은_게이트_워커가_있을_때만(self):
        block = GatedWorkerHintPolicy.rule_block(has_gated_workers=True)
        assert block.startswith("\n\n[승인 게이트 규칙]")
        assert "승인 후 호출" in block and "반드시 호출" in block
        assert GatedWorkerHintPolicy.rule_block(has_gated_workers=False) == ""


class TestGatedCategory:
    @pytest.mark.parametrize(
        ("category", "gated", "expected"),
        [
            (None, True, ("action", True)),  # 미분류 + 게이트 → 암묵 action
            # Analysis G2: search/collect 노드에는 게이트가 없다 — 승인 필요면 승격
            ("collect", True, ("action", True)),
            ("search", True, ("action", True)),
            ("action", True, ("action", False)),  # 명시 action 은 implicit 아님
            ("analysis", True, ("analysis", False)),  # 도구 미호출 노드는 불변
            (None, False, (None, False)),  # 비게이트 불변
            ("collect", False, ("collect", False)),
        ],
    )
    def test_promote(self, category, gated, expected):
        """B8"""
        assert GatedCategoryPolicy.promote(category, gated=gated) == expected
