"""EvalPolicy 단위 테스트 (agent-eval-gate Design §3-2)."""
import pytest

from src.domain.eval.policies import EvalPolicy


class TestValidateComment:
    def test_None은_통과(self):
        EvalPolicy.validate_comment(None)

    def test_정상_코멘트_통과(self):
        EvalPolicy.validate_comment("답변이 정확했어요")

    def test_경계_500자_통과(self):
        EvalPolicy.validate_comment("가" * 500)

    def test_초과_거부(self):
        with pytest.raises(ValueError):
            EvalPolicy.validate_comment("가" * 501)


class TestSatisfaction:
    def test_정상_비율(self):
        assert EvalPolicy.satisfaction(up=8, down=2) == 0.8

    def test_전부_up이면_1(self):
        assert EvalPolicy.satisfaction(up=5, down=0) == 1.0

    def test_전부_down이면_0(self):
        assert EvalPolicy.satisfaction(up=0, down=3) == 0.0

    def test_평가_0건이면_None(self):
        assert EvalPolicy.satisfaction(up=0, down=0) is None
