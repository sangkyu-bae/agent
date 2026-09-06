-- mcp-tool-category-routing Design §3.3 (FR-01): 워커 노드 종류를 결정하는
-- 분류와 도구 호출 상한을 tool_catalog에 둔다. 도구 단위로 한 번 정리하면
-- 그 도구를 쓰는 모든 에이전트에 적용된다(에이전트별 예외는 agent_tool.category).
--
-- 두 컬럼 모두 nullable이며 백필하지 않는다. NULL = 미분류 = 이 사이클
-- 이전과 동일한 react 경로(FR-14)이므로 기존 저장 에이전트의 동작은 바뀌지
-- 않는다. 동작 변화는 관리자가 값을 지정한 도구에서만 일어난다.
--
-- 두 컬럼은 is_builtin과 같은 '관리자 지정, sync 보존' 계약을 따른다(D-02):
-- ToolCatalogRepository.upsert_by_tool_id의 UPDATE SET 절에 넣지 않는다.
-- 참조: docs/02-design/features/mcp-tool-category-routing.design.md

ALTER TABLE tool_catalog
    ADD COLUMN category VARCHAR(20) NULL DEFAULT NULL
        COMMENT '워커 노드 분류(search/collect/analysis/action). NULL=미분류 → react 기본 경로. 관리자 지정, sync 보존'
        AFTER is_builtin,
    ADD COLUMN max_tool_calls INT NULL DEFAULT NULL
        COMMENT '워커 1회 실행당 도구 호출 상한. NULL=정책 기본값(2회). 관리자 지정, sync 보존'
        AFTER category;

ALTER TABLE tool_catalog
    COMMENT = '시스템에 등록된 도구 카탈로그 — 내부 도구 + MCP 서버 도구';
