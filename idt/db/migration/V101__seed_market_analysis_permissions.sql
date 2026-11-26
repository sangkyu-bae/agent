-- stock-analysis-agents Design DD10, §3.3: 시장 분석 권한 2개와 설정 기본 행
-- PermissionCode enum(src/domain/permission/value_objects.py)과 동기화.
-- role 기본 권한(role_permissions)에는 넣지 않는다 — 관리자가 사용자에게 부여한 경우만 본다 (Plan D5).
-- admin 은 코드와 무관하게 열람·관리할 수 있다 (AccessPolicy).
INSERT INTO permissions (code, description) VALUES
    ('MARKET_ANALYSIS_VIEW',   '시장 분석 화면 열람'),
    ('MARKET_ANALYSIS_MANAGE', '시장 분석 설정·원칙 관리');

-- 기본값은 src/domain/market_analysis/setting.py MarketAnalysisSetting 과 같다.
-- 자동 분석은 꺼진 채로 시작한다 (Plan FR-01).
INSERT INTO ma_setting (
    id, enabled, round_times, max_per_round, max_per_day,
    max_concurrent_stocks, max_concurrent_runs, signal_rules, rule_params,
    ranking_kinds, ranking_limit, condition_seqs, intraday_entry_allowed,
    slot_count, min_score_by_regime, min_rr, max_stop_pct, min_stop_pct,
    max_principles, principle_auto_activate, run_as_user_id,
    kis_server_id, dart_server_id, perplexity_server_id, updated_by, updated_at
) VALUES (
    1, 0, JSON_ARRAY('10:00', '14:00', '18:10'), 20, 50,
    2, 4,
    JSON_ARRAY('ma_cross', 'rsi_threshold', 'bollinger_break', 'macd_cross',
               'volume_spike', 'gap', 'closing_strength'),
    NULL,
    JSON_ARRAY('volume', 'fluctuation', 'volume_power'), 30, JSON_ARRAY(), 1,
    10,
    JSON_OBJECT('strong_bull', 5, 'bull', 6, 'neutral', 6, 'bear', 7, 'strong_bear', 8),
    2.00, 7.00, 2.00,
    10, 0, NULL,
    NULL, NULL, NULL, NULL, UTC_TIMESTAMP()
);
