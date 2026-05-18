"""Elasticsearch index mapping and settings definitions."""

DOCUMENTS_INDEX_SETTINGS: dict = {
    "analysis": {
        "tokenizer": {
            "nori_user_dict_tokenizer": {
                "type": "nori_tokenizer",
                "decompound_mode": "mixed",
            }
        },
        "filter": {
            "nori_posfilter": {
                "type": "nori_part_of_speech",
                "stoptags": [
                    "E", "IC", "J", "MAG", "MAJ",
                    "MM", "SP", "SSC", "SSO", "SC",
                    "SE", "XPN", "XSA", "XSN", "XSV",
                    "UNA", "NA", "VSV",
                ],
            }
        },
        "analyzer": {
            "nori_analyzer": {
                "type": "custom",
                "tokenizer": "nori_user_dict_tokenizer",
                "filter": ["nori_posfilter", "nori_readingform", "lowercase"],
            }
        },
    }
}

DOCUMENTS_INDEX_MAPPINGS: dict = {
    "properties": {
        "content": {"type": "text", "analyzer": "nori_analyzer"},
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
