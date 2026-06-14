-- V024__create_user_profiles.sql
-- agent-user-context Design §5.2:
--   사용자 사내 메타데이터 (이름/직급/사번/입사일).
--   users(인증) 과 분리.
--   display_name 은 NOT NULL — 회원가입 시 필수. 기존 회원은 V030 백필.

CREATE TABLE user_profiles (
    user_id       BIGINT      NOT NULL PRIMARY KEY,
    display_name  VARCHAR(100) NOT NULL,
    position      VARCHAR(50)  NULL,
    employee_no   VARCHAR(50)  NULL,
    joined_at     DATE         NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_profiles_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_profiles_emp_no (employee_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
