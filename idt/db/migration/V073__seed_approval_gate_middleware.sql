-- approval-gate Design §3.3 — 미들웨어 카탈로그에 승인 게이트 등록.
--
-- is_builtin=0, is_enforced=0 으로 시드하는 이유: 관리자가 명시적으로 켜기
-- 전에는 어떤 에이전트에도 적용되지 않는다 (무회귀). 켠 뒤에도 도구 축
-- (tool_catalog.requires_approval)이 참이어야 실제로 발동한다.
--
-- sort_order=100: 기존 4종(10~40)보다 뒤 — 게이트는 체인 마지막이어야
-- ToolCallLimitMiddleware 등이 먼저 걸러낸 뒤 판정한다.

INSERT INTO middleware_catalog
    (id, middleware_type, name, description,
     is_builtin, is_enforced, default_config, is_active, sort_order)
VALUES
    (UUID(), 'approval_gate', '승인 게이트',
     '부작용 도구 호출 전 사람의 승인을 요구한다. execute_after 로 승인 시각과 집행 시각을 분리할 수 있다.',
     0, 0,
     JSON_OBJECT(
         'mode', 'always',
         'execute_after', NULL,
         'expires_hours', 168,
         'on_expire', 'expire'
     ),
     1, 100);
