-- graph-rag-foundation Design §3.3 (V086): 그래프 RAG 전역 설정 — 단일 행(id 고정).
-- llm 모델 id 는 llm_model.id 소프트 참조(FK 없음 — V065 multimodal_setting 선례).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). 열거값은 VARCHAR(애플리케이션 검증).
-- 범위 검증은 도메인 VO GraphRagSettings.__post_init__ 가 단일 출처.
-- ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE graph_rag_setting (
    id                      VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    rollout_stage           VARCHAR(16)  NOT NULL DEFAULT 'off' COMMENT '노출 단계 off 또는 admin_only 또는 general',
    extraction_enabled      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '업로드 후 자동 추출 여부',
    jev_enabled             TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'Jev 판정 사용 여부 — 끄면 LLM 선택으로 판정',
    link_threshold          DECIMAL(4,3) NOT NULL DEFAULT 0.800 COMMENT '이 확률 이상이면 기존 엔티티에 연결',
    new_threshold           DECIMAL(4,3) NOT NULL DEFAULT 0.400 COMMENT '이 확률 미만이면 새 엔티티 생성',
    extraction_llm_model_id VARCHAR(36)  NULL COMMENT 'llm_model.id 소프트 참조 — 추출용',
    rejudge_llm_model_id    VARCHAR(36)  NULL COMMENT 'llm_model.id 소프트 참조 — 재판정용 NULL이면 추출 모델',
    concurrency             INT          NOT NULL DEFAULT 3 COMMENT '추출 동시 LLM 호출 수',
    max_llm_calls_per_doc   INT          NOT NULL DEFAULT 300 COMMENT '문서당 LLM 호출 상한 — 초과 시 partial',
    candidate_top_k         INT          NOT NULL DEFAULT 5 COMMENT '판정 후보 수 상한',
    max_hops                INT          NOT NULL DEFAULT 2 COMMENT '그래프 검색 최대 탐색 단계',
    graph_rrf_weight        DECIMAL(4,3) NOT NULL DEFAULT 0.500 COMMENT '그래프 결과 RRF 가중치',
    retrieval_timeout_ms    INT          NOT NULL DEFAULT 800 COMMENT '그래프 검색 시간 상한 밀리초',
    entity_types            JSON         NOT NULL COMMENT '허용 엔티티 타입 목록',
    relation_types          JSON         NOT NULL COMMENT '허용 관계 타입 목록',
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='그래프 RAG 전역 설정 — 단일 행';

INSERT INTO graph_rag_setting (id, entity_types, relation_types) VALUES (
  'c0000000-0000-4000-8000-000000000001',
  JSON_ARRAY('상품·서비스','대상','조건·요건','규정·문서','조문','용어','조직·부서','수치기준','절차','기타'),
  JSON_ARRAY('적용대상','요건','예외','한도','정의','참조','포함','담당','기타'));
