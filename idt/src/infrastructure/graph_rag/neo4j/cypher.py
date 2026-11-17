"""Neo4j Cypher 상수 (Design §3.2) — 라벨·관계 타입은 코드 상수, 값은 전부 파라미터."""

VECTOR_INDEX_NAME = "entity_name_vec"

SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
    "FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE INDEX entity_norm IF NOT EXISTS "
    "FOR (e:Entity) ON (e.scope_key, e.normalized_name)",
    "CREATE INDEX alias_norm IF NOT EXISTS "
    "FOR (a:Alias) ON (a.scope_key, a.normalized)",
    "CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.document_id)",
)

# OPTIONS 맵은 파라미터를 받지 않는 버전이 있어 차원은 검증된 int 로만 채운다.
VECTOR_INDEX_CREATE = (
    "CREATE VECTOR INDEX " + VECTOR_INDEX_NAME + " IF NOT EXISTS "
    "FOR (e:Entity) ON e.name_embedding "
    "OPTIONS {{indexConfig: {{`vector.dimensions`: {dims}, "
    "`vector.similarity_function`: 'cosine'}}}}"
)

VECTOR_INDEX_SHOW = "SHOW INDEXES YIELD name, options WHERE name = $name RETURN options"

COUNT_NODES = "MATCH (n) RETURN count(n) AS c"
COUNT_RELATIONSHIPS = "MATCH ()-[r]->() RETURN count(r) AS c"

# ── module-3: 적재 (Design §3.2) ────────────────────────────────────────────

EXTRACTED_CHUNKS = (
    "MATCH (c:Chunk {document_id: $document_id}) "
    "WHERE c.extractor_version = $version RETURN c.chunk_id AS chunk_id"
)

FIND_ENTITY = (
    "MATCH (e:Entity {scope_key: $scope_key, normalized_name: $normalized, "
    "type: $type}) RETURN e.id AS id LIMIT 1"
)

DELETE_DOC_CHUNKS = "MATCH (c:Chunk {document_id: $document_id}) DETACH DELETE c"
DELETE_DOC_RELATES = (
    "MATCH ()-[r:RELATES|REFERS_TO {document_id: $document_id}]->() DELETE r"
)
# 언급(MENTIONED_IN)이 하나도 남지 않은 엔티티와 그 별칭을 지운다.
DELETE_ORPHAN_ENTITIES = (
    "MATCH (e:Entity) WHERE NOT (e)-[:MENTIONED_IN]->() "
    "OPTIONAL MATCH (a:Alias)-[:ALIAS_OF]->(e) DETACH DELETE a, e"
)

WRITE_CHUNK = (
    "MERGE (c:Chunk {chunk_id: $chunk_id}) "
    "SET c.document_id = $document_id, c.kb_id = $kb_id, "
    "c.collection_name = $collection_name, c.extractor_version = $version, "
    "c.extracted_at = datetime()"
)
WRITE_ENTITIES = (
    "UNWIND $entities AS e "
    "MERGE (n:Entity {id: e.id}) "
    "ON CREATE SET n.scope_key = e.scope_key, n.name = e.name, "
    "n.normalized_name = e.normalized_name, n.type = e.type, "
    "n.description = e.description, n.created_at = datetime() "
    "SET n.updated_at = datetime()"
)
WRITE_MENTIONS = (
    "UNWIND $mentions AS m "
    "MATCH (n:Entity {id: m.entity_id}), (c:Chunk {chunk_id: $chunk_id}) "
    "MERGE (n)-[r:MENTIONED_IN {decision_id: m.decision_id}]->(c) "
    "SET r.document_id = $document_id"
)
_REL_SET = (
    "SET x.type = r.type, x.evidence_chunk_id = $chunk_id, "
    "x.document_id = $document_id, x.kb_id = $kb_id, "
    "x.evidence_text = r.evidence_text, "
    "x.source_decision_id = r.source_decision_id, "
    "x.target_decision_id = r.target_decision_id, x.extractor_version = $version"
)
WRITE_RELATES = (
    "UNWIND $relations AS r "
    "MATCH (a:Entity {id: r.source}), (b:Entity {id: r.target}) "
    "MERGE (a)-[x:RELATES {id: r.id}]->(b) " + _REL_SET
)
WRITE_REFERS_TO = (
    "UNWIND $relations AS r "
    "MATCH (a:Entity {id: r.source}), (b:Entity {id: r.target}) "
    "MERGE (a)-[x:REFERS_TO {id: r.id}]->(b) " + _REL_SET
)
