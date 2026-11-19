"""LLM 해석 관련 도메인 예외."""


class UtilityLLMUnavailableError(RuntimeError):
    """관리자 유틸리티 LLM을 해석하지 못해 호출할 모델이 없다.

    UtilityLLMProviderPort.get()이 None을 돌려준 경우. 대체 모델이 없는
    호출부(예: 엑셀 분석 노드)는 이 예외로 실패 사유를 분명히 남긴다.
    """
