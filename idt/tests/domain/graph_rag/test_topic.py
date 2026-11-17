"""module-4b 주제 도메인 — 이름 규칙·판정 id·발췌·판정 타입 구분."""

import pytest

from src.domain.graph_rag.exceptions import GraphTopicInvalidError
from src.domain.graph_rag.extraction import ChunkUnit
from src.domain.graph_rag.topic import (
    DOCUMENT_CHUNK_ID,
    TOPIC_EXCERPT_CHARS,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicPolicy,
    TopicStatus,
    is_topic_decision,
    mention_type_for,
    topic_decision_id,
)


def _unit(i: int, text: str) -> ChunkUnit:
    return ChunkUnit(f"c{i}", "doc", "kb", "col", text, i)


def test_name_is_trimmed_and_normalized():
    assert TopicPolicy.clean_name("  여신  ") == "여신"
    assert TopicPolicy.normalize(" 기업  여신 ") == "기업 여신"
    assert TopicPolicy.normalize("Loan") == "loan"


@pytest.mark.parametrize("bad", ["", "   ", "가" * 65])
def test_invalid_name_rejected(bad):
    with pytest.raises(GraphTopicInvalidError):
        TopicPolicy.clean_name(bad)


def test_level_and_parent_rules():
    TopicPolicy.check_parent(TopicLevel.MAJOR, None)
    TopicPolicy.check_parent(TopicLevel.MINOR, "p1")
    with pytest.raises(GraphTopicInvalidError):
        TopicPolicy.check_parent(TopicLevel.MAJOR, "p1")
    with pytest.raises(GraphTopicInvalidError):
        TopicPolicy.check_parent(TopicLevel.MINOR, None)


def test_decision_id_is_deterministic_per_document_slot():
    a = topic_decision_id("doc", "major")
    assert a == topic_decision_id("doc", "major")
    assert a != topic_decision_id("doc", "minor")
    assert a != topic_decision_id("doc2", "major")


def test_mention_types_and_detection():
    assert mention_type_for(TopicLevel.MAJOR) == "주제:대분류"
    assert mention_type_for(TopicLevel.MINOR) == "주제:소분류"
    assert is_topic_decision("주제:소분류")
    assert not is_topic_decision("상품")
    assert DOCUMENT_CHUNK_ID == "__document__"


def test_excerpt_uses_first_chunks_in_order_and_caps_length():
    units = [_unit(2, "셋째"), _unit(0, "첫째"), _unit(1, "둘째"), _unit(3, "넷째")]
    assert TopicPolicy.excerpt(units) == "첫째\n둘째\n셋째"
    long = [_unit(0, "가" * (TOPIC_EXCERPT_CHARS + 50))]
    assert len(TopicPolicy.excerpt(long)) == TOPIC_EXCERPT_CHARS


def test_topic_parent_key_and_usable():
    major = Topic("t1", "여신", "여신", TopicLevel.MAJOR, None, "",
                  TopicStatus.ACTIVE, TopicOrigin.ADMIN)
    minor = Topic("t2", "기업여신", "기업여신", TopicLevel.MINOR, "t1", "",
                  TopicStatus.PENDING, TopicOrigin.AUTO)
    retired = Topic("t3", "옛주제", "옛주제", TopicLevel.MAJOR, None, "",
                    TopicStatus.RETIRED, TopicOrigin.AUTO)
    assert major.parent_key == "" and minor.parent_key == "t1"
    assert major.usable and minor.usable and not retired.usable
