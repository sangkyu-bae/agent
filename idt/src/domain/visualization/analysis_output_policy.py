"""분석 텍스트 출력 새니타이저 (domain, 순수 규칙).

분석 노드는 자연어 분석 텍스트만 생성해야 하고, 차트 JSON 생성은 chart_builder가
전담한다. 프롬프트를 어기고 새어 나온 코드블록/JSON 페이로드를 제거해, 하류의
chart_router(숫자 토큰 휴리스틱)·evaluate_hallucination(자연어 평가)이 깨끗한
텍스트만 받도록 보장한다.

외부/LLM 의존 없는 순수 정책 (CLAUDE.md §2: domain 규칙).
"""
import re
from typing import Callable


class AnalysisOutputSanitizer:
    """분석 텍스트에서 코드블록/JSON 페이로드를 제거하는 순수 정책."""

    _FENCE_RE = re.compile(r"```.*?```", re.DOTALL)  # ```json...```, ```python...```
    _JSON_KEY_RE = re.compile(r'"[^"]+"\s*:')  # "type": 같은 JSON 키 신호

    def strip(self, text: str) -> str:
        """펜스 코드블록 + raw JSON(객체/객체배열)을 제거하고 정리한다.

        수치 배열([1, 2, 3])처럼 차트 원재료가 되는 신호는 보존한다.
        """
        if not text:
            return text
        cleaned = self._FENCE_RE.sub("", text)
        # 배열 먼저: 객체 배열 [{...}] 제거 후 객체 {...} 제거(잔여물 방지).
        cleaned = self._strip_json_arrays(cleaned)
        cleaned = self._strip_json_objects(cleaned)
        return cleaned.strip()

    def _strip_json_arrays(self, text: str) -> str:
        """객체를 포함한 […] 배열만 제거. 수치 배열은 보존."""
        return self._strip_balanced(text, "[", "]", lambda b: "{" in b)

    def _strip_json_objects(self, text: str) -> str:
        """JSON 키 신호를 가진 {…} 객체만 제거. 일반 중괄호는 보존."""
        return self._strip_balanced(
            text, "{", "}", lambda b: bool(self._JSON_KEY_RE.search(b))
        )

    @staticmethod
    def _strip_balanced(
        text: str, open_ch: str, close_ch: str, predicate: Callable[[str], bool]
    ) -> str:
        """open_ch..close_ch로 균형 잡힌 블록 중 predicate 만족분만 제거.

        닫힘을 못 찾거나(불균형) predicate 불만족이면 원문 보존(오탐 방지).
        """
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            if text[i] == open_ch:
                end = AnalysisOutputSanitizer._match_close(text, i, open_ch, close_ch)
                if end != -1 and predicate(text[i : end + 1]):
                    i = end + 1  # 블록 버림
                    continue
            out.append(text[i])
            i += 1
        return "".join(out)

    @staticmethod
    def _match_close(text: str, start: int, open_ch: str, close_ch: str) -> int:
        """start의 open_ch에 대응하는 close_ch 인덱스. 없으면 -1."""
        depth = 0
        for j in range(start, len(text)):
            if text[j] == open_ch:
                depth += 1
            elif text[j] == close_ch:
                depth -= 1
                if depth == 0:
                    return j
        return -1


# 결정 2: DI 아님 — 모듈 싱글톤으로 공용 사용.
ANALYSIS_OUTPUT_SANITIZER = AnalysisOutputSanitizer()
