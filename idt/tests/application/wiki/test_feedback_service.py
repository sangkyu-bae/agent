"""FeedbackWikiService 단위 테스트 (wiki-feedback-loop Design §3-4).

MemoryExtractionService 동형 launcher — off no-op·refs dedup·draft 저장·격리.
kickoff은 fire-and-forget이라 테스트는 drain으로 잔여 태스크를 대기한다.
"""
from unittest.mock import AsyncMock, MagicMock

from src.application.wiki.feedback_service import FeedbackWikiService
from src.application.wiki.schemas import FeedbackWikiDraft
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


def _existing_article(refs: list[str]) -> WikiArticle:
    return WikiArticle(
        id="a-1", agent_id="super", title="기존", content="기존 본문",
        source_type=WikiSourceType.CONVERSATION, source_refs=refs,
    )


class _BeginCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _SessionCtx:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        self._counter["opened"] += 1
        session = MagicMock()
        session.begin = lambda: _BeginCtx()
        return session

    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make(
    draft=None,
    existing=None,
    enabled=True,
    distill_error=None,
):
    counter = {"opened": 0, "closed": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    repo.find_by_agent = AsyncMock(return_value=list(existing or []))
    saved: list[WikiArticle] = []

    async def _save(article, request_id):
        saved.append(article)
        return article

    repo.save = AsyncMock(side_effect=_save)

    distiller = MagicMock()
    if distill_error is not None:
        distiller.distill_feedback = AsyncMock(side_effect=distill_error)
    else:
        distiller.distill_feedback = AsyncMock(return_value=draft)

    logger = MagicMock()
    service = FeedbackWikiService(
        session_factory=session_factory,
        distiller=distiller,
        logger=logger,
        enabled=enabled,
        repo_builder=lambda session: repo,
    )
    return service, repo, distiller, logger, saved, counter


_DRAFT = FeedbackWikiDraft(
    title="여신 한도 산정 기준", content="담보가치의 70% 상한.", confidence=0.8
)


class TestKickoffDraft:
    async def test_enabled_False면_no_op(self):
        service, _, distiller, _, _, counter = _make(enabled=False, draft=_DRAFT)

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        distiller.distill_feedback.assert_not_awaited()
        assert counter["opened"] == 0
        assert service.enabled is False

    async def test_worthy_초안은_draft_CONVERSATION으로_저장(self):
        service, _, distiller, _, saved, _ = _make(draft=_DRAFT)

        service.kickoff_draft("super", 77, "질문", "답변", "70%가 맞음", "req-1")
        await service.drain()

        assert distiller.distill_feedback.await_args.args[:3] == (
            "질문", "답변", "70%가 맞음"
        )
        assert len(saved) == 1
        article = saved[0]
        assert article.status == WikiStatus.DRAFT
        assert article.source_type == WikiSourceType.CONVERSATION
        assert article.source_refs == ["feedback:77"]
        assert article.agent_id == "super"
        assert article.path == "피드백"
        assert article.confidence == 0.8
        assert service.enabled is True

    async def test_동일_message_refs_존재시_LLM_호출_전_스킵(self):
        service, _, distiller, _, saved, _ = _make(
            draft=_DRAFT, existing=[_existing_article(["feedback:77"])]
        )

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        distiller.distill_feedback.assert_not_awaited()  # FR-04 멱등
        assert saved == []

    async def test_다른_message_refs는_스킵되지_않음(self):
        service, _, _, _, saved, _ = _make(
            draft=_DRAFT, existing=[_existing_article(["feedback:99"])]
        )

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        assert len(saved) == 1

    async def test_distiller가_None이면_저장_0건(self):
        service, repo, _, _, saved, _ = _make(draft=None)

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        assert saved == []
        repo.save.assert_not_awaited()

    async def test_불변식_위반_초안은_warning_스킵(self):
        bad = FeedbackWikiDraft(title="제목", content="   ", confidence=0.5)
        service, _, _, logger, saved, _ = _make(draft=bad)

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        assert saved == []
        logger.warning.assert_called_once()

    async def test_예외는_warning으로_격리(self):
        service, _, _, logger, saved, _ = _make(distill_error=RuntimeError("llm down"))

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        assert saved == []
        logger.warning.assert_called_once()

    async def test_세션은_dedup조회와_저장_2회_개폐(self):
        service, _, _, _, _, counter = _make(draft=_DRAFT)

        service.kickoff_draft("super", 77, "질문", "답변", "이유", "req-1")
        await service.drain()

        assert counter["opened"] == 2  # 조회/저장 분리 — LLM 중 DB 점유 없음
        assert counter["closed"] == 2
