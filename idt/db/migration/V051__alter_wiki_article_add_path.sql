-- wiki-user-facing: 지식 트리(가상 폴더) 분류 경로.
-- NULL = 미분류(기존 행 전부). FK/COLLATE 명시 없음 (V037 주석 선례).
ALTER TABLE wiki_article
    ADD COLUMN path VARCHAR(255) NULL COMMENT '가상 폴더 경로 예: 여신/한도',
    ADD INDEX idx_wiki_agent_path (agent_id, path);
