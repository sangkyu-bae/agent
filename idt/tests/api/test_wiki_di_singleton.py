"""wiki-tree-performance D1: wiki DI 싱글턴 회귀 테스트 (FR-01/05).

per-request로 OpenAIEmbedding·AsyncQdrantClient·QdrantVectorStore를 생성하면
요청마다 수 초의 초기화 비용 + 미해제 누수가 발생한다(plan §1.2 실측).
팩토리를 반복 호출해도 생성이 프로세스 수명 1회임을 계수로 단언한다.
"""
from unittest.mock import MagicMock

import pytest

import src.api.main as main_mod


@pytest.fixture(autouse=True)
def reset_wiki_singletons(monkeypatch):
    """전역 lazy 싱글턴을 테스트마다 초기화한다 (교차 오염 방지)."""
    monkeypatch.setattr(main_mod, "_wiki_vector_stack", None, raising=False)
    monkeypatch.setattr(main_mod, "_wiki_folder_summary_service", None, raising=False)


@pytest.fixture
def counting_ctors(monkeypatch):
    """main 네임스페이스의 무거운 생성자 3종을 계수 페이크로 교체한다."""
    emb_cls = MagicMock(name="OpenAIEmbedding")
    qdrant_cls = MagicMock(name="AsyncQdrantClient")
    store_cls = MagicMock(name="QdrantVectorStore")
    monkeypatch.setattr(main_mod, "OpenAIEmbedding", emb_cls)
    monkeypatch.setattr(main_mod, "AsyncQdrantClient", qdrant_cls)
    monkeypatch.setattr(main_mod, "QdrantVectorStore", store_cls)
    return emb_cls, qdrant_cls, store_cls


class TestWikiFactorySingleton:

    def test_tc01_repeated_requests_construct_once(self, counting_ctors):
        """query_factory(요청 상당) 3회 호출에도 생성자는 각 1회만 실행된다."""
        emb_cls, qdrant_cls, store_cls = counting_ctors
        _, query_factory, _, _ = main_mod.create_wiki_factories()

        for _ in range(3):
            query_factory(session=MagicMock())

        assert emb_cls.call_count == 1
        assert qdrant_cls.call_count == 1
        assert store_cls.call_count == 1

    def test_tc02_factory_reassembly_keeps_singleton(self, counting_ctors):
        """조립 함수 재호출(create_wiki_factories 2회)에도 전역 싱글턴이 유지된다."""
        emb_cls, qdrant_cls, store_cls = counting_ctors
        _, query_a, _, _ = main_mod.create_wiki_factories()
        _, query_b, _, _ = main_mod.create_wiki_factories()

        query_a(session=MagicMock())
        query_b(session=MagicMock())

        assert emb_cls.call_count == 1
        assert qdrant_cls.call_count == 1
        assert store_cls.call_count == 1

    def test_tc03_folder_summary_builder_shares_stack(
        self, counting_ctors, monkeypatch
    ):
        """폴더 요약 서비스의 article_repo_builder도 동일 싱글턴을 공유한다."""
        emb_cls, qdrant_cls, store_cls = counting_ctors
        service_cls = MagicMock(name="WikiFolderSummaryService")
        monkeypatch.setattr(
            "src.application.wiki.folder_summary_service.WikiFolderSummaryService",
            service_cls,
        )
        monkeypatch.setattr(
            "src.infrastructure.wiki.folder_summary_distiller."
            "FolderSummaryDistiller.from_openai",
            MagicMock(return_value=MagicMock()),
        )

        main_mod.get_wiki_folder_summary_service()
        builder = service_cls.call_args.kwargs["article_repo_builder"]

        builder(MagicMock())
        builder(MagicMock())

        assert emb_cls.call_count == 1
        assert qdrant_cls.call_count == 1
        assert store_cls.call_count == 1
