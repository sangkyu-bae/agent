"""pii-masking 코퍼스 로더 (Design §8.2 — tests/fixtures/pii_masking/*.txt).

한 줄 한 케이스, `#` 시작 줄과 빈 줄은 무시. 필드 구분자는 ` | ` 이며
문장 안의 표 구분자(`|`)와 겹치지 않도록 앞쪽 필드만 나눈다.
"""
from pathlib import Path

from src.domain.pii_masking.schemas import PiiType

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "pii_masking"


def _lines(name: str) -> list[str]:
    raw = (_FIXTURES / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    return [ln for ln in raw if ln.strip() and not ln.lstrip().startswith("#")]


def load_benign() -> list[str]:
    return _lines("benign_ko")


def load_pii() -> list[tuple[PiiType, str, str]]:
    cases = []
    for line in _lines("pii_ko"):
        pii_type, value, sentence = line.split(" | ", 2)
        cases.append((PiiType(pii_type), value, sentence))
    return cases


def load_known_fp() -> list[tuple[PiiType, str, str]]:
    cases = []
    for line in _lines("known_fp"):
        pii_type, value, sentence, _reason = line.split(" | ", 3)
        cases.append((PiiType(pii_type), value, sentence))
    return cases
