"""문서 폰트 임베드 정책 — 순수 규칙만 담는다.

Design Ref: fix-doc-generator-korean-font §9.4 — 사용 문자 추출은 외부 의존이
없는 순수 규칙이므로 domain 에 둔다. 폰트 파일 IO·서브셋팅은 infrastructure.
"""
from __future__ import annotations

import html as html_module
import re

# 화면에 그려지지 않는 영역 — 서브셋 대상에서 제외한다.
_HIDDEN_BLOCK_RE = re.compile(
    r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>", re.DOTALL)


class DocumentCharsetPolicy:
    """HTML 에서 '실제로 그려지는 문자'만 뽑아낸다.

    태그명·속성값·주석·style/script 본문은 렌더링되지 않으므로 제외한다.
    이 집합이 곧 폰트 서브셋 대상이며, 여기서 빠지면 해당 글자가 .notdef 로
    떨어진다 (Plan SC: 생성 PDF 의 한글 .notdef 비율 0%).
    """

    @staticmethod
    def extract_chars(html: str) -> frozenset[str]:
        if not html or not html.strip():
            return frozenset()

        text = _HIDDEN_BLOCK_RE.sub(" ", html)
        text = _COMMENT_RE.sub(" ", text)
        text = _TAG_RE.sub(" ", text)
        text = html_module.unescape(text)

        return frozenset(
            ch for ch in text if not ch.isspace() and ch.isprintable()
        )
