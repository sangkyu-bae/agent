"""Application 테스트: render_wiki_folder_block (wiki-folder-summaries D5)."""
from datetime import datetime

from src.application.agent_run.prompt_rendering import (
    WIKI_FOLDER_HEADER_TAG,
    render_wiki_folder_block,
)
from src.domain.wiki.entity import WikiFolderSummary

NOW = datetime(2026, 7, 25)


def _folder(path="여신", summary="여신 지식", count=3):
    return WikiFolderSummary(
        id=f"f-{path}", agent_id="a1", path=path, summary=summary,
        article_count=count, updated_at=NOW,
    )


class TestRenderWikiFolderBlock:

    def test_renders_header_and_folder_lines(self):
        block = render_wiki_folder_block([_folder()], 0, max_bytes=4000)
        assert block.startswith(WIKI_FOLDER_HEADER_TAG)
        assert "- 여신 — 여신 지식 (3건)" in block
        assert "wiki_list" in block  # 진입 지시
        assert block.endswith("---\n\n")

    def test_uncategorized_line_when_present(self):
        block = render_wiki_folder_block([_folder()], 2, max_bytes=4000)
        assert "(미분류)" in block and "2건" in block

    def test_no_uncategorized_line_when_zero(self):
        block = render_wiki_folder_block([_folder()], 0, max_bytes=4000)
        assert "(미분류)" not in block

    def test_empty_folders_and_no_uncategorized_returns_empty(self):
        assert render_wiki_folder_block([], 0, max_bytes=4000) == ""

    def test_max_bytes_truncates_folder_lines(self):
        folders = [_folder(f"폴더{i}", "요약" * 50) for i in range(50)]
        block = render_wiki_folder_block(folders, 0, max_bytes=500)
        listed = [l for l in block.splitlines() if l.startswith("- ")]
        assert 0 < len(listed) < 50
        assert "생략" in block  # 절단 고지
