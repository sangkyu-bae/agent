"""DocumentCharsetPolicy 단위 테스트 (Design §8.2 U-01·U-02)."""
from src.domain.document_font.policies import DocumentCharsetPolicy


def test_extracts_only_text_characters_not_tag_names():
    """U-01: 태그명 문자는 서브셋 대상이 아니다."""
    html = "<h1>위기</h1><p>보고서</p>"

    chars = DocumentCharsetPolicy.extract_chars(html)

    assert chars == frozenset("위기보고서")


def test_unescapes_entities_and_drops_comments():
    """U-02: 엔티티는 실제 문자로, 주석 내용은 제외."""
    html = "<p>A&amp;B</p><!-- 숨김주석 -->"

    chars = DocumentCharsetPolicy.extract_chars(html)

    assert chars == frozenset("A&B")


def test_drops_whitespace_and_control_characters():
    html = "<p>가 나\n\t다</p>"

    chars = DocumentCharsetPolicy.extract_chars(html)

    assert chars == frozenset("가나다")


def test_ignores_attribute_values():
    """속성값은 화면에 그려지지 않으므로 서브셋 대상이 아니다."""
    html = '<p class="주석달림">본문</p>'

    chars = DocumentCharsetPolicy.extract_chars(html)

    assert chars == frozenset("본문")


def test_drops_style_and_script_content():
    html = "<style>body{color:red}</style><p>본문</p>"

    chars = DocumentCharsetPolicy.extract_chars(html)

    assert chars == frozenset("본문")


def test_empty_html_returns_empty_set():
    assert DocumentCharsetPolicy.extract_chars("") == frozenset()
    assert DocumentCharsetPolicy.extract_chars("   ") == frozenset()
