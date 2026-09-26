-- mcp-identity-header Design §3.3 — 서버별 호출자 신원 헤더 설정.
-- 값이 있으면 이 서버로 나가는 tool 호출마다 idt 가 실행 주체의 HS256 토큰을
-- 새로 발급해 헤더에 싣는다. 서명 비밀을 포함하므로 auth_config_enc 와 같은
-- SecretCipher 로 암호화한다.
--
-- auth_config_enc 와 컬럼을 나눈 이유: MCP 서버 수정(PUT)은 auth_config 를
-- 통째로 교체한다. 같은 JSON 에 두면 API 키만 바꿀 때 서명 비밀이 지워진다.

ALTER TABLE mcp_server_registry
    ADD COLUMN identity_config_enc TEXT NULL
    COMMENT '호출자 신원 헤더 설정(header_name·claim_name·claim_source·issuer·audience·secret·ttl) 암호화 JSON. NULL 이면 신원 헤더 미사용 — 기존 동작과 동일';
