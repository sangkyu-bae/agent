-- prompt-composer: 시스템 프롬프트 버전 이력
-- Design: docs/02-design/features/prompt-composer.design.md §3.3
--
-- schema_version (Design Q4): sections JSON 구조가 바뀔 때 증가시켜 과거 행을
--   분기 파싱한다. 이력 테이블은 지우지 않아 장기 보관되므로, 나중에 추가하면
--   전 행 백필이 필요해진다 — 지금 넣는 비용이 사실상 0이다.
-- uq_session_version: 동시 재생성 시 version_no 중복을 DB 가 막는다 (Design E10).
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 미명시로 prompt_session 과 정합.

CREATE TABLE prompt_version (
  id              VARCHAR(36)  PRIMARY KEY         COMMENT '버전 ID (uuid4)',
  session_id      VARCHAR(36)  NOT NULL            COMMENT '소속 prompt_session ID',
  version_no      INT          NOT NULL            COMMENT '세션 내 버전 번호 (1부터 증가)',
  schema_version  SMALLINT     NOT NULL DEFAULT 1  COMMENT 'sections JSON 구조 버전. 구조 변경 시 증가시켜 과거 행 파싱 분기 (Design Q4)',
  sections        JSON         NOT NULL            COMMENT '구조화 섹션 — purpose / roles / tool_guides / principles 4키',
  assembled       TEXT         NOT NULL            COMMENT '서버가 결정적으로 조립한 최종 시스템 프롬프트 문자열',
  intent_snapshot JSON         NULL                COMMENT '생성에 사용된 IntentResult 원본 스냅샷. 미주입이거나 degraded 면 NULL',
  tool_ids        JSON         NOT NULL            COMMENT '생성에 실제 반영된 tool_id 배열 (환각 폐기·미존재 제외 후)',
  degraded        TINYINT(1)   NOT NULL DEFAULT 0  COMMENT 'LLM 실패로 규칙기반 폴백이 쓰였는지 여부',
  reason          VARCHAR(500) NULL                COMMENT 'degraded 사유(error|timeout|schema|empty) 또는 관측 메모',
  elapsed_ms      INT          NOT NULL DEFAULT 0  COMMENT 'LLM 호출 소요 시간(ms). 관측용',
  created_at      DATETIME     NOT NULL            COMMENT '버전 생성 시각 (UTC)',
  UNIQUE KEY uq_session_version (session_id, version_no),
  CONSTRAINT fk_prompt_version_session FOREIGN KEY (session_id)
    REFERENCES prompt_session(id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='시스템 프롬프트 버전 이력 — 생성 1회당 1행, 근거(의도·도구) 동봉';
