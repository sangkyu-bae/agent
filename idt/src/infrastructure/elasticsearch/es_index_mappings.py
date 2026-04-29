"""Elasticsearch index mapping definitions."""

DOCUMENTS_INDEX_MAPPINGS: dict = {
    "properties": {
        "content": {"type": "text"},
        "morph_text": {"type": "text"},
        "morph_keywords": {"type": "keyword"},
        "chunk_id": {"type": "keyword"},
        "chunk_type": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "total_chunks": {"type": "integer"},
        "document_id": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "collection_name": {"type": "keyword"},
        "parent_id": {"type": "keyword"},
    }
}
