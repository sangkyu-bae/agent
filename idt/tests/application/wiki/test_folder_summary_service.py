"""Application 테스트: WikiFolderSummaryService (wiki-folder-summaries D2).

fire-and-forget 팬아웃 — 조상 확장·bottom-up 재증류·빈 폴더 삭제·실패 무해성·
enabled 게이트를 페이크 의존으로 검증한다 (WikiFeedbackService 패턴).
"""
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.wiki.folder_summary_service import WikiFolderSummaryService
from src.domain.wiki.entity import (
    WikiArticle,
    WikiFolderSummary,
    WikiSourceType,
    WikiStatus,
)

NOW = datetime(2026, 7, 25)


def _article(id, path, status=WikiStatus.APPROVED, content="본문"):
    return WikiArticle(
        id=id, agent_id="a1", title=f"제목{id}", content=content,
        source_type=WikiSourceType.HUMAN, source_refs=["human:u1"],
        status=status, created_at=NOW, updated_at=NOW, path=path,
    )


class FakeArticleRepo:
    def __init__(self, articles):
        self._articles = articles

    async def find_by_agent(self, agent_id, request_id, status=None):
        return [
            a for a in self._articles
            if a.agent_id == agent_id
            and (status is None or a.status == status)
        ]


class FakeFolderRepo:
    def __init__(self, rows=None):
        self.rows = {r.path: r for r in (rows or [])}
        self.deleted: list[str] = []

    async def upsert(self, summary, request_id):
        self.rows[summary.path] = summary

    async def delete(self, agent_id, path, request_id):
        self.rows.pop(path, None)
        self.deleted.append(path)

    async def list_by_agent(self, agent_id, request_id):
        return sorted(self.rows.values(), key=lambda r: r.path)


class FakeDistiller:
    def __init__(self, fail=False, fail_paths=None):
        self.calls: list[tuple] = []
        self.fail = fail
        self.fail_paths = set(fail_paths or [])

    async def summarize_folder(self, path, doc_snippets, child_summaries, request_id):
        self.calls.append((path, list(doc_snippets), list(child_summaries)))
        if self.fail or path in self.fail_paths:
            raise RuntimeError("llm down")
        return f"요약:{path}"


def _service(article_repo, folder_repo, distiller, enabled=True):
    @asynccontextmanager
    async def session_factory():
        session = MagicMock()

        @asynccontextmanager
        async def begin():
            yield

        session.begin = begin
        yield session

    return WikiFolderSummaryService(
        session_factory=session_factory,
        article_repo_builder=lambda s: article_repo,
        folder_repo_builder=lambda s: folder_repo,
        distiller=distiller,
        logger=MagicMock(),
        enabled=enabled,
    )


class TestKickoffRefresh:

    @pytest.mark.asyncio
    async def test_disabled_is_noop(self):
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo([]), FakeFolderRepo(), distiller, enabled=False)
        svc.kickoff_refresh("a1", ["여신"], "r")
        await svc.drain()
        assert distiller.calls == []

    @pytest.mark.asyncio
    async def test_none_paths_only_is_noop(self):
        """미분류(path=None)만 변경 — 재증류 대상 없음."""
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo([]), FakeFolderRepo(), distiller)
        svc.kickoff_refresh("a1", [None], "r")
        await svc.drain()
        assert distiller.calls == []

    @pytest.mark.asyncio
    async def test_refreshes_self_and_ancestors_bottom_up(self):
        articles = [_article("w1", "여신/한도/개인"), _article("w2", "여신")]
        folder_repo = FakeFolderRepo()
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo(articles), folder_repo, distiller)

        svc.kickoff_refresh("a1", ["여신/한도/개인"], "r")
        await svc.drain()

        assert [c[0] for c in distiller.calls] == [
            "여신/한도/개인", "여신/한도", "여신",
        ]
        assert set(folder_repo.rows) == {"여신/한도/개인", "여신/한도", "여신"}
        # 재귀 승인 문서 수: 최상위 "여신"은 w1+w2=2
        assert folder_repo.rows["여신"].article_count == 2

    @pytest.mark.asyncio
    async def test_parent_input_uses_child_summaries(self):
        """상위 폴더 증류 입력에 방금 갱신된 하위 요약이 들어간다 (D3 계층 증류)."""
        articles = [_article("w1", "여신/한도")]
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo(articles), FakeFolderRepo(), distiller)

        svc.kickoff_refresh("a1", ["여신/한도"], "r")
        await svc.drain()

        parent_call = distiller.calls[1]
        assert parent_call[0] == "여신"
        assert "요약:여신/한도" in parent_call[2]

    @pytest.mark.asyncio
    async def test_empty_folder_summary_deleted(self):
        """직속 문서 0 + 하위 폴더 0 → 요약 row 삭제, 증류 호출 없음."""
        stale = WikiFolderSummary(
            id="f1", agent_id="a1", path="여신", summary="옛날", updated_at=NOW
        )
        folder_repo = FakeFolderRepo([stale])
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo([]), folder_repo, distiller)

        svc.kickoff_refresh("a1", ["여신"], "r")
        await svc.drain()

        assert folder_repo.deleted == ["여신"]
        assert distiller.calls == []

    @pytest.mark.asyncio
    async def test_expired_articles_excluded(self):
        expired = _article("w1", "여신")
        expired.valid_until = datetime(2020, 1, 1)
        folder_repo = FakeFolderRepo()
        svc = _service(FakeArticleRepo([expired]), folder_repo, FakeDistiller())

        svc.kickoff_refresh("a1", ["여신"], "r")
        await svc.drain()

        assert folder_repo.rows == {}

    @pytest.mark.asyncio
    async def test_distill_failure_is_swallowed(self):
        """LLM 실패는 warning 격리 — kickoff 호출자에 전파 금지."""
        svc = _service(
            FakeArticleRepo([_article("w1", "여신")]),
            FakeFolderRepo(), FakeDistiller(fail=True),
        )
        svc.kickoff_refresh("a1", ["여신"], "r")
        await svc.drain()  # 예외 없이 완료되어야 한다

    @pytest.mark.asyncio
    async def test_leaf_failure_does_not_block_ancestors(self):
        """폴더 단위 실패 격리 — leaf 증류 실패에도 조상 폴더는 계속 갱신 (D2)."""
        articles = [_article("w1", "여신/한도"), _article("w2", "여신")]
        folder_repo = FakeFolderRepo()
        distiller = FakeDistiller(fail_paths={"여신/한도"})
        svc = _service(FakeArticleRepo(articles), folder_repo, distiller)

        svc.kickoff_refresh("a1", ["여신/한도"], "r")
        await svc.drain()

        assert [c[0] for c in distiller.calls] == ["여신/한도", "여신"]
        assert "여신/한도" not in folder_repo.rows  # 실패 폴더는 미기록
        assert folder_repo.rows["여신"].summary == "요약:여신"

    @pytest.mark.asyncio
    async def test_duplicate_paths_deduped(self):
        """[old, new]가 같은 조상을 공유해도 폴더당 1회만 증류."""
        articles = [_article("w1", "여신/한도"), _article("w2", "여신/심사")]
        distiller = FakeDistiller()
        svc = _service(FakeArticleRepo(articles), FakeFolderRepo(), distiller)

        svc.kickoff_refresh("a1", ["여신/한도", "여신/심사"], "r")
        await svc.drain()

        paths = [c[0] for c in distiller.calls]
        assert paths.count("여신") == 1
        assert set(paths) == {"여신/한도", "여신/심사", "여신"}
