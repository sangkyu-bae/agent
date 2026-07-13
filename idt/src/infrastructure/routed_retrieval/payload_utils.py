"""Qdrant payload 값 복원 유틸 (summary-routed-retrieval).

`_point_to_document`가 payload 전 값을 str 캐스팅하므로(업로드 관례),
list 필드(keywords)는 파이썬 repr 문자열로 돌아온다 — 관대하게 복원한다.
"""
import ast


def parse_keyword_list(value) -> list[str]:
    """payload keywords 복원 — list 그대로/repr 문자열/그 외 순으로 관대 처리."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (ValueError, SyntaxError):
            pass
    return []
