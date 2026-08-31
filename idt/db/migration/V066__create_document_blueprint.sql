-- golden-sample-blueprint Design §3.3 (V066): Golden Sample 에서 추출한 발표자료 양식 blueprint.
-- blueprint_json 에 style·patterns·narrative·font_mapping·warnings 를 직렬화 (schema_version 으로 하위호환).
-- 에셋은 AttachmentStore(TTL 삭제) 대신 LONGBLOB 영구 보관 (Design D2).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). 열거값은 VARCHAR(애플리케이션 검증).
-- ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE document_blueprint (
    id             VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'blueprint 식별자 UUID',
    name           VARCHAR(100) NOT NULL COMMENT '표시 이름',
    description    VARCHAR(500) NOT NULL DEFAULT '' COMMENT '설명',
    source_kind    VARCHAR(10)  NOT NULL COMMENT '원본 종류 pdf 또는 pptx',
    page_count     INT          NOT NULL COMMENT '원본 페이지 수',
    schema_version INT          NOT NULL DEFAULT 1 COMMENT 'blueprint JSON 스키마 버전',
    blueprint_json JSON         NOT NULL COMMENT 'style·patterns·narrative·font_mapping·warnings 직렬화',
    status         VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT '상태 active 또는 inactive',
    created_by     VARCHAR(36)  NOT NULL COMMENT '등록 관리자 사용자 식별자',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    KEY idx_document_blueprint_status (status)
) ENGINE=InnoDB COMMENT='Golden Sample 에서 추출한 발표자료 양식 blueprint';

CREATE TABLE document_blueprint_asset (
    id           VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '에셋 식별자 UUID',
    blueprint_id VARCHAR(36) NOT NULL COMMENT '소속 document_blueprint.id',
    kind         VARCHAR(20) NOT NULL COMMENT '에셋 종류 logo 또는 decoration 또는 cover',
    mime         VARCHAR(50) NOT NULL COMMENT 'MIME 타입',
    width        INT         NOT NULL COMMENT '픽셀 너비',
    height       INT         NOT NULL COMMENT '픽셀 높이',
    sha256       CHAR(64)    NOT NULL COMMENT '이미지 내용 해시',
    box_json     JSON        NOT NULL COMMENT '슬라이드 비율 좌표 x y w h',
    adopted      TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '관리자 채택 여부',
    data         LONGBLOB    NOT NULL COMMENT '이미지 바이트 — TTL 없는 영구 보관',
    created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    KEY idx_document_blueprint_asset_bp (blueprint_id)
) ENGINE=InnoDB COMMENT='blueprint 로고·장식·표지 이미지 에셋';
