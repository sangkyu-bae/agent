"""Formatter for web search results."""

import html

from src.domain.web_search.value_objects import SearchResult


def format_search_result_to_xml(
    result: SearchResult,
    include_raw_content: bool = False,
) -> str:
    """Format search results to XML string.

    Args:
        result: The search result to format.
        include_raw_content: Whether to include raw_content in output.

    Returns:
        XML-formatted string of search results.
    """
    lines = ["<search_results>"]

    for item in result.items:
        lines.append("  <result>")
        lines.append(f"    <title>{html.escape(item.title)}</title>")
        lines.append(f"    <url>{html.escape(item.url)}</url>")
        lines.append(f"    <content>{html.escape(item.content)}</content>")
        lines.append(f"    <score>{item.score}</score>")

        if include_raw_content and item.raw_content is not None:
            lines.append(
                f"    <raw_content>{html.escape(item.raw_content)}</raw_content>"
            )

        lines.append("  </result>")

    lines.append("</search_results>")

    return "\n".join(lines)
