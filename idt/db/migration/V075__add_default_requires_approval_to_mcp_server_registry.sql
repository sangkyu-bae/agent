-- approval-gate-phase2-mcp-executor Design §3.3 (D-07) — 서버 축 초기값.
-- MCP 서버는 사용자별로 등록되고 sync 는 등록 건마다 tool_catalog 엔트리를
-- 만든다. 엔트리의 requires_approval 이 항상 0 으로 시작하면 새 사용자의
-- 발송·변경 도구는 관리자가 찾아서 켜기 전까지 승인 없이 실행된다.
--
-- 이 컬럼은 그 "초기값" 만 정한다:
--   sync 가 엔트리를 신규 INSERT 할 때 1회 복사된다.
--   이미 있는 엔트리에는 소급하지 않는다 — 런타임 SoT 는 여전히
--   tool_catalog.requires_approval (V072, 관리자 토글) 이고, upsert 의
--   UPDATE 분기는 그 컬럼을 건드리지 않는다.

ALTER TABLE mcp_server_registry
    ADD COLUMN default_requires_approval TINYINT(1) NOT NULL DEFAULT 0
    COMMENT '1이면 이 서버의 도구가 카탈로그에 처음 등록될 때 requires_approval=1 로 시작 (초기값 전용, 기존 엔트리 소급 없음). 기본 0 이라 기존 서버는 무영향';
