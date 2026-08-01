"""db/migration DDL COMMENT 규칙 검증.

규칙(2026-07-25): 테이블 생성 시 테이블 + 전 컬럼 COMMENT 필수,
ALTER로 컬럼을 추가(ADD)/재정의(MODIFY·CHANGE)할 때도 COMMENT 필수
(MODIFY/CHANGE에서 COMMENT를 생략하면 기존 코멘트가 소실된다).

V053 이전 레거시 파일에는 소급 적용하지 않는다 (ENFORCED_FROM 참조).
"""

import re
from pathlib import Path

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "db" / "migration"
ENFORCED_FROM = 54

_CONSTRAINT_PREFIXES = (
    "PRIMARY",
    "UNIQUE",
    "KEY",
    "INDEX",
    "CONSTRAINT",
    "FOREIGN",
    "CHECK",
    "FULLTEXT",
    "SPATIAL",
)
_ALTER_COLUMN_VERBS = ("ADD", "MODIFY", "CHANGE")


def _strip_line_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def _split_top_level(body: str) -> list[str]:
    """괄호 깊이 0의 콤마 기준으로 분할한다 (DECIMAL(10,2) 등 내부 콤마 보호)."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _has_comment(fragment: str) -> bool:
    return re.search(r"\bCOMMENT\b", fragment, re.IGNORECASE) is not None


def _check_create_tables(sql: str) -> list[str]:
    violations: list[str] = []
    for match in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\(",
        sql,
        re.IGNORECASE,
    ):
        table = match.group(1)
        open_paren = match.end() - 1
        depth = 0
        close_paren = open_paren
        for i in range(open_paren, len(sql)):
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
                if depth == 0:
                    close_paren = i
                    break
        body = sql[open_paren + 1 : close_paren]
        tail = sql[close_paren + 1 :].split(";", 1)[0]

        for part in _split_top_level(body):
            first = part.split()[0].strip("`").upper()
            if first in _CONSTRAINT_PREFIXES:
                continue
            column = part.split()[0].strip("`")
            if not _has_comment(part):
                violations.append(f"{table}.{column}: 컬럼 COMMENT 누락")
        if not re.search(r"\bCOMMENT\s*=?\s*'", tail, re.IGNORECASE):
            violations.append(f"{table}: 테이블 COMMENT 누락")
    return violations


def _check_alter_tables(sql: str) -> list[str]:
    violations: list[str] = []
    for match in re.finditer(
        r"ALTER\s+TABLE\s+`?(\w+)`?(.*?);", sql, re.IGNORECASE | re.DOTALL
    ):
        table = match.group(1)
        for clause in _split_top_level(match.group(2)):
            words = clause.split()
            if not words or words[0].upper() not in _ALTER_COLUMN_VERBS:
                continue
            verb = words[0].upper()
            rest = words[1:]
            if rest and rest[0].upper() == "COLUMN":
                rest = rest[1:]
            if not rest or rest[0].strip("`").upper() in _CONSTRAINT_PREFIXES:
                continue  # ADD INDEX / ADD CONSTRAINT 등 컬럼 아님
            column = rest[0].strip("`")
            if not _has_comment(clause):
                violations.append(f"{table}.{column}: {verb} 컬럼 COMMENT 누락")
    return violations


def find_comment_violations(sql: str) -> list[str]:
    sql = _strip_line_comments(sql)
    return _check_create_tables(sql) + _check_alter_tables(sql)


def _migration_version(path: Path) -> int | None:
    match = re.match(r"V(\d+)__", path.name)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# 검증기 자체 단위 테스트 (픽스처 DDL)
# ---------------------------------------------------------------------------


GOOD_CREATE = """
CREATE TABLE sample (
    id     CHAR(36)      NOT NULL COMMENT 'UUID PK',
    amount DECIMAL(10,2) NOT NULL DEFAULT 0 COMMENT '금액',
    PRIMARY KEY (id),
    KEY idx_sample_amount (amount)
) ENGINE=InnoDB
  COMMENT='샘플 테이블';
"""


def test_good_create_passes():
    assert find_comment_violations(GOOD_CREATE) == []


def test_create_missing_column_comment_detected():
    sql = """
    CREATE TABLE sample (
        id   CHAR(36)     NOT NULL COMMENT 'UUID PK',
        name VARCHAR(100) NOT NULL,
        PRIMARY KEY (id)
    ) ENGINE=InnoDB COMMENT='샘플';
    """
    assert find_comment_violations(sql) == ["sample.name: 컬럼 COMMENT 누락"]


def test_create_missing_table_comment_detected():
    sql = """
    CREATE TABLE sample (
        id CHAR(36) NOT NULL COMMENT 'UUID PK',
        PRIMARY KEY (id)
    ) ENGINE=InnoDB;
    """
    assert find_comment_violations(sql) == ["sample: 테이블 COMMENT 누락"]


def test_alter_add_without_comment_detected():
    sql = "ALTER TABLE sample ADD COLUMN flag TINYINT(1) NOT NULL DEFAULT 0;"
    assert find_comment_violations(sql) == ["sample.flag: ADD 컬럼 COMMENT 누락"]


def test_alter_add_with_comment_passes():
    sql = (
        "ALTER TABLE sample "
        "ADD COLUMN flag TINYINT(1) NOT NULL DEFAULT 0 COMMENT '활성 여부';"
    )
    assert find_comment_violations(sql) == []


def test_alter_modify_without_comment_detected():
    sql = "ALTER TABLE sample MODIFY name VARCHAR(200) NOT NULL;"
    assert find_comment_violations(sql) == ["sample.name: MODIFY 컬럼 COMMENT 누락"]


def test_alter_add_index_is_ignored():
    sql = "ALTER TABLE sample ADD INDEX idx_sample_name (name);"
    assert find_comment_violations(sql) == []


def test_data_only_migration_passes():
    sql = "INSERT INTO permissions (id, name) VALUES ('1', 'admin');"
    assert find_comment_violations(sql) == []


def test_sql_line_comment_does_not_satisfy_rule():
    sql = """
    -- COMMENT 규칙 언급하는 주석
    CREATE TABLE sample (
        id CHAR(36) NOT NULL,
        PRIMARY KEY (id)
    ) ENGINE=InnoDB;
    """
    assert find_comment_violations(sql) == [
        "sample.id: 컬럼 COMMENT 누락",
        "sample: 테이블 COMMENT 누락",
    ]


# ---------------------------------------------------------------------------
# 실제 마이그레이션 파일 검사 (V054 이후 강제)
# ---------------------------------------------------------------------------


def test_enforced_migrations_have_ddl_comments():
    assert MIGRATION_DIR.is_dir(), f"마이그레이션 폴더 없음: {MIGRATION_DIR}"
    failures: list[str] = []
    for path in sorted(MIGRATION_DIR.glob("V*.sql")):
        version = _migration_version(path)
        if version is None or version < ENFORCED_FROM:
            continue
        sql = path.read_text(encoding="utf-8")
        for violation in find_comment_violations(sql):
            failures.append(f"{path.name}: {violation}")
    assert not failures, (
        "DDL COMMENT 규칙 위반 (테이블+전 컬럼 COMMENT 필수):\n"
        + "\n".join(failures)
    )
