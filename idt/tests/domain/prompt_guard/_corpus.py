"""prompt-guard 코퍼스 로더 (Design §8.1 — tests/fixtures/prompt_guard/*.txt).

한 줄 한 케이스, `#` 시작 줄과 빈 줄은 무시. `\\uXXXX` 표기는 실제 문자로 바꾼다
(zero-width 같은 비가시 문자를 픽스처에 읽을 수 있게 적기 위함).
"""
import re
from pathlib import Path

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "prompt_guard"
_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def load_corpus(name: str) -> list[str]:
    lines = (_FIXTURES / f"{name}.txt").read_text(encoding="utf-8").splitlines()
    cases: list[str] = []
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        cases.append(_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw))
    return cases
