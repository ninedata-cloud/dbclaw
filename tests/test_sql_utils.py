"""测试 SQL 工具函数"""
import pytest
from backend.utils.sql_utils import extract_oracle_bind_variables, prepare_oracle_explain_sql


def test_extract_oracle_bind_variables_simple():
    """测试简单的绑定变量提取"""
    sql = "SELECT * FROM t WHERE id = :id"
    result = extract_oracle_bind_variables(sql)
    assert result == ['id']


def test_extract_oracle_bind_variables_multiple():
    """测试多个绑定变量"""
    sql = "SELECT * FROM t WHERE id = :id AND name = :name"
    result = extract_oracle_bind_variables(sql)
    assert result == ['id', 'name']


def test_extract_oracle_bind_variables_numeric():
    """测试数字绑定变量"""
    sql = "SELECT * FROM t WHERE id = :1 AND name = :2"
    result = extract_oracle_bind_variables(sql)
    assert result == ['1', '2']


def test_extract_oracle_bind_variables_ignore_string_literals():
    """测试忽略字符串字面量中的冒号"""
    sql = "SELECT * FROM t WHERE name = 'test:value' AND id = :id"
    result = extract_oracle_bind_variables(sql)
    assert result == ['id']


def test_extract_oracle_bind_variables_complex():
    """测试复杂 SQL"""
    sql = """
    SELECT * FROM user
    WHERE name = 'user:admin'
      AND id = :user_id
      AND status = :status
      AND created_at > :start_date
    """
    result = extract_oracle_bind_variables(sql)
    assert result == ['user_id', 'status', 'start_date']


def test_extract_oracle_bind_variables_duplicate():
    """测试重复的绑定变量（应该去重）"""
    sql = "SELECT * FROM t WHERE id = :id OR parent_id = :id"
    result = extract_oracle_bind_variables(sql)
    assert result == ['id']


def test_extract_oracle_bind_variables_no_binds():
    """测试没有绑定变量的 SQL"""
    sql = "SELECT * FROM t WHERE id = 123"
    result = extract_oracle_bind_variables(sql)
    assert result == []


def test_prepare_oracle_explain_sql_with_binds():
    """测试准备 EXPLAIN PLAN 语句（带绑定变量）"""
    sql = "SELECT * FROM t WHERE id = :id"
    explain_sql, bind_params = prepare_oracle_explain_sql(sql, "STMT_123")

    assert "EXPLAIN PLAN SET STATEMENT_ID = 'STMT_123' FOR" in explain_sql
    assert sql in explain_sql
    assert bind_params == {'id': None}


def test_prepare_oracle_explain_sql_no_binds():
    """测试准备 EXPLAIN PLAN 语句（无绑定变量）"""
    sql = "SELECT * FROM t WHERE id = 123"
    explain_sql, bind_params = prepare_oracle_explain_sql(sql, "STMT_456")

    assert "EXPLAIN PLAN SET STATEMENT_ID = 'STMT_456' FOR" in explain_sql
    assert sql in explain_sql
    assert bind_params == {}


def test_prepare_oracle_explain_sql_multiple_binds():
    """测试准备 EXPLAIN PLAN 语句（多个绑定变量）"""
    sql = "SELECT * FROM t WHERE id = :id AND name = :name"
    explain_sql, bind_params = prepare_oracle_explain_sql(sql, "STMT_789")

    assert "EXPLAIN PLAN SET STATEMENT_ID = 'STMT_789' FOR" in explain_sql
    assert bind_params == {'id': None, 'name': None}
