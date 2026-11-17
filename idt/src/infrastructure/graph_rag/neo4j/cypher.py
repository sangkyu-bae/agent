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
    "n.description = e.description, n.created_at = datetime(), "
    "n.name_embedding = e.name_embedding "
    "SET n.updated_at = datetime()"
)
WRITE_ALIASES = (
    "UNWIND $aliases AS a "
    "MATCH (e:Entity {id: a.entity_id}) "
    "MERGE (x:Alias {scope_key: a.scope_key, normalized: a.normalized}) "
    "SET x.surface = a.surface "
    "MERGE (x)-[:ALIAS_OF]->(e)"
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

# ── module-4: 판정·검토 (Design §2.2 판정) ──────────────────────────────────

_CANDIDATE_RETURN = (
    "e.id AS id, e.name AS name, e.type AS type, "
    "coalesce(e.description, '') AS description"
)
CANDIDATES_EXACT = (
    "MATCH (e:Entity {scope_key: $scope_key, normalized_name: $normalized}) "
    "RETURN " + _CANDIDATE_RETURN
)
CANDIDATES_ALIAS = (
    "MATCH (:Alias {scope_key: $scope_key, normalized: $normalized})"
    "-[:ALIAS_OF]->(e:Entity) RETURN " + _CANDIDATE_RETURN
)
# Neo4j 벡터 인덱스의 cosine score 는 (1 + cos) / 2 로 정규화돼 [0, 1] 이다.
CANDIDATES_VECTOR = (
    "CALL db.index.vector.queryNodes('" + VECTOR_INDEX_NAME + "', $k, $embedding) "
    "YIELD node AS e, score "
    "WHERE e.scope_key = $scope_key AND score >= $min_score "
    "RETURN " + _CANDIDATE_RETURN + ", score"
)

# 관계 시작점·끝점은 바꿀 수 없어 같은 속성으로 새로 만들고 지운다.
REASSIGN_MENTIONS = (
    "MATCH (:Entity)-[m:MENTIONED_IN {decision_id: $decision_id}]->(c:Chunk) "
    "MATCH (n:Entity {id: $to}) "
    "MERGE (n)-[m2:MENTIONED_IN {decision_id: $decision_id}]->(c) "
    "SET m2.document_id = m.document_id DELETE m"
)
REASSIGN_REL_SOURCES = (
    "MATCH (a:Entity)-[r:{rel}]->(b:Entity) "
    "WHERE r.source_decision_id = $decision_id AND a.id <> $to "
    "MATCH (n:Entity {{id: $to}}) "
    "CREATE (n)-[r2:{rel}]->(b) SET r2 = properties(r) DELETE r"
)
REASSIGN_REL_TARGETS = (
    "MATCH (a:Entity)-[r:{rel}]->(b:Entity) "
    "WHERE r.target_decision_id = $decision_id AND b.id <> $to "
    "MATCH (n:Entity {{id: $to}}) "
    "CREATE (a)-[r2:{rel}]->(n) SET r2 = properties(r) DELETE r"
)
CREATE_ENTITY = (
    "MERGE (n:Entity {id: $id}) "
    "SET n.scope_key = $scope_key, n.name = $name, "
    "n.normalized_name = $normalized_name, n.type = $type, "
    "n.description = $description, n.created_at = datetime(), "
    "n.updated_at = datetime()"
)
DELETE_ENTITY_IF_ORPHAN = (
    "MATCH (e:Entity {id: $id}) WHERE NOT (e)-[:MENTIONED_IN]->() "
    "OPTIONAL MATCH (a:Alias)-[:ALIAS_OF]->(e) "
    "DETACH DELETE a, e RETURN count(*) AS deleted"
)

# module-4b: 문서 청크에 주제 id 복사(검색 범위 필터).
# 원본은 MySQL graph_document_topic.
SET_DOCUMENT_TOPICS = (
    "MATCH (c:Chunk {document_id: $document_id}) SET c.topic_ids = $topic_ids "
    "RETURN count(c) AS updated"
)

# ── module-5: 검색 (Design §2.2 검색) ──────────────────────────────────────
# $topic_ids 가 null 이면 범위를 좁히지 않는다. 범위 = 그 주제 청크에 언급된 엔티티.
_IN_SCOPE_CHUNK = (
    "($topic_ids IS NULL OR any(t IN coalesce(c.topic_ids, []) WHERE t IN $topic_ids))"
)
_ENTITY_IN_SCOPE = (
    "($topic_ids IS NULL OR EXISTS { MATCH (e)-[:MENTIONED_IN]->(c:Chunk) "
    "WHERE any(t IN coalesce(c.topic_ids, []) WHERE t IN $topic_ids) })"
)
LINK_VECTOR = (
    "CALL db.index.vector.queryNodes('" + VECTOR_INDEX_NAME + "', $k, $embedding) "
    "YIELD node AS e, score "
    "WHERE e.scope_key = $scope_key AND score >= $min_score "
    "AND " + _ENTITY_IN_SCOPE + " "
    "RETURN e.id AS id, e.name AS name, e.type AS type, score ORDER BY score DESC"
)
SEED_MENTIONS = (
    "MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk) "
    "WHERE e.id IN $ids AND " + _IN_SCOPE_CHUNK + " "
    "RETURN c.chunk_id AS chunk_id, count(*) AS n"
)
# 경유 노드(처음·끝 제외)는 관계 수가 $hub_limit 이하여야 한다. 단계 수는 검증된 int.
FIND_PATHS = (
    "MATCH (s:Entity) WHERE s.id IN $ids "
    "MATCH p = (s)-[:RELATES|REFERS_TO*1..{hops}]-(:Entity) "
    "WHERE all(n IN nodes(p)[1..-1] "
    "WHERE COUNT {{ (n)-[:RELATES|REFERS_TO]-() }} <= $hub_limit) "
    "RETURN [n IN nodes(p) | n.name] AS names, "
    "[r IN relationships(p) | r.type] AS types, "
    "[r IN relationships(p) | r.evidence_chunk_id] AS chunks "
    "LIMIT $limit"
)
CHUNKS_IN_SCOPE = (
    "MATCH (c:Chunk) WHERE c.chunk_id IN $ids AND " + _IN_SCOPE_CHUNK + " "
    "RETURN c.chunk_id AS chunk_id"
)
# 정확 일치·별칭을 한 번에(왕복 1회).
LINK_NAMES = (
    "CALL { "
    "UNWIND $phrases AS p "
    "MATCH (e:Entity {scope_key: $scope_key, normalized_name: p}) "
    "RETURN e, 'exact' AS via "
    "UNION "
    "UNWIND $phrases AS p "
    "MATCH (:Alias {scope_key: $scope_key, normalized: p})-[:ALIAS_OF]->(e:Entity) "
    "RETURN e, 'alias' AS via "
    "} "
    "WITH e, via WHERE " + _ENTITY_IN_SCOPE + " "
    "RETURN e.id AS id, e.name AS name, e.type AS type, via"
)

# ── module-5b: 관리자 점검 ─────────────────────────────────────────────────
# 값 엔티티(청크 단위 키 '{chunk_id}::이름')는 목록에서 뺀다.
_ENTITY_FILTER = (
    "MATCH (e:Entity) WHERE NOT e.normalized_name CONTAINS '::' "
    "AND ($q IS NULL OR e.normalized_name CONTAINS $q) "
    "AND ($type IS NULL OR e.type = $type) "
)
COUNT_ENTITIES = _ENTITY_FILTER + "RETURN count(e) AS c"
SEARCH_ENTITIES = (
    _ENTITY_FILTER + "WITH e ORDER BY e.name SKIP $skip LIMIT $limit "
    "RETURN e.id AS id, e.name AS name, e.type AS type, "
    "coalesce(e.description, '') AS description, "
    "COUNT { (e)-[:MENTIONED_IN]->() } AS mentions, "
    "COUNT { (e)-[:RELATES|REFERS_TO]-() } AS rels"
)
ENTITY_ALIASES = (
    "MATCH (a:Alias)-[:ALIAS_OF]->(:Entity {id: $id}) RETURN a.surface AS surface"
)
ENTITY_RELATIONS = (
    "MATCH (e:Entity {id: $id})-[r:RELATES|REFERS_TO]-(o:Entity) "
    "RETURN r.id AS id, type(r) AS kind, coalesce(r.type, '') AS type, "
    "CASE WHEN startNode(r) = e THEN 'out' ELSE 'in' END AS direction, "
    "o.id AS other_id, o.name AS other_name, "
    "coalesce(r.evidence_chunk_id, '') AS chunk_id, "
    "coalesce(r.evidence_text, '') AS evidence, "
    "coalesce(r.document_id, '') AS document_id "
    "ORDER BY kind, type, other_name LIMIT $limit"
)
ENTITY_MENTIONS = (
    "MATCH (:Entity {id: $id})-[m:MENTIONED_IN]->(c:Chunk) "
    "RETURN c.chunk_id AS chunk_id, c.document_id AS document_id, "
    "m.decision_id AS decision_id LIMIT $limit"
)
SAMPLE_CHUNKS = (
    "MATCH (c:Chunk) WHERE $kb_id IS NULL OR c.kb_id = $kb_id "
    "RETURN c.chunk_id AS chunk_id, c.document_id AS document_id LIMIT $limit"
)
ENTITY_SUMMARY = (
    "MATCH (e:Entity {id: $id}) "
    "RETURN e.id AS id, e.name AS name, e.type AS type, "
    "coalesce(e.description, '') AS description, "
    "COUNT { (e)-[:MENTIONED_IN]->() } AS mentions, "
    "COUNT { (e)-[:RELATES|REFERS_TO]-() } AS rels"
)
