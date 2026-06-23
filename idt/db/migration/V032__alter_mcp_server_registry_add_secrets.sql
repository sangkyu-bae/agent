-- naver-search-mcp-integration: transport별 인증/서버 config(Fernet 암호문) 컬럼 추가 (비파괴)
-- 기존 행은 두 컬럼 NULL, transport 기존값('sse') 유지 → 동작 불변
ALTER TABLE mcp_server_registry
    ADD COLUMN auth_config_enc   TEXT NULL COMMENT 'Fernet 암호화된 플랫폼 인증(api_key/profile/headers)' AFTER input_schema,
    ADD COLUMN server_config_enc TEXT NULL COMMENT 'Fernet 암호화된 다운스트림 서버 config(NAVER_CLIENT_ID 등)' AFTER auth_config_enc;
