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
