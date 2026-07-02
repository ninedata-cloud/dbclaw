"""Shared database type constants and compatibility helpers."""

from __future__ import annotations

from typing import Optional


OCEANBASE_MYSQL = "oceanbase-mysql"

MYSQL_FAMILY_DB_TYPES = {"mysql", "tdsql-c-mysql", OCEANBASE_MYSQL}
POSTGRES_FAMILY_DB_TYPES = {"postgresql", "opengauss"}

SUPPORTED_DB_TYPES = {
    "mysql",
    "postgresql",
    "sqlserver",
    "oracle",
    "tdsql-c-mysql",
    OCEANBASE_MYSQL,
    "opengauss",
    "hana",
}

DB_TYPE_PATTERN = (
    "^(mysql|postgresql|sqlserver|oracle|tdsql-c-mysql|"
    "oceanbase-mysql|opengauss|hana)$"
)


def normalize_db_type(db_type: Optional[str]) -> Optional[str]:
    if not db_type:
        return None

    value = str(db_type).strip().lower()
    aliases = {
        "postgres": "postgresql",
        "pg": "postgresql",
        "mssql": "sqlserver",
        "sql_server": "sqlserver",
        "tdsql_c_mysql": "tdsql-c-mysql",
        "oceanbase": OCEANBASE_MYSQL,
        "oceanbase_mysql": OCEANBASE_MYSQL,
        "ob_mysql": OCEANBASE_MYSQL,
        "ob-mysql": OCEANBASE_MYSQL,
    }
    return aliases.get(value, value)


def is_mysql_family(db_type: Optional[str]) -> bool:
    return normalize_db_type(db_type) in MYSQL_FAMILY_DB_TYPES


def is_postgres_family(db_type: Optional[str]) -> bool:
    return normalize_db_type(db_type) in POSTGRES_FAMILY_DB_TYPES


def is_supported_db_type(db_type: Optional[str]) -> bool:
    return normalize_db_type(db_type) in SUPPORTED_DB_TYPES


def compatibility_db_types(db_type: Optional[str]) -> list[str]:
    normalized = normalize_db_type(db_type)
    if not normalized:
        return ["general"]
    if normalized == "tdsql-c-mysql":
        return ["tdsql-c-mysql", "mysql", "general"]
    if normalized == OCEANBASE_MYSQL:
        return [OCEANBASE_MYSQL, "oceanbase", "mysql", "general"]
    if normalized == "opengauss":
        return ["opengauss", "postgresql", "general"]
    return [normalized, "general"]
