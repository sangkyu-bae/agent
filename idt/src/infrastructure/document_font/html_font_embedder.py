"""HtmlFontEmbedder — 변환 직전 HTML 에 한글 폰트를 심는다.

Design Ref: fix-doc-generator-korean-font §4.2 — 외부 MCP 변환 서버(WeasyPrint)에
한글 폰트가 없어 DejaVu Serif 로 폴백하고, 한글이 전부 GID 0(.notdef)로 떨어졌다.
서버를 고칠 수 없으므로 요청 HTML 자체를 self-contained 로 만든다.

Plan SC: 생성 PDF 의 한글 .notdef 비율 0% / 페이로드 증가분 ≤ 200KB.
"""
from __future__ import annotations

import re

from src.domain.document_font.policies import DocumentCharsetPolicy
from src.domain.document_font.schemas import EmbeddedFont, FontEmbedResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_DEFAULT_WEIGHTS = (400, 700)
_FALLBACK_STACK = "'Noto Sans KR', 'Malgun Gothic', sans-serif"

_HEAD_CLOSE_RE = re.compile(r"</\s*head\s*>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<\s*html\b[^>]*>", re.IGNORECASE)


class HtmlFontEmbedder:
    """HTML → 폰트가 임베드된 완결 HTML.

    실패는 예외가 아니라 폴백이다: 폰트 처리가 어긋나도 문서 생성 자체를
    막지 않고 원본 HTML 로 진행한다 (Plan FR-09).
    """

    def __init__(
        self,
        subsetter,
        logger: LoggerInterface,
        family: str,
        enabled: bool = True,
        weights: tuple[int, ...] = _DEFAULT_WEIGHTS,
        max_embed_kb: int = 200,
    ) -> None:
        self._subsetter = subsetter
        self._logger = logger
        self._family = family
        self._enabled = enabled
        self._weights = weights
        self._max_embed_bytes = max_embed_kb * 1024

    def wrap(self, html: str, request_id: str) -> FontEmbedResult:
        skip_reason = self._skip_reason(html)
        if skip_reason:
            return FontEmbedResult(html=html, reason=skip_reason)

        try:
            fonts = self._build_within_budget(html, request_id)
        except Exception as exc:  # 자산 누락·서브셋 실패 모두 폴백 (FR-09)
            self._logger.warning(
                "document font embed skipped",
                request_id=request_id,
                reason=str(exc),
            )
            return FontEmbedResult(html=html, reason=str(exc))

        result = FontEmbedResult(
            html=self._inject(html, self._build_css(fonts)),
            fonts=fonts,
            applied=True,
        )
        self._log_result(result, request_id)
        return result

    # ── 판단 ─────────────────────────────────────────────────────────────
    def _skip_reason(self, html: str) -> str:
        if not self._enabled:
            return "font embed disabled"
        if not html or not html.strip():
            return "empty html"
        return ""

    # ── 조립 ─────────────────────────────────────────────────────────────
    def _build_within_budget(
        self, html: str, request_id: str
    ) -> tuple[EmbeddedFont, ...]:
        """예산을 넘으면 weight 를 줄여 재서브셋한다 (적응형 폴백).

        한글은 음절마다 글리프가 있어 고유 자수가 곧 용량이다. 고유 500자
        문서면 Regular+Bold 가 약 215KB — 기본 예산 200KB 를 넘는다. 이때
        굵은글씨 품질보다 변환 성공을 우선해 Regular 만 남긴다.
        """
        chars = self._extract_chars(html)
        fonts = self._subset_all(chars, self._weights)
        if not self._over_budget(fonts) or len(self._weights) == 1:
            return fonts

        reduced = self._subset_all(chars, self._weights[:1])
        self._logger.warning(
            "document font weight reduced for payload budget",
            request_id=request_id,
            before_bytes=sum(len(f.data_uri) for f in fonts),
            after_bytes=sum(len(f.data_uri) for f in reduced),
            limit_bytes=self._max_embed_bytes,
        )
        return reduced

    def _subset_all(
        self, chars: frozenset[str], weights: tuple[int, ...]
    ) -> tuple[EmbeddedFont, ...]:
        return tuple(self._subsetter.subset(weight, chars) for weight in weights)

    def _over_budget(self, fonts: tuple[EmbeddedFont, ...]) -> bool:
        return sum(len(font.data_uri) for font in fonts) > self._max_embed_bytes

    @staticmethod
    def _extract_chars(html: str) -> frozenset[str]:
        return DocumentCharsetPolicy.extract_chars(html)

    def _build_css(self, fonts: tuple[EmbeddedFont, ...]) -> str:
        faces = "\n".join(
            "@font-face{"
            f"font-family:'{self._family}';"
            f"font-weight:{font.weight};"
            "font-style:normal;"
            f"src:url({font.data_uri}) format('truetype');"
            "}"
            for font in fonts
        )
        return (
            "<style>\n"
            f"{faces}\n"
            "html,body,table,th,td,li,p,h1,h2,h3,strong,em{"
            f"font-family:'{self._family}',{_FALLBACK_STACK};"
            "}\n"
            "</style>"
        )

    def _inject(self, html: str, style: str) -> str:
        """입력 HTML 형태별 주입 규칙 (Design §4.2, FR-06)."""
        if _HEAD_CLOSE_RE.search(html):
            return _HEAD_CLOSE_RE.sub(style + "</head>", html, count=1)

        html_open = _HTML_OPEN_RE.search(html)
        if html_open:
            head = f"<head><meta charset=\"utf-8\">{style}</head>"
            return html[: html_open.end()] + head + html[html_open.end():]

        return (
            "<html><head><meta charset=\"utf-8\">"
            f"{style}</head><body>{html}</body></html>"
        )

    # ── 로깅 ─────────────────────────────────────────────────────────────
    def _log_result(self, result: FontEmbedResult, request_id: str) -> None:
        if result.missing_chars:
            self._logger.warning(
                "document font glyph missing",
                request_id=request_id,
                missing_chars="".join(result.missing_chars),
                missing_count=len(result.missing_chars),
            )
        if result.embedded_bytes > self._max_embed_bytes:
            self._logger.warning(
                "document font payload exceeded",
                request_id=request_id,
                embedded_bytes=result.embedded_bytes,
                limit_bytes=self._max_embed_bytes,
            )
        self._logger.info(
            "document font embedded",
            request_id=request_id,
            family=self._family,
            weights=[font.weight for font in result.fonts],
            font_bytes=result.font_bytes,
            payload_bytes=len(result.html.encode("utf-8")),
        )
