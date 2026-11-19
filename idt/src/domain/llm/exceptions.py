"""LLM 해석 관련 도메인 예외."""


class UtilityLLMUnavailableError(RuntimeError):
    """관리자 유틸리티 LLM을 해석하지 못해 호출할 모델이 없다.

    UtilityLLMProviderPort.get()이 None을 돌려준 경우. 대체 모델이 없는
    호출부(예: 엑셀 분석 노드)는 이 예외로 실패 사유를 분명히 남긴다.
    """


class EmptyLLMResponseError(RuntimeError):
    """LLM 응답에 텍스트가 없다 (claude-agent-e2e-fixes Check G-1).

    thinking 상시 모델이 출력 한도를 추론에 다 써 text가 비는 경우가 대표적이다.
    빈 답을 하류(환각 검사 등)로 넘기면 원인과 무관한 오류가 나므로, 호출부는
    이 예외로 원인(출력 한도 도달 여부)을 분명히 남기고 재시도하지 않는다.
    """

    @classmethod
    def from_stop_reason(cls, stop_reason: str | None) -> "EmptyLLMResponseError":
        if stop_reason == "max_tokens":
            return cls(
                "분석 모델이 출력 한도에 도달해 답을 만들지 못했습니다 "
                "(관리자 LLM 모델 설정의 '최대 출력 토큰'을 늘려 주세요)"
            )
        reason = stop_reason or "없음"
        return cls(f"분석 모델이 빈 응답을 돌려줬습니다 (stop_reason={reason})")
