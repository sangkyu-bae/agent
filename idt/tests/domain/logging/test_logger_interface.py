"""Tests for LoggerInterface ABC."""

import pytest
from abc import ABC

from src.domain.logging.interfaces import LoggerInterface


class TestLoggerInterface:
    """LoggerInterface ABC 테스트."""

    def test_logger_interface_is_abstract_class(self):
        """LoggerInterface는 ABC를 상속해야 한다."""
        assert issubclass(LoggerInterface, ABC)

    def test_logger_interface_cannot_be_instantiated(self):
        """LoggerInterface는 직접 인스턴스화할 수 없다."""
        with pytest.raises(TypeError):
            LoggerInterface()

    def test_logger_interface_has_debug_method(self):
        """LoggerInterface는 debug 메서드를 정의해야 한다."""
        assert hasattr(LoggerInterface, "debug")
        assert callable(getattr(LoggerInterface, "debug", None))

    def test_logger_interface_has_info_method(self):
        """LoggerInterface는 info 메서드를 정의해야 한다."""
        assert hasattr(LoggerInterface, "info")
        assert callable(getattr(LoggerInterface, "info", None))

    def test_logger_interface_has_warning_method(self):
        """LoggerInterface는 warning 메서드를 정의해야 한다."""
        assert hasattr(LoggerInterface, "warning")
        assert callable(getattr(LoggerInterface, "warning", None))

    def test_logger_interface_has_error_method(self):
        """LoggerInterface는 error 메서드를 정의해야 한다."""
        assert hasattr(LoggerInterface, "error")
        assert callable(getattr(LoggerInterface, "error", None))

    def test_logger_interface_has_critical_method(self):
        """LoggerInterface는 critical 메서드를 정의해야 한다."""
        assert hasattr(LoggerInterface, "critical")
        assert callable(getattr(LoggerInterface, "critical", None))

    def test_concrete_class_must_implement_all_methods(self):
        """구현 클래스는 모든 추상 메서드를 구현해야 한다."""

        class IncompleteLogger(LoggerInterface):
            def debug(self, message: str, **kwargs) -> None:
                pass

        with pytest.raises(TypeError):
            IncompleteLogger()

    def test_concrete_class_with_all_methods_can_be_instantiated(self):
        """모든 메서드를 구현한 클래스는 인스턴스화 가능하다."""

        class CompleteLogger(LoggerInterface):
            def debug(self, message: str, **kwargs) -> None:
                pass

            def info(self, message: str, **kwargs) -> None:
                pass

            def warning(self, message: str, **kwargs) -> None:
                pass

            def error(self, message: str, exception: Exception | None = None, **kwargs) -> None:
                pass

            def critical(self, message: str, exception: Exception | None = None, **kwargs) -> None:
                pass

        logger = CompleteLogger()
        assert isinstance(logger, LoggerInterface)
