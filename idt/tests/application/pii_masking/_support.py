"""pii_masking application 테스트 공용 픽스처 (mock 금지, 명시적 fake)."""

from src.application.pii_masking.message_masker import PiiMessageMasker
from src.application.pii_masking.pii_masking_service import PiiMaskingService
from src.application.pii_masking.schemas import PiiMaskingConfig
from src.infrastructure.pii_masking.regex_detectors import RegexPiiDetector

ALL_TYPES = "rrn,phone,email,card,account"


class NullLogger:
    def debug(self, message: str, **kwargs) -> None: ...
    def info(self, message: str, **kwargs) -> None: ...
    def warning(self, message: str, **kwargs) -> None: ...
    def error(self, message: str, **kwargs) -> None: ...
    def critical(self, message: str, **kwargs) -> None: ...


def make_service(mode: str = "on") -> PiiMaskingService:
    return PiiMaskingService(
        detector=RegexPiiDetector(),
        logger=NullLogger(),
        config=PiiMaskingConfig.from_settings(mode=mode, types_csv=ALL_TYPES),
    )


def make_masker(mode: str = "on") -> PiiMessageMasker:
    return PiiMessageMasker(make_service(mode))
