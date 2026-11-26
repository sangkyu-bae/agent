-- stock-analysis-agents Design §3.3: 시장 분석 모듈 테이블 (ma_ 접두, 13개)
-- additive 변경. 분리 가능하도록 플랫폼 테이블(에이전트·사용자)에는 FK 를 걸지 않는다 (Design §1.1-3, DD8).
-- 모듈 안 테이블끼리만 FK 를 둔다. 시각은 UTC, 거래일은 KST 날짜.
CREATE TABLE ma_setting (
    id INT NOT NULL COMMENT '설정 행 ID (항상 1)',
    enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '자동 분석 스위치',
    round_times JSON NOT NULL COMMENT '회차 시각 목록 (KST HH:MM)',
    max_per_round INT NOT NULL DEFAULT 20 COMMENT '회차당 최대 분석 종목 수',
    max_per_day INT NOT NULL DEFAULT 50 COMMENT '하루 최대 분석 종목 수',
    max_concurrent_stocks INT NOT NULL DEFAULT 2 COMMENT '동시 분석 종목 수',
    max_concurrent_runs INT NOT NULL DEFAULT 4 COMMENT '동시 에이전트 실행 수',
    signal_rules JSON NOT NULL COMMENT '분석 대상으로 삼을 신호 규칙 목록',
    rule_params JSON NULL COMMENT '신호 규칙 파라미터 (scan_signals rule_params)',
    ranking_kinds JSON NOT NULL COMMENT '후보 수집에 쓰는 순위 종류',
    ranking_limit INT NOT NULL DEFAULT 30 COMMENT '순위 종류별 후보 수',
    condition_seqs JSON NOT NULL COMMENT 'HTS 조건검색 seq 목록',
    intraday_entry_allowed TINYINT(1) NOT NULL DEFAULT 1 COMMENT '장중 회차 진입 허용',
    slot_count INT NOT NULL DEFAULT 10 COMMENT '가상 계좌 슬롯 수',
    min_score_by_regime JSON NOT NULL COMMENT '시장 체제별 최소 매수 점수',
    min_rr DECIMAL(5,2) NOT NULL DEFAULT 2.00 COMMENT '최소 손익비',
    max_stop_pct DECIMAL(5,2) NOT NULL DEFAULT 7.00 COMMENT '최대 손절폭 (%)',
    min_stop_pct DECIMAL(5,2) NOT NULL DEFAULT 2.00 COMMENT '최소 손절폭 (%)',
    max_principles INT NOT NULL DEFAULT 10 COMMENT '판단에 넣을 활성 원칙 최대 수',
    principle_auto_activate TINYINT(1) NOT NULL DEFAULT 0 COMMENT '원칙 후보 자동 활성 여부',
    run_as_user_id VARCHAR(100) NULL COMMENT '에이전트 실행 신원 (사용자 ID)',
    kis_server_id VARCHAR(36) NULL COMMENT 'KIS MCP 서버 ID',
    dart_server_id VARCHAR(36) NULL COMMENT 'DART MCP 서버 ID',
    perplexity_server_id VARCHAR(36) NULL COMMENT 'Perplexity MCP 서버 ID',
    updated_by VARCHAR(100) NULL COMMENT '마지막 수정자 (사용자 ID)',
    updated_at DATETIME NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 모듈 설정 (단일 행)';

CREATE TABLE ma_role_agent (
    role VARCHAR(32) NOT NULL COMMENT '역할 (section_technical 등 11종)',
    agent_id VARCHAR(36) NOT NULL COMMENT '매핑한 빌더 에이전트 ID',
    updated_by VARCHAR(100) NULL COMMENT '마지막 수정자 (사용자 ID)',
    updated_at DATETIME NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 역할별 담당 에이전트';

CREATE TABLE ma_round (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '회차 ID',
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    slot CHAR(5) NOT NULL COMMENT '회차 시각 (KST HH:MM)',
    kind VARCHAR(16) NOT NULL COMMENT 'intraday|close',
    run_trigger VARCHAR(16) NOT NULL COMMENT 'auto|manual',
    status VARCHAR(16) NOT NULL COMMENT 'running|done|skipped|failed|abandoned',
    skip_reason VARCHAR(32) NULL COMMENT '건너뜀 사유 (DISABLED·WEEKEND·HOLIDAY·BUSY)',
    candidates INT NOT NULL DEFAULT 0 COMMENT '수집한 후보 종목 수',
    signaled INT NOT NULL DEFAULT 0 COMMENT '신호가 난 종목 수',
    analyzed INT NOT NULL DEFAULT 0 COMMENT '분석 완료 종목 수',
    over_cap INT NOT NULL DEFAULT 0 COMMENT '상한 초과로 분석하지 않은 종목 수',
    failed INT NOT NULL DEFAULT 0 COMMENT '분석 실패 종목 수',
    total_tokens INT NOT NULL DEFAULT 0 COMMENT '회차 토큰 합계',
    total_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '회차 비용 합계 (USD)',
    error TEXT NULL COMMENT '회차 실패 사유',
    started_at DATETIME NOT NULL COMMENT '시작 시각 (UTC)',
    finished_at DATETIME NULL COMMENT '종료 시각 (UTC)',
    PRIMARY KEY (id),
    UNIQUE KEY uq_ma_round_slot (trade_date, slot, run_trigger),
    KEY ix_ma_round_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 회차 (UNIQUE 로 다중 인스턴스 1회 실행 보장)';

CREATE TABLE ma_round_item (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '회차 종목 ID',
    round_id BIGINT NOT NULL COMMENT '회차 ID',
    symbol VARCHAR(16) NOT NULL COMMENT '종목 코드',
    name VARCHAR(100) NULL COMMENT '종목명',
    signals JSON NOT NULL COMMENT '발생한 신호 (규칙명과 값)',
    status VARCHAR(16) NOT NULL COMMENT 'queued|analyzing|done|failed|over_cap|duplicate|held',
    error VARCHAR(500) NULL COMMENT '실패 사유',
    report_id BIGINT NULL COMMENT '생성된 리포트 ID',
    tokens INT NOT NULL DEFAULT 0 COMMENT '종목 토큰 합계',
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '종목 비용 합계 (USD)',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_round_item_round (round_id),
    KEY ix_ma_round_item_symbol (symbol, created_at),
    CONSTRAINT fk_ma_round_item_round FOREIGN KEY (round_id)
        REFERENCES ma_round (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 회차별 종목 처리 결과';

CREATE TABLE ma_report (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '리포트 ID',
    symbol VARCHAR(16) NOT NULL COMMENT '종목 코드',
    name VARCHAR(100) NULL COMMENT '종목명',
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    round_id BIGINT NULL COMMENT '만든 회차 ID',
    provisional TINYINT(1) NOT NULL DEFAULT 0 COMMENT '미확정 봉 기반 여부',
    signals JSON NOT NULL COMMENT '분석 계기가 된 신호',
    header_facts JSON NULL COMMENT '머리 사실 (도구 결과에서 결정론 렌더)',
    strategy MEDIUMTEXT NULL COMMENT '투자 시나리오·리스크 본문',
    summary TEXT NULL COMMENT '핵심 요약',
    regime VARCHAR(16) NULL COMMENT '분석 시점 시장 체제',
    status VARCHAR(16) NOT NULL COMMENT 'running|done|partial|failed',
    tokens INT NOT NULL DEFAULT 0 COMMENT '리포트 토큰 합계',
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '리포트 비용 합계 (USD)',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_report_date (trade_date),
    KEY ix_ma_report_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 종목 리포트';

CREATE TABLE ma_report_section (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '섹션 ID',
    report_id BIGINT NOT NULL COMMENT '리포트 ID',
    role VARCHAR(32) NOT NULL COMMENT '섹션 역할',
    status VARCHAR(16) NOT NULL COMMENT 'done|failed|empty',
    content MEDIUMTEXT NULL COMMENT '섹션 본문 (Markdown)',
    run_id VARCHAR(36) NULL COMMENT '에이전트 실행 ID (ai_run)',
    tokens INT NOT NULL DEFAULT 0 COMMENT '섹션 토큰',
    cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '섹션 비용 (USD)',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    PRIMARY KEY (id),
    UNIQUE KEY uq_ma_report_section (report_id, role),
    CONSTRAINT fk_ma_report_section_report FOREIGN KEY (report_id)
        REFERENCES ma_report (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 리포트 섹션';

CREATE TABLE ma_evidence (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '근거 ID',
    report_id BIGINT NOT NULL COMMENT '리포트 ID',
    source VARCHAR(16) NOT NULL COMMENT 'kis|dart|tavily|perplexity',
    tool VARCHAR(64) NOT NULL COMMENT '호출한 도구 이름',
    args JSON NOT NULL COMMENT '도구 인자',
    payload MEDIUMTEXT NULL COMMENT '도구 결과 원문',
    is_error TINYINT(1) NOT NULL DEFAULT 0 COMMENT '도구 오류 여부',
    fetched_at DATETIME NOT NULL COMMENT '조회 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_evidence_report (report_id),
    CONSTRAINT fk_ma_evidence_report FOREIGN KEY (report_id)
        REFERENCES ma_report (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 리포트 근거 (prefetch 도구 결과)';

CREATE TABLE ma_decision (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '판단 ID',
    kind VARCHAR(8) NOT NULL COMMENT 'buy|sell',
    symbol VARCHAR(16) NOT NULL COMMENT '종목 코드',
    name VARCHAR(100) NULL COMMENT '종목명',
    report_id BIGINT NULL COMMENT '근거 리포트 ID (매수 판단)',
    position_id BIGINT NULL COMMENT '대상 포지션 ID (매도 판단·진입 결과)',
    score INT NULL COMMENT '매수 점수 (1~10)',
    decision VARCHAR(16) NOT NULL COMMENT 'enter|skip|hold|sell|adjust',
    target_price DECIMAL(14,2) NULL COMMENT '목표가',
    stop_loss DECIMAL(14,2) NULL COMMENT '손절가',
    investment_period VARCHAR(8) NULL COMMENT '투자 기간 (단기·중기·장기)',
    sector VARCHAR(100) NULL COMMENT '섹터',
    confidence INT NULL COMMENT '확신도 (1~10, 매도 판단)',
    rationale TEXT NULL COMMENT '판단 근거',
    skip_reason TEXT NULL COMMENT '보류 사유 (게이트 사유 포함)',
    gate JSON NULL COMMENT '결정론 게이트 결과',
    principles_used JSON NULL COMMENT '판단에 넣은 원칙 ID 목록',
    price_at_decision DECIMAL(14,2) NULL COMMENT '판단 시점 현재가',
    regime VARCHAR(16) NULL COMMENT '판단 시점 시장 체제',
    provisional TINYINT(1) NOT NULL DEFAULT 0 COMMENT '미확정 봉 기반 여부',
    run_id VARCHAR(36) NULL COMMENT '에이전트 실행 ID (ai_run)',
    created_at DATETIME NOT NULL COMMENT '판단 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_decision_kind (kind, decision, created_at),
    KEY ix_ma_decision_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 매수·매도 판단 (매수 보류는 관심종목)';

CREATE TABLE ma_position (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '포지션 ID',
    symbol VARCHAR(16) NOT NULL COMMENT '종목 코드',
    name VARCHAR(100) NULL COMMENT '종목명',
    sector VARCHAR(100) NULL COMMENT '섹터',
    status VARCHAR(8) NOT NULL COMMENT 'open|closed',
    slot_weight DECIMAL(4,3) NOT NULL DEFAULT 1.000 COMMENT '사용 슬롯 비중',
    entry_price DECIMAL(14,2) NOT NULL COMMENT '진입가',
    entry_at DATETIME NOT NULL COMMENT '진입 시각 (UTC)',
    target_price DECIMAL(14,2) NOT NULL COMMENT '현재 목표가',
    stop_loss DECIMAL(14,2) NOT NULL COMMENT '현재 손절가',
    exit_price DECIMAL(14,2) NULL COMMENT '청산가',
    exit_at DATETIME NULL COMMENT '청산 시각 (UTC)',
    exit_reason VARCHAR(16) NULL COMMENT 'target|stop|judge',
    profit_rate DECIMAL(8,4) NULL COMMENT '실현 수익률 (%)',
    holding_days INT NULL COMMENT '보유 일수',
    buy_decision_id BIGINT NULL COMMENT '진입 근거 매수 판단 ID',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    updated_at DATETIME NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_position_status (status),
    KEY ix_ma_position_symbol (symbol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 가상 계좌 포지션';

CREATE TABLE ma_market_regime (
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    kospi_close DECIMAL(12,2) NULL COMMENT 'KOSPI 종가',
    kosdaq_close DECIMAL(12,2) NULL COMMENT 'KOSDAQ 종가',
    kospi_ma20 DECIMAL(12,2) NULL COMMENT 'KOSPI 20일 이평',
    kospi_ma60 DECIMAL(12,2) NULL COMMENT 'KOSPI 60일 이평',
    regime VARCHAR(16) NOT NULL COMMENT '시장 체제',
    basis JSON NULL COMMENT '판정 근거 (20일 수익률·봉 수 등)',
    created_at DATETIME NOT NULL COMMENT '계산 시각 (UTC)',
    PRIMARY KEY (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 일자별 시장 체제';

CREATE TABLE ma_equity_snapshot (
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    realized_cum_rate DECIMAL(10,4) NOT NULL COMMENT '누적 실현 수익률 (%)',
    open_positions INT NOT NULL COMMENT '보유 종목 수',
    used_slots DECIMAL(5,2) NOT NULL COMMENT '사용 슬롯',
    kospi_cum_rate DECIMAL(10,4) NULL COMMENT 'KOSPI 누적 수익률 (%)',
    kosdaq_cum_rate DECIMAL(10,4) NULL COMMENT 'KOSDAQ 누적 수익률 (%)',
    created_at DATETIME NOT NULL COMMENT '기록 시각 (UTC)',
    PRIMARY KEY (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 일자별 성과 스냅샷';

CREATE TABLE ma_journal (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '저널 ID',
    position_id BIGINT NOT NULL COMMENT '청산된 포지션 ID',
    one_line VARCHAR(300) NULL COMMENT '한 줄 요약',
    situation TEXT NULL COMMENT '상황 분석',
    evaluation TEXT NULL COMMENT '판단 평가',
    lessons JSON NULL COMMENT '교훈 목록',
    tags JSON NULL COMMENT '패턴 태그',
    raw_answer MEDIUMTEXT NULL COMMENT '구조화 실패 시 에이전트 원문',
    run_id VARCHAR(36) NULL COMMENT '에이전트 실행 ID (ai_run)',
    created_at DATETIME NOT NULL COMMENT '작성 시각 (UTC)',
    PRIMARY KEY (id),
    UNIQUE KEY uq_ma_journal_position (position_id),
    CONSTRAINT fk_ma_journal_position FOREIGN KEY (position_id)
        REFERENCES ma_position (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 청산 저널';

CREATE TABLE ma_principle (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '원칙 ID',
    condition_text VARCHAR(500) NOT NULL COMMENT '적용 조건',
    action_text VARCHAR(500) NOT NULL COMMENT '취할 행동',
    reason TEXT NULL COMMENT '근거',
    scope VARCHAR(8) NOT NULL COMMENT 'buy|sell|all',
    priority VARCHAR(8) NOT NULL COMMENT 'high|medium|low',
    confidence INT NOT NULL COMMENT '확신도 (1~10)',
    supporting_count INT NOT NULL DEFAULT 1 COMMENT '근거 거래 수',
    is_active TINYINT(1) NOT NULL DEFAULT 0 COMMENT '판단에 넣는지 여부',
    source_journal_id BIGINT NULL COMMENT '출처 저널 ID',
    updated_by VARCHAR(100) NULL COMMENT '마지막 수정자 (사용자 ID)',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    updated_at DATETIME NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id),
    KEY ix_ma_principle_active (is_active, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 매매 원칙 (저널에서 생성)';
