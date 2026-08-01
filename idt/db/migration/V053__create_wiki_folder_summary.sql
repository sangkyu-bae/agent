-- wiki-folder-summaries: 쓰기 시점 폴더 요약 계층 (wiki_article path 파생 데이터).
-- FK/COLLATE 명시 없음 (V037 주석 선례), ENGINE=InnoDB.
-- DDL comment 규칙(2026-07-25): 전 컬럼 + 테이블 COMMENT 필수.
CREATE TABLE wiki_folder_summary (
    id            CHAR(36)     NOT NULL COMMENT 'UUID PK',
    agent_id      CHAR(36)     NOT NULL COMMENT '소속 에이전트 (agent_definition.id)',
    path          VARCHAR(255) NOT NULL COMMENT '가상 폴더 경로("여신/한도"), 깊이<=3 — wiki_article.path와 동일 제약',
    summary       TEXT         NOT NULL COMMENT 'LLM 증류 폴더 안내 설명 (탐색 힌트 — 진실은 wiki_list 실시간 목록)',
    article_count INT          NOT NULL DEFAULT 0 COMMENT '하위 전체(재귀) 승인+미만료 문서 수',
    updated_at    DATETIME     NOT NULL COMMENT '마지막 재증류 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_wiki_folder (agent_id, path),
    KEY idx_wiki_folder_agent (agent_id)
) ENGINE=InnoDB
  COMMENT='에이전트 위키 폴더 요약 — 승인/편집/폐기 이벤트로 재증류되는 파생 캐시';
