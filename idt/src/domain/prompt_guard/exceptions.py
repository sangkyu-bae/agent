"""prompt-guard 도메인 예외 — Design Ref: §3.5·D4."""


class JudgeUnavailableError(Exception):
    """판정기 LLM 을 해석할 수 없음(기본 모델 미등록 등). 서비스는 fail-open 한다."""
