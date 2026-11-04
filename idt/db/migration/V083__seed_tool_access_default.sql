-- tool-access-control Design §3.3 (V083) / Plan FR-03: 배포 직후 동작 변화 0.
-- 기본 차단으로 전환하는 순간 기존 에이전트 도구가 막히지 않도록 현재 카탈로그의 모든 도구를
-- 기본 세트에 넣는다. 관리자는 이후 기본 세트에서 빼고 부서·사용자에게 좁혀 나간다.
-- 이 시드 이후 MCP sync·내부 도구 sync 로 생기는 도구는 어느 테이블에도 행이 없어 기본 차단이다.
-- 비활성(is_active=0) 도구도 포함한다 — 재활성화 시 기존 동작을 그대로 복원하기 위함.

INSERT INTO tool_access_default (tool_id, granted_by)
SELECT tc.tool_id, NULL
FROM tool_catalog tc
WHERE NOT EXISTS (
    SELECT 1 FROM tool_access_default d WHERE d.tool_id = tc.tool_id
);
