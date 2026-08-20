-- prompt-composer: 시스템 프롬프트 생성 세션
-- Design: docs/02-design/features/prompt-composer.design.md §3.3
--
-- agent_id 에 FK 를 걸지 않는다 (Design §3.3):
--   에이전트 삭제가 이력 삭제로 전이되면 "왜 이 프롬프트가 나왔는가"의 기록이
--   사라진다. 정합성은 백필 API(PATCH /sessions/{id}) 가 담당한다.
-- ⚠️ FK 콜레이션 주의(errno 3780, V037/V038 선례): 테이블 레벨 CHARSET/COLLATE
--   미명시로 DB 기본값 상속. ENGINE=InnoDB 만 명시한다.

CREATE TABLE prompt_session (
  id           VARCHAR(36)  PRIMARY KEY COMMENT '세션 ID (uuid4)',
  user_id      VARCHAR(36)  NOT NULL    COMMENT '생성 요청 사용자 ID (조회 인가 기준)',
  agent_id     VARCHAR(36)  NULL        COMMENT '바인딩된 에이전트 ID. 생성 시점엔 미저장 상태라 NULL 허용(Design D5). FK 미설정 — 에이전트 삭제가 이력 삭제로 전이되면 안 됨',
  user_request TEXT         NOT NULL    COMMENT '최초 자연어 요청 원문 (최대 1000자, 서버 검증)',
  created_at   DATETIME     NOT NULL    COMMENT '세션 생성 시각 (UTC)',
  updated_at   DATETIME     NOT NULL    COMMENT '수정 시각 (UTC). agent_id 백필 시 갱신',
  KEY ix_prompt_session_user (user_id, created_at),
  KEY ix_prompt_session_agent (agent_id)
) ENGINE=InnoDB COMMENT='시스템 프롬프트 생성 세션 — 하나의 요청에서 파생된 버전들의 묶음';
