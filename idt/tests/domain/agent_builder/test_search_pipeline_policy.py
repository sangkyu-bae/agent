"""SearchPipelinePolicy 단위 테스트 (search-node-query-pipeline Design §4-1)."""
from src.domain.agent_builder.policies import SearchPipelinePolicy


class TestIsLastAttempt:
    def test_first_and_second_attempts_are_not_last(self):
        policy = SearchPipelinePolicy()
        assert policy.is_last_attempt(1) is False
        assert policy.is_last_attempt(2) is False

    def test_third_and_beyond_are_last(self):
        policy = SearchPipelinePolicy()
        assert policy.is_last_attempt(3) is True
        assert policy.is_last_attempt(4) is True


class TestNeedsCompression:
    def test_at_threshold_returns_false(self):
        policy = SearchPipelinePolicy(compress_threshold=100)
        assert policy.needs_compression("a" * 100) is False

    def test_above_threshold_returns_true(self):
        policy = SearchPipelinePolicy(compress_threshold=100)
        assert policy.needs_compression("a" * 101) is True

    def test_empty_text_returns_false(self):
        policy = SearchPipelinePolicy(compress_threshold=100)
        assert policy.needs_compression("") is False


class TestConstructor:
    def test_none_uses_default(self):
        policy = SearchPipelinePolicy(compress_threshold=None)
        assert policy.compress_threshold == SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD

    def test_zero_uses_default(self):
        policy = SearchPipelinePolicy(compress_threshold=0)
        assert policy.compress_threshold == SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD

    def test_negative_uses_default(self):
        policy = SearchPipelinePolicy(compress_threshold=-1)
        assert policy.compress_threshold == SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD

    def test_positive_value_is_kept(self):
        policy = SearchPipelinePolicy(compress_threshold=2000)
        assert policy.compress_threshold == 2000

    def test_default_constants(self):
        assert SearchPipelinePolicy.MAX_SEARCH_ATTEMPTS == 3
        assert SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD == 4000
