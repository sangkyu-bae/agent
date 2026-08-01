-- builtin-tools D1: 에이전트 생성 시 자동 주입되는 빌트인 도구 플래그.
-- 런타임 SoT는 본 컬럼(관리자 토글). 부팅 sync는 UPDATE 시 본 컬럼을 건드리지 않는다(D2).
ALTER TABLE tool_catalog
    ADD COLUMN is_builtin TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '빌트인 여부 — 에이전트 생성 시 자동 주입. 관리자 토글, sync 보존, INSERT 시 ToolMeta.builtin_default 시드';

-- 초기 시드 (기존 DB 전용 — 프레시 DB는 첫 sync INSERT가 builtin_default로 시드)
UPDATE tool_catalog SET is_builtin = 1
WHERE tool_id IN ('internal:wiki_read', 'internal:wiki_list');
