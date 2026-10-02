"""근거 판정기에 넘기는 결정적 힌트 — 근거 문자열에서 찾지 못한 고위험 값.

Design Ref: draft-grounding-check v0.2 §3.2 (D-01).

v0.1 에서는 이 규칙이 차단을 결정했지만 "정해진 값이 어떤 질문에서는 나와도
된다" 는 피드백으로 **힌트 전용**이 됐다. 판정기는 힌트를 참고해 맥락상
적절한지 스스로 판단한다. 종류: 전화·URL·이메일·계좌·금리(%). 금액·날짜는
근거에서 계산된 값이 많아 제외한다.
"""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]]+")
_PHONE = re.compile(
    r"(?<![\d*●])(?:1[5-9]\d{2}[-.\s]?\d{4}"
    r"|(?:\+?82[-.\s]?)?0\d{1,2}[-.\s)]?\d{3,4}[-.\s]?\d{4})(?![\d*●])"
)
_ACCOUNT = re.compile(r"(?<![\d*●])\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,6})?(?![\d*●])")
_DATE_LIKE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_RATE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s?%")

_LABELS = {
    "phone": "전화번호", "url": "URL", "email": "이메일",
    "account": "계좌번호", "rate": "금리·비율",
}


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _norm_phone(raw: str) -> str:
    digits = _digits(raw)
    if raw.lstrip().lstrip("+").startswith("82") and len(digits) >= 11:
        return "0" + digits[2:]
    return digits


def _norm_url(raw: str) -> str:
    url = re.sub(r"^(?:https?://)?(?:www\.)?", "", raw.lower())
    return url.rstrip("/.,;:")


def _norm_rate(raw: str) -> str:
    return f"{float(raw.replace('%', '').strip()):g}%"


def _mask(text: str, span: tuple[int, int]) -> str:
    start, end = span
    return text[:start] + " " * (end - start) + text[end:]


class GroundingHintPolicy:
    @classmethod
    def extract(cls, text: str) -> list[tuple[str, str, str]]:
        """(kind, raw, normalized). 앞 종류가 잡은 범위는 뒤 종류에서 가린다."""
        found: list[tuple[str, str, str]] = []
        work = text or ""
        for kind, pattern, norm in (
            ("email", _EMAIL, str.lower),
            ("url", _URL, _norm_url),
            ("phone", _PHONE, _norm_phone),
            ("account", _ACCOUNT, _digits),
            ("rate", _RATE, _norm_rate),
        ):
            for match in list(pattern.finditer(work)):
                raw = match.group(0).strip()
                work = _mask(work, match.span())
                if kind == "account" and _DATE_LIKE.match(raw):
                    continue
                found.append((kind, raw, norm(raw)))
        return found

    @classmethod
    def unfound_values(cls, text: str, sources: str) -> list[str]:
        """근거에서 확인되지 않은 값 — `"전화번호 1877-9900"` 형태, 순서 유지·중복 제거."""
        source_values = {(k, n) for k, _, n in cls.extract(sources)}
        source_digits = _digits(sources or "")
        hints: list[str] = []
        for kind, raw, normalized in cls.extract(text):
            if (kind, normalized) in source_values:
                continue
            if kind in ("phone", "account") and normalized and normalized in source_digits:
                continue
            label = f"{_LABELS[kind]} {raw}"
            if label not in hints:
                hints.append(label)
        return hints
