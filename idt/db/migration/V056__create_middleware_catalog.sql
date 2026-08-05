-- builtin-middleware D2: 미들웨어 카탈로그 — 빌트인/강제 플래그와 기본 설정의 런타임 SoT.
-- 시드는 본 마이그레이션의 INSERT가 유일한 공급원 (부팅 sync 없음 — D3).
-- FK 참조 테이블(agent_definition)은 SQLAlchemy 생성 — CHARSET/COLLATE 명시 금지,
-- ENGINE=InnoDB만 지정 (MySQL errno 3780 선례, V037 주석 참조).
CREATE TABLE middleware_catalog (
    id              VARCHAR(36)  NOT NULL COMMENT 'PK (UUID)',
    middleware_type VARCHAR(50)  NOT NULL COMMENT '미들웨어 유형 식별자 (model_retry/tool_retry/model_fallback/model_call_limit)',
    name            VARCHAR(100) NOT NULL COMMENT '표시 이름 (폼·관리자 화면)',
    description     VARCHAR(500) NOT NULL COMMENT '설명 — 폼 안내 문구',
    is_builtin      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '빌트인 여부 — 에이전트 생성 시 기본 적용(사용자 해제 가능) · 관리자 토글',
    is_enforced     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '강제 여부 — 실행 시 에이전트 스냅샷과 무관하게 병합 적용(사용자 해제 불가) · 관리자 토글',
    default_config  JSON         NOT NULL COMMENT '기본 설정값 (관리자 편집) — 런타임 설정 단일 소스 · 1차는 에이전트별 오버라이드 없음',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '활성 여부 — 비활성 시 빌트인/강제 판정에서 제외',
    sort_order      INT          NOT NULL DEFAULT 0 COMMENT '적용 순서 (미들웨어 체인 순서)',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_middleware_catalog_type (middleware_type)
) ENGINE=InnoDB
  COMMENT='미들웨어 카탈로그 — 빌트인/강제/기본 설정의 런타임 SoT (관리자 관리)';

-- builtin-middleware D5: 에이전트별 적용 미들웨어 스냅샷 (행 존재 = 적용).
CREATE TABLE agent_middleware (
    id              VARCHAR(36) NOT NULL COMMENT 'PK (UUID)',
    agent_id        VARCHAR(36) NOT NULL COMMENT '에이전트 FK (agent_definition.id)',
    middleware_type VARCHAR(50) NOT NULL COMMENT '적용 미들웨어 유형 (middleware_catalog.middleware_type 참조값)',
    config          JSON        NULL COMMENT '에이전트별 설정 오버라이드 — 1차 미사용(NULL) · 후속 확장 예약',
    sort_order      INT         NOT NULL DEFAULT 0 COMMENT '적용 순서 (스냅샷 시점 카탈로그 순서)',
    created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_middleware (agent_id, middleware_type),
    CONSTRAINT fk_agent_middleware_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='에이전트별 적용 미들웨어 스냅샷 — 생성 시 빌트인 주입, 폼 수정 시 전체 교체';

-- 시드: 1차 4종 (초기 빌트인 = model_retry + tool_retry, enforced 전부 off — Design D2)
INSERT INTO middleware_catalog
    (id, middleware_type, name, description, is_builtin, is_enforced, default_config, sort_order)
VALUES
    (UUID(), 'model_retry', 'LLM 재시도',
     'LLM 호출 실패 시 지수 백오프로 자동 재시도합니다. 네트워크 불안정 환경에 적합합니다.',
     1, 0, '{"max_retries": 3, "backoff_factor": 2.0, "initial_delay": 1.0}', 10),
    (UUID(), 'tool_retry', '도구 재시도',
     '도구(내부/MCP) 호출 실패 시 지수 백오프로 자동 재시도합니다.',
     1, 0, '{"max_retries": 2, "backoff_factor": 2.0, "initial_delay": 1.0}', 20),
    (UUID(), 'model_fallback', '모델 폴백',
     '주 모델 실패 시 대체 모델로 자동 전환합니다. 대체 모델을 설정해야 동작합니다.',
     0, 0, '{"fallback_models": []}', 30),
    (UUID(), 'model_call_limit', '모델 호출 상한',
     'run당 LLM 호출 횟수를 제한해 무한 루프와 비용 폭주를 방지합니다.',
     0, 0, '{"run_limit": 10, "exit_behavior": "end"}', 40);
