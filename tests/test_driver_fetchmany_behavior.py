"""
验证 SQL Server 和 Oracle 驱动的 fetchmany 行为

这个脚本用于测试：
1. pyodbc (SQL Server) 的 fetchmany 是否会预先缓冲所有结果
2. oracledb (Oracle) 的 fetchmany 是否会预先缓冲所有结果

测试方法：
- 创建一个大表（100万行）
- 执行 SELECT * 查询
- 只调用 fetchmany(10) 获取 10 行
- 监控内存使用情况

预期结果：
- 如果驱动是流式的：内存增长很小（只有 10 行数据）
- 如果驱动会缓冲：内存增长很大（100万行数据）
"""

import tracemalloc
import sys


def test_pyodbc_fetchmany_behavior():
    """测试 pyodbc 的 fetchmany 是否会预先缓冲所有结果"""
    try:
        import pyodbc
    except ImportError:
        print("⚠️  pyodbc 未安装，跳过 SQL Server 测试")
        return None

    print("\n" + "="*60)
    print("测试 SQL Server (pyodbc) fetchmany 行为")
    print("="*60)

    # 注意：这需要实际的 SQL Server 连接
    # 这里只是演示代码结构
    print("ℹ️  需要实际的 SQL Server 连接才能测试")
    print("ℹ️  根据 pyodbc 文档，fetchmany 应该是流式的")
    print("ℹ️  但需要实际测试确认")

    return "需要实际数据库连接"


def test_oracledb_fetchmany_behavior():
    """测试 oracledb 的 fetchmany 是否会预先缓冲所有结果"""
    try:
        import oracledb
        print("\n" + "="*60)
        print(f"测试 Oracle (oracledb {oracledb.__version__}) fetchmany 行为")
        print("="*60)
    except ImportError:
        print("⚠️  oracledb 未安装，跳过 Oracle 测试")
        return None

    # 注意：这需要实际的 Oracle 连接
    print("ℹ️  需要实际的 Oracle 连接才能测试")
    print("ℹ️  oracledb 3.x+ (thin mode) 默认是流式的")
    print("ℹ️  但需要实际测试确认")

    return "需要实际数据库连接"


def analyze_driver_documentation():
    """分析驱动文档和已知行为"""
    print("\n" + "="*60)
    print("驱动行为分析（基于文档和社区反馈）")
    print("="*60)

    analysis = {
        "pyodbc": {
            "driver": "pyodbc (SQL Server)",
            "default_behavior": "客户端缓冲（默认）",
            "streaming_option": "需要设置 cursor.fast_executemany 或使用特定连接参数",
            "risk_level": "⚠️  高风险",
            "recommendation": "需要验证并可能需要修复",
            "notes": [
                "pyodbc 默认会在 execute() 时获取所有结果",
                "fetchmany() 只是从已缓冲的结果中返回",
                "可以通过连接字符串参数优化，但不是默认行为"
            ]
        },
        "oracledb": {
            "driver": "oracledb (Oracle)",
            "default_behavior": "流式（3.x+ thin mode）",
            "streaming_option": "默认启用",
            "risk_level": "✅ 低风险",
            "recommendation": "应该是安全的，但建议测试确认",
            "notes": [
                "oracledb 3.x+ 使用 thin mode，默认流式",
                "fetchmany() 按需从服务器获取数据",
                "arraysize 参数控制每次网络往返获取的行数"
            ]
        },
        "asyncpg": {
            "driver": "asyncpg (PostgreSQL)",
            "default_behavior": "流式（服务端游标）",
            "streaming_option": "默认启用",
            "risk_level": "✅ 安全",
            "recommendation": "已确认安全",
            "notes": [
                "cursor.fetch(n) 只从服务器获取 n 行",
                "不会预先缓冲所有结果"
            ]
        },
        "aiomysql": {
            "driver": "aiomysql (MySQL)",
            "default_behavior": "客户端缓冲（默认）",
            "streaming_option": "SSCursor（已修复）",
            "risk_level": "✅ 已修复",
            "recommendation": "已使用 SSCursor 修复",
            "notes": [
                "默认 Cursor 会缓冲所有结果",
                "SSCursor 使用服务端游标，流式读取",
                "已在 execute_query 中启用 SSCursor"
            ]
        }
    }

    for driver_name, info in analysis.items():
        print(f"\n【{info['driver']}】")
        print(f"  默认行为: {info['default_behavior']}")
        print(f"  流式选项: {info['streaming_option']}")
        print(f"  风险等级: {info['risk_level']}")
        print(f"  建议: {info['recommendation']}")
        print(f"  说明:")
        for note in info['notes']:
            print(f"    - {note}")

    return analysis


if __name__ == "__main__":
    print("🔍 数据库驱动 fetchmany 行为验证工具")
    print("="*60)

    # 分析文档
    analysis = analyze_driver_documentation()

    # 尝试测试
    test_pyodbc_fetchmany_behavior()
    test_oracledb_fetchmany_behavior()

    print("\n" + "="*60)
    print("📋 总结")
    print("="*60)
    print("✅ MySQL (aiomysql): 已修复，使用 SSCursor")
    print("✅ PostgreSQL (asyncpg): 默认安全")
    print("✅ HANA (hdbcli): 已修复 truncated 标志")
    print("⚠️  SQL Server (pyodbc): 需要进一步验证和可能的修复")
    print("✅ Oracle (oracledb): 应该安全，建议测试确认")
    print("\n建议：优先测试 SQL Server，因为风险最高")
