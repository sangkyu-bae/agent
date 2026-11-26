"""ORM 모델 ↔ V100 DDL 일치 — 테이블·컬럼·COMMENT
가 같아야 한다 (idt/CLAUDE.md DDL 규칙).

stock-analysis-agents design §3.3. 두 곳을 따로 고치다 어긋나는 것을 막는다.
"""

import re
from pathlib import Path

from src.infrastructure.market_analysis import models  # noqa: F401 — 메타데이터 등록
from src.infrastructure.persistence.models.base import Base

_DDL = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migration"
    / "V100__create_market_analysis_tables.sql"
)

EXPECTED_TABLES = {
    "ma_setting",
    "ma_role_agent",
    "ma_round",
    "ma_round_item",
    "ma_report",
    "ma_report_section",
    "ma_evidence",
    "ma_decision",
    "ma_position",
    "ma_market_regime",
    "ma_equity_snapshot",
    "ma_journal",
    "ma_principle",
}


def _ddl_tables() -> dict[str, dict]:
    sql = "\n".join(
        line
        for line in _DDL.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    tables: dict[str, dict] = {}
    for block in re.finditer(
        r"CREATE TABLE (\w+) \((.*?)\n\) ENGINE=.*?COMMENT='([^']*)';", sql, re.S
    ):
        name, body, table_comment = block.group(1), block.group(2), block.group(3)
        columns = {}
        for line in body.splitlines():
            m = re.match(r"\s+(\w+) .*COMMENT '([^']*)',?$", line)
            if m and m.group(1).upper() not in {
                "PRIMARY",
                "UNIQUE",
                "KEY",
                "CONSTRAINT",
            }:
                columns[m.group(1)] = m.group(2)
        tables[name] = {"comment": table_comment, "columns": columns}
    return tables


def test_ddl_declares_expected_tables():
    assert set(_ddl_tables()) == EXPECTED_TABLES


def test_models_match_ddl_columns_and_comments():
    ddl = _ddl_tables()
    for name in EXPECTED_TABLES:
        table = Base.metadata.tables[name]
        assert table.comment == ddl[name]["comment"], name
        model_cols = {c.name: c.comment for c in table.columns}
        assert model_cols == ddl[name]["columns"], name
