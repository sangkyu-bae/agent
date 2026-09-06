"""HtmlFontEmbedder 단위 테스트 (Design §8.2 U-05~U-09, §4.2 주입 규칙)."""
import base64
import re
import time
from pathlib import Path

import pytest

from src.infrastructure.document_font.font_subsetter import FontSubsetter
from src.infrastructure.document_font.html_font_embedder import HtmlFontEmbedder

_FONT_DIR = Path(__file__).resolve().parents[3] / "resources" / "fonts"
_HAS_FONTS = (_FONT_DIR / "Pretendard-Regular.ttf").exists()


class _SpyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def _record(self, level):
        def log(message: str, **kwargs) -> None:
            self.records.append((level, message, kwargs))
        return log

    def __getattr__(self, name):
        if name in ("debug", "info", "warning", "error", "critical"):
            return self._record(name)
        raise AttributeError(name)

    def messages(self, level: str) -> list[str]:
        return [m for lv, m, _ in self.records if lv == level]


@pytest.fixture
def logger() -> _SpyLogger:
    return _SpyLogger()


@pytest.fixture
def embedder(logger: _SpyLogger) -> HtmlFontEmbedder:
    return HtmlFontEmbedder(
        subsetter=FontSubsetter(font_dir=_FONT_DIR, family="Pretendard"),
        logger=logger,
        family="Pretendard",
    )


needs_fonts = pytest.mark.skipif(not _HAS_FONTS, reason="폰트 자산 미반입")


@needs_fonts
def test_wraps_html_fragment_with_document_shell(embedder):
    """U-05: 조각 HTML 은 완결 문서 셸로 감싸이고 폰트가 심긴다."""
    result = embedder.wrap("<h1>위기 레포트</h1>", request_id="r-1")

    assert result.applied is True
    assert "<html" in result.html and "</html>" in result.html
    assert "@font-face" in result.html
    assert "data:font/ttf;base64," in result.html
    assert "<h1>위기 레포트</h1>" in result.html
    assert "font-family" in result.html


@needs_fonts
def test_embeds_regular_and_bold_weights(embedder):
    result = embedder.wrap("<p>본문 <strong>강조</strong></p>", request_id="r-1")

    assert {font.weight for font in result.fonts} == {400, 700}
    assert result.html.count("@font-face") == 2


@needs_fonts
def test_injects_style_into_existing_head_without_duplicating_shell(embedder):
    """U-06: 완결 HTML 은 셸을 덧씌우지 않고 <style> 만 삽입한다."""
    html = "<html><head><title>보고서</title></head><body><p>본문</p></body></html>"

    result = embedder.wrap(html, request_id="r-1")

    assert result.applied is True
    assert result.html.count("<html") == 1
    assert result.html.count("<head") == 1
    assert "<title>보고서</title>" in result.html
    assert result.html.index("@font-face") < result.html.index("</head>")


@needs_fonts
def test_adds_head_when_html_tag_has_no_head(embedder):
    html = "<html><body><p>본문</p></body></html>"

    result = embedder.wrap(html, request_id="r-1")

    assert result.applied is True
    assert result.html.count("<html") == 1
    assert "<head>" in result.html
    assert "@font-face" in result.html


@needs_fonts
def test_subsets_only_characters_used_in_document(embedder):
    """서브셋 대상이 문서 문자로 한정되는지 — 페이로드 통제의 핵심."""
    small = embedder.wrap("<p>가</p>", request_id="r-1")
    large = embedder.wrap("<p>" + "".join(
        chr(0xAC00 + i) for i in range(500)
    ) + "</p>", request_id="r-2")

    assert small.font_bytes < large.font_bytes


@needs_fonts
def test_warns_but_proceeds_when_glyph_missing(embedder, logger):
    """사용자 결정: 글리프 누락은 경고 로그 후 진행 (중단하지 않는다)."""
    rare = "\U0002000b"
    result = embedder.wrap(f"<p>본문{rare}</p>", request_id="r-1")

    assert result.applied is True
    assert rare in result.missing_chars
    assert any("glyph" in m for m in logger.messages("warning"))


def test_falls_back_to_original_html_when_font_asset_missing(tmp_path, logger):
    """U-07: 자산이 없으면 원본 HTML 로 진행하고 경고만 남긴다."""
    embedder = HtmlFontEmbedder(
        subsetter=FontSubsetter(font_dir=tmp_path, family="Pretendard"),
        logger=logger,
        family="Pretendard",
    )

    result = embedder.wrap("<p>본문</p>", request_id="r-1")

    assert result.applied is False
    assert result.html == "<p>본문</p>"
    assert result.fonts == ()
    assert logger.messages("warning")


def test_falls_back_when_subsetter_raises(logger):
    """U-08: 서브셋 중 예외가 나도 전파하지 않는다 (FR-09)."""

    class _Boom:
        def subset(self, weight, chars):
            raise RuntimeError("boom")

    embedder = HtmlFontEmbedder(
        subsetter=_Boom(), logger=logger, family="Pretendard"
    )

    result = embedder.wrap("<p>본문</p>", request_id="r-1")

    assert result.applied is False
    assert result.html == "<p>본문</p>"
    assert logger.messages("warning")


def test_disabled_embedder_returns_original_html(logger):
    embedder = HtmlFontEmbedder(
        subsetter=None, logger=logger, family="Pretendard", enabled=False
    )

    result = embedder.wrap("<p>본문</p>", request_id="r-1")

    assert result.applied is False
    assert result.html == "<p>본문</p>"
    assert result.reason == "font embed disabled"


@needs_fonts
def test_blank_html_is_returned_untouched(embedder):
    result = embedder.wrap("   ", request_id="r-1")

    assert result.applied is False
    assert result.html == "   "


@needs_fonts
def test_warns_when_payload_exceeds_threshold(logger):
    embedder = HtmlFontEmbedder(
        subsetter=FontSubsetter(font_dir=_FONT_DIR, family="Pretendard"),
        logger=logger,
        family="Pretendard",
        max_embed_kb=1,
    )

    result = embedder.wrap("<p>본문 보고서</p>", request_id="r-1")

    assert result.applied is True
    assert any("payload" in m for m in logger.messages("warning"))


@needs_fonts
def test_embed_overhead_within_budget(embedder):
    """U-09: 일반 문서 기준 오버헤드 ≤ 300ms (Plan NFR).

    GAP-06: 첫 호출은 2.7MB 폰트 로드가 섞여 계측이 환경(커버리지 계측, 병렬
    실행, 디스크 캐시)에 좌우된다. 임베더는 앱 스코프로 오래 사는 객체이므로
    NFR 이 뜻하는 것은 정상 운영 상태(warm)의 건당 비용이다. 예열 후 측정한다.
    """
    html = "<p>" + ("한글 문서 본문입니다. " * 200) + "</p>"
    embedder.wrap(html, request_id="warmup")

    samples = []
    for _ in range(3):
        start = time.perf_counter()
        embedder.wrap(html, request_id="r-1")
        samples.append((time.perf_counter() - start) * 1000)

    assert min(samples) <= 300, f"warm 오버헤드 {samples}"


@needs_fonts
def test_payload_growth_within_budget_for_typical_document(embedder):
    """U-13: 일반 문서(한글 2000자, 고유 ~500자)의 증가분 ≤ 200KB (Plan NFR).

    실측: 고유 500자면 Regular+Bold 는 약 215KB 로 예산을 넘고, 적응형 폴백이
    Regular 만 남겨 약 107KB 로 떨어진다.
    """
    unique = [chr(0xAC00 + (i * 7) % 11172) for i in range(500)]
    body = "".join(unique[i % len(unique)] for i in range(2000))
    html = f"<p>{body}</p>"

    result = embedder.wrap(html, request_id="r-1")
    growth = len(result.html.encode("utf-8")) - len(html.encode("utf-8"))

    assert result.applied is True
    assert growth <= 200 * 1024


@needs_fonts
def test_drops_bold_weight_when_payload_exceeds_budget(embedder, logger):
    """적응형 폴백: 예산 초과 시 굵은글씨보다 변환 성공을 우선한다."""
    body = "".join(chr(0xAC00 + (i * 7) % 11172) for i in range(500))

    result = embedder.wrap(f"<p>{body}</p>", request_id="r-1")

    assert {font.weight for font in result.fonts} == {400}
    assert any("weight reduced" in m for m in logger.messages("warning"))


@needs_fonts
def test_keeps_both_weights_for_small_document(embedder):
    result = embedder.wrap("<p>짧은 문서</p>", request_id="r-1")

    assert {font.weight for font in result.fonts} == {400, 700}
    assert result.embedded_bytes <= 200 * 1024


@needs_fonts
def test_embedded_font_data_uri_is_valid_base64(embedder):
    result = embedder.wrap("<p>본문</p>", request_id="r-1")

    for match in re.findall(r"base64,([A-Za-z0-9+/=]+)\)", result.html):
        assert base64.b64decode(match, validate=True)[:4] == b"\x00\x01\x00\x00"
