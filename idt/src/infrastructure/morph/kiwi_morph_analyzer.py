"""KiwiMorphAnalyzer: kiwipiepy 기반 한국어 형태소 분석기."""
from kiwipiepy import Kiwi

from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.domain.morph.schemas import MorphAnalysisResult, MorphToken


class KiwiMorphAnalyzer(MorphAnalyzerInterface):
    """kiwipiepy Kiwi 래퍼.

    Kiwi 인스턴스는 생성 비용이 높으므로 인스턴스당 1회만 생성한다.
    """

    def __init__(self) -> None:
        self._kiwi = Kiwi()

    def analyze(self, text: str) -> MorphAnalysisResult:
        """kiwipiepy로 형태소 분석을 수행하고 도메인 타입으로 변환한다.

        Args:
            text: 분석할 텍스트

        Returns:
            MorphAnalysisResult (MorphToken 튜플 포함)
        """
        raw_tokens = self._kiwi.tokenize(text)
        tokens = tuple(
            MorphToken(
                surface=tok.form,
                pos=tok.tag if isinstance(tok.tag, str) else tok.tag.name,
                start=tok.start,
                length=tok.len,
            )
            for tok in raw_tokens
        )
        return MorphAnalysisResult(tokens=tokens, text=text)
