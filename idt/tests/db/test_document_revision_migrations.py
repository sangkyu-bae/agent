"""document-revision 마이그레이션 존재·핵심 컬럼 — Design §3.3 (V095~V097).

모델(SQLAlchemy)과 DDL 의 컬럼 집합이 어긋나면 운영 DB 조회가 깨지므로 양쪽을 대조한다.
"""

import re
from pathlib import Path

from src.infrastructure.doc_browse.models import DocumentMetadataModel

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "db" / "migration"

_REVISION_COLUMNS = {
    "file_hash",
    "lineage_id",
    "version_no",
    "version_label",
    "effective_date",
    "revision_status",
    "sync_state",
    "superseded_by",
    "superseded_at",
    "revised_by",
}


def _read(prefix: str) -> str:
    files = list(MIGRATION_DIR.glob(f"{prefix}__*.sql"))
    assert len(files) == 1, f"{prefix} 마이그레이션이 정확히 1개여야 함: {files}"
    return files[0].read_text(encoding="utf-8")


def test_v095_adds_all_revision_columns_matching_model() -> None:
    sql = _read("V095")
    added = set(re.findall(r"ADD COLUMN\s+(\w+)", sql))
    assert added == _REVISION_COLUMNS
    assert _REVISION_COLUMNS <= set(DocumentMetadataModel.__table__.columns.keys())
    for index in ("idx_dm_kb_hash", "idx_dm_lineage", "idx_dm_kb_status"):
        assert index in sql


def test_v096_adds_revision_mode() -> None:
    assert re.search(r"ADD COLUMN\s+revision_mode", _read("V096"))


def test_v097_creates_check_log_table() -> None:
    sql = _read("V097")
    assert "CREATE TABLE document_revision_check" in sql
    for col in ("candidates_json", "llm_status", "parse_ms", "decision", "decided_by"):
        assert col in sql
