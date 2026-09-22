-- approval-gate Design §3.3 — 도구 축 플래그.
-- SoT 이원화 (V054 is_builtin 과 동형):
--   런타임 SoT = tool_catalog.requires_approval (관리자 토글)
--   ToolMeta.requires_approval_default = 신규 DB 의 sync INSERT 시드 전용
-- upsert 보존 계약: tool_catalog upsert 의 UPDATE 분기 SET 절에 이 컬럼을
-- 넣지 않는다 — sync 재실행이 관리자 설정을 덮으면 안 된다.

ALTER TABLE tool_catalog
    ADD COLUMN requires_approval TINYINT(1) NOT NULL DEFAULT 0
    COMMENT '1이면 이 도구 호출 전 사람 승인 필요 (런타임 SoT, 관리자 토글). 기본 0 이라 기존 도구는 무영향';
