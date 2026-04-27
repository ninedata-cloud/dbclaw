import pytest

from backend.utils.version_parser import simplify_version


@pytest.mark.unit
def test_simplify_version_parses_mysql_oracle_and_sqlserver():
    mysql = simplify_version("8.0.36-commercial", "mysql")
    assert mysql["short"] == "MySQL 8.0.36"
    assert mysql["full"] == "8.0.36-commercial"

    oracle = simplify_version(
        "Oracle Database 19.0.0.0.0 Enterprise Edition Release 19.0.0.0.0",
        "oracle",
    )
    assert oracle["short"] == "Oracle 19.0.0.0.0"
    assert "Enterprise Edition" in oracle["details"]

    sqlserver = simplify_version(
        "Microsoft SQL Server 15.0.4261.1 (X64) Developer Edition",
        "sqlserver",
    )
    assert sqlserver["short"] == "SQL Server 15.0.4261.1"
    assert "(X64)" in sqlserver["details"]


@pytest.mark.unit
def test_simplify_version_handles_unknown_and_empty_inputs():
    empty = simplify_version("", "mysql")
    assert empty == {"short": "未知版本", "full": "", "details": ""}

    unknown = simplify_version("CustomDB version 1 build 2", "custom")
    assert unknown["short"] == "CustomDB version 1 build 2"
    assert unknown["details"] == ""


@pytest.mark.unit
def test_simplify_version_truncates_very_long_fallback():
    raw = "x" * 80
    simplified = simplify_version(raw, "unsupported")
    assert simplified["short"] == ("x" * 50) + "..."
    assert simplified["full"] == raw
    assert simplified["details"] == ("x" * 30)
