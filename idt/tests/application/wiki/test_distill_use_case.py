"""Application 테스트: DistillToWikiUseCase (LLM-WIKI-001, Phase 1/B).

원본 청크 그룹을 LLM이 요약 → draft 위키 항목 생성 흐름을 Fake로 검증한다.
실인프라(LLM/Qdrant/ES) 없이 비즈니스 규칙만 검증한다.
"""
import pytest

from src.application.wiki.distill_use_case import DistillToWikiUseCase
from src.application.wiki.interfaces import WikiDistillerInterface, WikiSourceProvider
from src.application.wiki.schemas import DistilledContent, WikiSourceGroup
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


class _NullLogger(LoggerInterface):
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, message, **kw): pass
    def info(self, message, **kw): pass
    def warning(self, message, **kw): self.warnings.append(message)
    def error(self, message, exception=None, **kw): pass
    def critical(self, message, exception=None, **kw): pass


class _FakeRepo:
    def __init__(self) -> None:
        self.store: dict[str, WikiArticle] = {}

    async def save(self, article: WikiArticle, request_id: str) -> WikiArticle:
        self.store[article.id] = article
        return article


class _FakeProvider(WikiSourceProvider):
    def __init__(self, groups: list[WikiSourceGroup]) -> None:
        self._groups = groups

    async def fetch_source_groups(
        self, agent_id, collection_name, max_articles, request_id
    ) -> list[WikiSourceGroup]:
        return self._groups[:max_articles]


class _FakeDistiller(WikiDistillerInterface):
    async def distill(self, group: WikiSourceGroup, request_id) -> DistilledContent:
        return DistilledContent(
            title=(group.topic_hint or "요약"),
            content=" / ".join(group.texts),
        )


def _group(topic="여신 한도", texts=None, refs=None) -> WikiSourceGroup:
    return WikiSourceGroup(
        topic_hint=topic,
        texts=texts if texts is not None else ["원문 A", "원문 B"],
        refs=refs if refs is not None else ["doc:1#p3"],
    )


def _make_uc(groups, repo=None, logger=None) -> tuple:
    repo = repo or _FakeRepo()
    logger = logger or _NullLogger()
    uc = DistillToWikiUseCase(
        repository=repo,
        source_provider=_FakeProvider(groups),
        distiller=_FakeDistiller(),
        logger=logger,
    )
    return uc, repo, logger


class TestDistill:

    @pytest.mark.asyncio
    async def test_creates_draft_articles(self):
        uc, repo, _ = _make_uc([_group(), _group(topic="금리")])
        created = await uc.execute(
            agent_id="agent_1", collection_name="policy", max_articles=10, request_id="r"
        )
        assert len(created) == 2
        assert all(a.status == WikiStatus.DRAFT for a in created)
        assert all(a.source_type == WikiSourceType.DISTILLED for a in created)
        assert all(a.agent_id == "agent_1" for a in created)

    @pytest.mark.asyncio
    async def test_default_path_is_collection_name(self):
        """wiki-user-facing FR-10: 신규 정제 문서에 컬렉션명 기본 path 부여."""
        uc, _, _ = _make_uc([_group()])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].path == "policy"

    @pytest.mark.asyncio
    async def test_title_and_content_from_distiller(self):
        uc, _, _ = _make_uc([_group(topic="여신 한도", texts=["A", "B"])])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].title == "여신 한도"
        assert created[0].content == "A / B"

    @pytest.mark.asyncio
    async def test_source_refs_carried_from_group(self):
        uc, _, _ = _make_uc([_group(refs=["doc:9#p1", "doc:9#p2"])])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].source_refs == ["doc:9#p1", "doc:9#p2"]

    @pytest.mark.asyncio
    async def test_persisted_via_repo(self):
        uc, repo, _ = _make_uc([_group()])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].id in repo.store

    @pytest.mark.asyncio
    async def test_respects_max_articles(self):
        uc, _, _ = _make_uc([_group(), _group(), _group()])
        created = await uc.execute("agent_1", "policy", max_articles=2, request_id="r")
        assert len(created) == 2

    @pytest.mark.asyncio
    async def test_group_without_refs_is_skipped_invariant(self):
        """출처 불변식: refs 빈 그룹은 건너뛰고 KB에 들어가지 않는다."""
        uc, repo, logger = _make_uc([_group(refs=[]), _group(refs=["doc:1"])])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert len(created) == 1
        assert len(repo.store) == 1
        assert logger.warnings  # skip 경고 기록

    @pytest.mark.asyncio
    async def test_empty_source_returns_empty(self):
        uc, repo, _ = _make_uc([])
        created = await uc.execute("agent_1", "policy", 10, "r")
        assert created == []
        assert repo.store == {}
