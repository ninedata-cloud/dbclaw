"""SQL 相关的工具函数"""
import re
from typing import List, Tuple


def extract_oracle_bind_variables(sql_text: str) -> List[str]:
    """
    从 Oracle SQL 中提取绑定变量名称。

    排除字符串字面量中的冒号，只提取真正的绑定变量。

    Args:
        sql_text: SQL 文本

    Returns:
        绑定变量名称列表（不包含冒号前缀）

    Examples:
        >>> extract_oracle_bind_variables("SELECT * FROM t WHERE id = :id")
        ['id']
        >>> extract_oracle_bind_variables("SELECT * FROM t WHERE name = 'test:value' AND id = :id")
        ['id']
        >>> extract_oracle_bind_variables("SELECT * FROM t WHERE id = :1 AND name = :2")
        ['1', '2']
    """
    # 先移除所有字符串字面量（单引号包围的内容），避免误匹配
    sql_without_strings = re.sub(r"'[^']*'", '', sql_text)

    # 查找所有绑定变量：冒号后跟字母数字下划线
    bind_vars = re.findall(r':(\w+)', sql_without_strings)

    # 去重并保持顺序
    seen = set()
    unique_vars = []
    for var in bind_vars:
        if var not in seen:
            seen.add(var)
            unique_vars.append(var)

    return unique_vars


def prepare_oracle_explain_sql(sql_text: str, statement_id: str) -> Tuple[str, dict]:
    """
    准备 Oracle EXPLAIN PLAN 语句和绑定变量参数。

    Args:
        sql_text: 要分析的 SQL 文本
        statement_id: 执行计划的唯一标识符

    Returns:
        (explain_sql, bind_params) 元组
        - explain_sql: EXPLAIN PLAN 语句
        - bind_params: 绑定变量字典，所有变量值为 None

    Examples:
        >>> sql = "SELECT * FROM t WHERE id = :id"
        >>> explain_sql, params = prepare_oracle_explain_sql(sql, "STMT_123")
        >>> explain_sql
        "EXPLAIN PLAN SET STATEMENT_ID = 'STMT_123' FOR SELECT * FROM t WHERE id = :id"
        >>> params
        {'id': None}
    """
    bind_vars = extract_oracle_bind_variables(sql_text)
    explain_sql = f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql_text}"

    # 为所有绑定变量提供 None 值
    bind_params = {var: None for var in bind_vars} if bind_vars else {}

    return explain_sql, bind_params
