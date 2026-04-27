"""
数据库版本信息解析和精简工具
"""
import re
from typing import Dict


def simplify_version(full_version: str, db_type: str) -> Dict[str, str]:
    """
    精简数据库版本信息

    Args:
        full_version: 完整版本字符串
        db_type: 数据库类型

    Returns:
        {
            "short": "PostgreSQL 10.9",
            "full": "原始完整版本",
            "details": "on x86_64-pc-linux-gnu, compiled by gcc..."
        }
    """
    if not full_version:
        return {"short": "未知版本", "full": "", "details": ""}

    # 各数据库类型的版本号提取正则
    patterns = {
        "postgresql": r"PostgreSQL\s+([\d.]+)",
        "mysql": r"([\d.]+)",
        "oracle": r"Oracle Database ([\d.]+)",
        "sqlserver": r"Microsoft SQL Server\s+([\d.]+)",
        "opengauss": r"openGauss\s+([\d.]+)",
        "hana": r"HDB\s+([\d.]+)",
        "tdsql": r"([\d.]+)"
    }

    db_type_lower = db_type.lower() if db_type else ""
    pattern = patterns.get(db_type_lower)

    if pattern:
        match = re.search(pattern, full_version)
        if match:
            version_num = match.group(1)

            # 构建精简版本名称
            db_display_name = {
                "postgresql": "PostgreSQL",
                "mysql": "MySQL",
                "oracle": "Oracle",
                "sqlserver": "SQL Server",
                "opengauss": "openGauss",
                "hana": "SAP HANA",
                "tdsql": "TDSQL-C"
            }.get(db_type_lower, db_type.upper())

            short = f"{db_display_name} {version_num}"

            # 提取详细信息（版本号之后的部分）
            details = full_version[match.end():].strip()
            if details.startswith("on") or details.startswith(","):
                details = details.lstrip(",").strip()

            return {
                "short": short,
                "full": full_version,
                "details": details
            }

    # 兜底：截断到50字符
    if len(full_version) > 50:
        return {
            "short": full_version[:50] + "...",
            "full": full_version,
            "details": full_version[50:]
        }

    return {
        "short": full_version,
        "full": full_version,
        "details": ""
    }
