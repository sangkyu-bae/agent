-- Test users seed (local/dev only)
--
-- 일반 유저 : testuser@sangplus.dev  / Test1234!
-- 관리자    : testadmin@sangplus.dev / Admin1234!
--
-- 주의: 도메인을 .local 로 두면 pydantic EmailStr(email-validator) 가
--      RFC 6762 예약 TLD 라며 422 를 반환하므로 .dev 를 사용한다.
--
-- password_hash 는 프로젝트와 동일한 passlib + bcrypt (cost 12) 로 생성됨.
-- BcryptPasswordHasher.verify() 와 호환.
--
-- 실행:
--   mysql -h $MYSQL_HOST -P $MYSQL_PORT -u $MYSQL_USER -p $MYSQL_DB < scripts/seed_test_users.sql
--
-- 주의: 운영 DB 에는 절대 사용하지 말 것.

INSERT INTO users (email, password_hash, role, status)
VALUES (
    'testuser@sangplus.dev',
    '$2b$12$i/dr1wkGp7ITk4dR9zbUIeMVDTuLX9fW3GMO/d7PEf4WkcXERQCaC',
    'user',
    'approved'
)
ON DUPLICATE KEY UPDATE
    password_hash = VALUES(password_hash),
    role          = VALUES(role),
    status        = VALUES(status);

INSERT INTO users (email, password_hash, role, status)
VALUES (
    'testadmin@sangplus.dev',
    '$2b$12$XvIHwtR6t.je60NEJY11Suj3dW/4/HuRQ4W2MZKW8RgTIZb.PC1Y.',
    'admin',
    'approved'
)
ON DUPLICATE KEY UPDATE
    password_hash = VALUES(password_hash),
    role          = VALUES(role),
    status        = VALUES(status);

-- 정리 (테스트 종료 후)
-- DELETE FROM users WHERE email IN ('testuser@sangplus.dev', 'testadmin@sangplus.dev');
