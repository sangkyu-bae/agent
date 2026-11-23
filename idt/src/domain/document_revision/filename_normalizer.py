"""파일명 정규화 — 버전·날짜·개정 꼬리표를 떼어 같은 문서의 판본끼리 비교한다.

Design Ref: document-revision §10.4 — 부서 특화 단어 없이 일반 패턴만 쓴다
(USER-SCENARIOS: 특화 vs 일반화 충돌 시 일반화).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# 확장자: 글자를 하나 이상 포함해야 한다 ("규정 2026.11" 의 ".11" 은 확장자가 아님)
_EXTENSION = re.compile(r"\.(?=[a-z0-9]*[a-z])[a-z0-9]{1,5}$")
_SEPARATORS = re.compile(r"[\s_\-.·,~+()\[\]{}【】<>「」『』]+")

_NOISE_WORDS = frozenset(
    {
        "개정본", "개정", "수정본", "수정", "최종본", "최종", "최신본", "최신",
        "사본", "초안", "final", "revised", "revision", "rev", "draft", "copy",
        "new", "latest", "ver", "version",
    }
)
_VERSION_TOKEN = re.compile(r"^(v|ver|version|rev|r)\d+$")
_NUMBER_TOKEN = re.compile(r"^\d+$")
_ORDINAL_TOKEN = re.compile(r"^(제)?\d+차$")

_GLUED_VERSION = re.compile(r"(?<=[가-힣a-z])(v|ver|rev)\d+$")
_GLUED_DIGITS = re.compile(r"(?<=\D)\d+$")
_GLUED_NOISE = re.compile(r"(?<=.)(개정본|개정|수정본|수정|최종본|최종|최신본|최신)$")


def _base(filename: str) -> str:
    text = unicodedata.normalize("NFKC", filename).strip().lower()
    return _EXTENSION.sub("", text)


def _is_noise(token: str) -> bool:
    return bool(
        token in _NOISE_WORDS
        or _VERSION_TOKEN.match(token)
        or _NUMBER_TOKEN.match(token)
        or _ORDINAL_TOKEN.match(token)
    )


def _strip_glued(token: str) -> str:
    previous = None
    while previous != token:
        previous = token
        for pattern in (_GLUED_VERSION, _GLUED_DIGITS, _GLUED_NOISE):
            token = pattern.sub("", token)
    return token


def normalize_filename(filename: str) -> str:
    """판본 표시를 걷어낸 비교용 이름. 전부 걷히면 확장자만 뗀 이름으로 낙하."""
    base = _base(filename)
    kept: list[str] = []
    for token in _SEPARATORS.split(base):
        if not token or _is_noise(token):
            continue
        token = _strip_glued(token)
        if token and not _is_noise(token):
            kept.append(token)
    if kept:
        return " ".join(kept)
    return " ".join(t for t in _SEPARATORS.split(base) if t)


def filename_similarity(a: str, b: str) -> float:
    """정규화 이름이 같으면 1.0, 아니면 SequenceMatcher 비율 (0.0~1.0)."""
    na, nb = normalize_filename(a), normalize_filename(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()
