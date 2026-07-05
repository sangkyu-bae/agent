-- LLM-WIKI-001: LLM Wiki(Self-Improving RAG) 정제 지식 저장소.
-- MySQL은 메타데이터/라이프사이클의 SoT(Source of Truth)이며,
-- 본문 임베딩/역색인은 Qdrant(wiki_knowledge) + Elasticsearch가 담당한다.
CREATE TABLE wiki_article (
    id            VARCHAR(36)  NOT NULL,
    agent_id      VARCHAR(36)  NOT NULL COMMENT '소속 에이전트(Phase 1 스코프 키)',
    title         VARCHAR(200) NOT NULL COMMENT '위키 항목 제목(검색 키)',
    content       TEXT         NOT NULL COMMENT '정제 본문(문서/섹션 요약)',
    source_type   VARCHAR(20)  NOT NULL COMMENT 'distilled|conversation|websearch|human',
    source_refs   JSON         NOT NULL COMMENT '출처 추적 식별자 목록(비면 생성 불가-출처 불변식)',
    status        VARCHAR(20)  NOT NULL DEFAULT 'draft' COMMENT 'draft|approved|deprecated',
    confidence    DECIMAL(4,3) NOT NULL DEFAULT 0.500 COMMENT '신뢰도 0~1(환류 신호로 갱신)',
    valid_until   DATETIME     NULL COMMENT '만료 시각(NULL=무기한, websearch 출처 권장)',
    version       INT          NOT NULL DEFAULT 1,
    editor_id     VARCHAR(36)  NULL,
    reviewer_id   VARCHAR(36)  NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_agent_status (agent_id, status),
    INDEX ix_valid_until (valid_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
