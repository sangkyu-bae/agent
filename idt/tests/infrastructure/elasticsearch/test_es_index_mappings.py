"""Tests for ES index mappings and settings with nori analyzer."""
from src.infrastructure.elasticsearch.es_index_mappings import (
    DOCUMENTS_INDEX_MAPPINGS,
    DOCUMENTS_INDEX_SETTINGS,
)


class TestDocumentsIndexSettings:
    def test_settings_has_analysis_section(self):
        assert "analysis" in DOCUMENTS_INDEX_SETTINGS

    def test_settings_defines_nori_tokenizer(self):
        tokenizer = DOCUMENTS_INDEX_SETTINGS["analysis"]["tokenizer"]
        assert "nori_user_dict_tokenizer" in tokenizer
        assert tokenizer["nori_user_dict_tokenizer"]["type"] == "nori_tokenizer"

    def test_nori_tokenizer_uses_mixed_decompound(self):
        tokenizer = DOCUMENTS_INDEX_SETTINGS["analysis"]["tokenizer"]["nori_user_dict_tokenizer"]
        assert tokenizer["decompound_mode"] == "mixed"

    def test_settings_defines_pos_filter(self):
        filters = DOCUMENTS_INDEX_SETTINGS["analysis"]["filter"]
        assert "nori_posfilter" in filters
        assert filters["nori_posfilter"]["type"] == "nori_part_of_speech"

    def test_pos_filter_removes_particles_and_endings(self):
        stoptags = DOCUMENTS_INDEX_SETTINGS["analysis"]["filter"]["nori_posfilter"]["stoptags"]
        assert "J" in stoptags
        assert "E" in stoptags

    def test_settings_defines_nori_analyzer(self):
        analyzer = DOCUMENTS_INDEX_SETTINGS["analysis"]["analyzer"]["nori_analyzer"]
        assert analyzer["type"] == "custom"
        assert analyzer["tokenizer"] == "nori_user_dict_tokenizer"
        assert "nori_posfilter" in analyzer["filter"]
        assert "nori_readingform" in analyzer["filter"]
        assert "lowercase" in analyzer["filter"]


class TestDocumentsIndexMappings:
    def test_content_field_uses_nori_analyzer(self):
        content = DOCUMENTS_INDEX_MAPPINGS["properties"]["content"]
        assert content["type"] == "text"
        assert content["analyzer"] == "nori_analyzer"

    def test_morph_text_field_uses_standard_analyzer(self):
        morph_text = DOCUMENTS_INDEX_MAPPINGS["properties"]["morph_text"]
        assert morph_text["type"] == "text"
        assert "analyzer" not in morph_text

    def test_keyword_fields_unchanged(self):
        props = DOCUMENTS_INDEX_MAPPINGS["properties"]
        for field in ["chunk_id", "chunk_type", "document_id", "user_id", "collection_name", "parent_id"]:
            assert props[field]["type"] == "keyword"

    def test_integer_fields_unchanged(self):
        props = DOCUMENTS_INDEX_MAPPINGS["properties"]
        assert props["chunk_index"]["type"] == "integer"
        assert props["total_chunks"]["type"] == "integer"
