"""TestsetFileParser — CSV/XLSX 테스트셋 파싱 (eval-hub Design A5)."""
import io

import pandas as pd
import pytest

from src.infrastructure.eval_testset.testset_file_parser import parse_testset_file


def _csv(text: str) -> bytes:
    return text.encode("utf-8-sig")


def _xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


class TestCsv:
    def test_기본_컬럼_파싱(self):
        cases = parse_testset_file(
            _csv("question,ground_truth\nq1,a1\nq2,a2\n"), "t.csv"
        )
        assert cases == [
            {"question": "q1", "ground_truth": "a1"},
            {"question": "q2", "ground_truth": "a2"},
        ]

    def test_한글_별칭_컬럼(self):
        cases = parse_testset_file(_csv("질문,정답\nq1,a1\n"), "t.csv")
        assert cases == [{"question": "q1", "ground_truth": "a1"}]

    def test_답변_별칭도_ground_truth(self):
        cases = parse_testset_file(_csv("질문,답변\nq1,a1\n"), "t.csv")
        assert cases[0]["ground_truth"] == "a1"

    def test_ground_truth_없는_행은_None(self):
        cases = parse_testset_file(_csv("question,ground_truth\nq1,\n"), "t.csv")
        assert cases == [{"question": "q1", "ground_truth": None}]

    def test_질문_빈_행_스킵(self):
        cases = parse_testset_file(
            _csv("question,ground_truth\n,skip\nq1,a1\n"), "t.csv"
        )
        assert len(cases) == 1

    def test_question_컬럼_없으면_ValueError(self):
        with pytest.raises(ValueError):
            parse_testset_file(_csv("a,b\n1,2\n"), "t.csv")

    def test_유효행_0건이면_ValueError(self):
        with pytest.raises(ValueError):
            parse_testset_file(_csv("question,ground_truth\n"), "t.csv")


class TestXlsx:
    def test_엑셀_파싱(self):
        data = _xlsx([{"question": "q1", "ground_truth": "a1"}])
        cases = parse_testset_file(data, "t.xlsx")
        assert cases == [{"question": "q1", "ground_truth": "a1"}]

    def test_한글_별칭(self):
        data = _xlsx([{"질문": "q1", "정답": "a1"}])
        cases = parse_testset_file(data, "t.xlsx")
        assert cases == [{"question": "q1", "ground_truth": "a1"}]


class TestExtension:
    def test_미지원_확장자_ValueError(self):
        with pytest.raises(ValueError):
            parse_testset_file(b"x", "t.pdf")
