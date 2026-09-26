-- mcp-identity-header Design §3.3 — 사용자별 메일함 UPN.
-- 신원 헤더가 설정된 MCP 서버(예: Outlook identity 모드)를 호출할 때
-- idt 가 실행 주체의 이 값을 서명 토큰 클레임에 싣는다. 메일함을 도구 인자로
-- 받지 않으므로 LLM·메일 본문이 타인 메일함을 고를 경로가 없다.
--
-- 로그인 email 과 독립이다 (로그인 계정 ≠ 사내 메일함인 경우).
-- NULL 이면 미등록 — 신원 필요 도구는 서버에 요청하기 전에 거부된다.

ALTER TABLE users
    ADD COLUMN mailbox_upn VARCHAR(255) NULL
    COMMENT '관리자가 지정한 사내 메일함 UPN(소문자). 신원 헤더 MCP 호출의 클레임 소스. 로그인 email 과 독립, NULL 이면 메일함 미등록';
