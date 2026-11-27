-- market-index-ytd-chart Design §3.3: 시장 분석 대시보드 올해 지수 차트용 확정 일봉
-- 장중(미확정) 봉은 저장하지 않는다. 같은 (지수, 거래일)을 다시 쓰면 덮어쓴다.
-- 플랫폼 테이블 FK 없음 (market_analysis 모듈 경계).
CREATE TABLE ma_index_daily (
    index_code VARCHAR(8) NOT NULL COMMENT '지수 (KOSPI·KOSDAQ)',
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    open_price DECIMAL(12,2) NOT NULL COMMENT '시가',
    high_price DECIMAL(12,2) NOT NULL COMMENT '고가',
    low_price DECIMAL(12,2) NOT NULL COMMENT '저가',
    close_price DECIMAL(12,2) NOT NULL COMMENT '종가',
    created_at DATETIME NOT NULL COMMENT '적재 시각 (UTC)',
    PRIMARY KEY (index_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 지수 확정 일봉';
