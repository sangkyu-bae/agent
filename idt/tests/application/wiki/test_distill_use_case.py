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

    async def find_by_agent(
        self, agent_id: str, request_id: str, status=None
    ) -> list[WikiArticle]:
        items = [a for a in self.store.values() if a.agent_id == agent_id]
        if status is not None:
            items = [a for a in items if a.status == status]
        return items


class _FakeProvider(WikiSourceProvider):
    def __init__(self, groups: list[WikiSourceGroup]) -> None:
        self._groups = groups

    async def fetch_source_groups(
        self, agent_id, collection_name, max_articles, request_id
    ) -> list[WikiSourceGroup]:
        return self._groups[:max_articles]


class _FakeDistiller(WikiDistillerInterface):
    def __init__(self) -> None:
        self.call_count = 0

    async def distill(self, group: WikiSourceGroup, request_id) -> DistilledContent:
        self.call_count += 1
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
        # dedup 도입 후 그룹별 고유 refs 필요 (동일 refs는 의도된 스킵 대상)
        uc, repo, _ = _make_uc(
            [_group(refs=["doc:1"]), _group(topic="금리", refs=["doc:2"])]
        )
        created, _skipped = await uc.execute(
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
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].path == "policy"

    @pytest.mark.asyncio
    async def test_title_and_content_from_distiller(self):
        uc, _, _ = _make_uc([_group(topic="여신 한도", texts=["A", "B"])])
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].title == "여신 한도"
        assert created[0].content == "A / B"

    @pytest.mark.asyncio
    async def test_source_refs_carried_from_group(self):
        uc, _, _ = _make_uc([_group(refs=["doc:9#p1", "doc:9#p2"])])
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].source_refs == ["doc:9#p1", "doc:9#p2"]

    @pytest.mark.asyncio
    async def test_persisted_via_repo(self):
        uc, repo, _ = _make_uc([_group()])
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert created[0].id in repo.store

    @pytest.mark.asyncio
    async def test_respects_max_articles(self):
        uc, _, _ = _make_uc(
            [_group(refs=["doc:1"]), _group(refs=["doc:2"]), _group(refs=["doc:3"])]
        )
        created, _skipped = await uc.execute("agent_1", "policy", max_articles=2, request_id="r")
        assert len(created) == 2

    @pytest.mark.asyncio
    async def test_group_without_refs_is_skipped_invariant(self):
        """출처 불변식: refs 빈 그룹은 건너뛰고 KB에 들어가지 않는다."""
        uc, repo, logger = _make_uc([_group(refs=[]), _group(refs=["doc:1"])])
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert len(created) == 1
        assert len(repo.store) == 1
        assert logger.warnings  # skip 경고 기록

    @pytest.mark.asyncio
    async def test_empty_source_returns_empty(self):
        uc, repo, _ = _make_uc([])
        created, _skipped = await uc.execute("agent_1", "policy", 10, "r")
        assert created == []
        assert repo.store == {}


class TestDedup:
    """fix-wiki-distill-dedup: refs 정확 일치 시 스킵 — 멱등 재실행."""

    @pytest.mark.asyncio
    async def test_동일_입력_재실행은_생성_0_스킵_N(self):
        groups = [_group(refs=["doc:1"]), _group(topic="금리", refs=["doc:2"])]
        uc, repo, _ = _make_uc(groups)

        first, first_skipped = await uc.execute("agent_1", "policy", 10, "r1")
        second, second_skipped = await uc.execute("agent_1", "policy", 10, "r2")

        assert len(first) == 2 and first_skipped == 0
        assert second == [] and second_skipped == 2
        assert len(repo.store) == 2  # 중복 미적재

    @pytest.mark.asyncio
    async def test_스킵_그룹은_distiller_미호출(self):
        """FR-02: LLM 호출 전 스킵 — 중복 비용 0."""
        uc, _, _ = _make_uc([_group(refs=["doc:1"])])

        await uc.execute("agent_1", "policy", 10, "r1")
        calls_after_first = uc._distiller.call_count
        await uc.execute("agent_1", "policy", 10, "r2")

        assert uc._distiller.call_count == calls_after_first  # 2회차 호출 0

    @pytest.mark.asyncio
    async def test_신규와_기존_혼합은_신규만_생성(self):
        uc, repo, _ = _make_uc([_group(refs=["doc:1"])])
        await uc.execute("agent_1", "policy", 10, "r1")

        uc2 = DistillToWikiUseCase(
            repository=repo,
            source_provider=_FakeProvider(
                [_group(refs=["doc:1"]), _group(topic="신규", refs=["doc:9"])]
            ),
            distiller=_FakeDistiller(),
            logger=_NullLogger(),
        )
        created, skipped = await uc2.execute("agent_1", "policy", 10, "r2")

        assert len(created) == 1 and created[0].source_refs == ["doc:9"]
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_refs_순서가_달라도_스킵(self):
        uc, repo, _ = _make_uc([_group(refs=["doc:1", "doc:2"])])
        await uc.execute("agent_1", "policy", 10, "r1")

        uc2 = DistillToWikiUseCase(
            repository=repo,
            source_provider=_FakeProvider([_group(refs=["doc:2", "doc:1"])]),
            distiller=_FakeDistiller(),
            logger=_NullLogger(),
        )
        created, skipped = await uc2.execute("agent_1", "policy", 10, "r2")

        assert created == [] and skipped == 1

    @pytest.mark.asyncio
    async def test_human_문서_refs는_비교_제외(self):
        """human:{id} 출처는 distilled 정체성과 무관 — 교차 오염 방지."""
        repo = _FakeRepo()
        human = WikiArticle(
            id="h1", agent_id="agent_1", title="사람 작성", content="본문",
            source_type=WikiSourceType.HUMAN, source_refs=["doc:1"],
            status=WikiStatus.APPROVED,
        )
        repo.store["h1"] = human
        uc, _, _ = _make_uc([_group(refs=["doc:1"])], repo=repo)

        created, skipped = await uc.execute("agent_1", "policy", 10, "r")

        assert len(created) == 1  # human refs와 겹쳐도 신규 정제
        assert skipped == 0

    @pytest.mark.asyncio
    async def test_동일_실행_내_중복_그룹은_1회만(self):
        uc, repo, _ = _make_uc([_group(refs=["doc:1"]), _group(refs=["doc:1"])])

        created, skipped = await uc.execute("agent_1", "policy", 10, "r")

        assert len(created) == 1 and skipped == 1
        assert len(repo.store) == 1
