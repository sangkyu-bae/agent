"""Logger Interface for Domain Layer.

이 인터페이스는 로깅 추상화를 정의합니다.
Infrastructure layer에서 구체적인 구현을 제공합니다.
"""

from abc import ABC, abstractmethod


class LoggerInterface(ABC):
    """로거 인터페이스.

    모든 로거 구현체는 이 인터페이스를 상속해야 합니다.
    """

    @abstractmethod
    def debug(self, message: str, **kwargs) -> None:
        """디버그 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        pass

    @abstractmethod
    def info(self, message: str, **kwargs) -> None:
        """정보 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs) -> None:
        """경고 레벨 로그 기록.

        Args:
            message: 로그 메시지
            **kwargs: 추가 컨텍스트 정보
        """
        pass

    @abstractmethod
    def error(self, message: str, exception: Exception | None = None, **kwargs) -> None:
        """에러 레벨 로그 기록.

        Args:
            message: 로그 메시지
            exception: 예외 객체 (스택 트레이스 포함 시)
            **kwargs: 추가 컨텍스트 정보
        """
        pass

    @abstractmethod
    def critical(self, message: str, exception: Exception | None = None, **kwargs) -> None:
        """치명적 에러 레벨 로그 기록.

        Args:
            message: 로그 메시지
            exception: 예외 객체 (스택 트레이스 포함 시)
            **kwargs: 추가 컨텍스트 정보
        """
        pass
