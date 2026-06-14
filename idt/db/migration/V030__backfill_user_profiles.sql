-- V030__backfill_user_profiles.sql
-- agent-user-context Design §5.2:
--   V024 적용 직후 기존 users 회원에게 display_name 자동 백필.
--   email local-part를 임시 이름으로 사용 (예: hong@company.com → "hong").
--   사용자가 이후 프로필 수정 API로 정상 이름 설정 가능.

INSERT INTO user_profiles (user_id, display_name)
SELECT u.id, SUBSTRING_INDEX(u.email, '@', 1)
FROM users u
LEFT JOIN user_profiles p ON p.user_id = u.id
WHERE p.user_id IS NULL;
