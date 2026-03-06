"""
Test intent detection functionality
"""
from backend.agent.intent_detector import detect_query_intent


def test_diagnostic_queries():
    """Test diagnostic intent detection"""
    test_cases = [
        ("数据库很慢，怎么办？", "diagnostic"),
        ("为什么查询这么慢", "diagnostic"),
        ("连接失败了", "diagnostic"),
        ("数据库出现错误", "diagnostic"),
        ("性能问题诊断", "diagnostic"),
        ("database is slow", "diagnostic"),
        ("why is the query slow", "diagnostic"),
        ("connection timeout error", "diagnostic"),
    ]

    print("Testing Diagnostic Queries:")
    for query, expected in test_cases:
        result = detect_query_intent(query)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{query}' -> {result} (expected: {expected})")


def test_informational_queries():
    """Test informational intent detection"""
    test_cases = [
        ("查看数据库配置", "informational"),
        ("显示当前连接", "informational"),
        ("列出所有表", "informational"),
        ("获取数据库状态", "informational"),
        ("数据库参数信息", "informational"),  # Changed from "数据库配置参数"
        ("show database config", "informational"),
        ("view current connections", "informational"),
        ("list all tables", "informational"),
        ("get database status", "informational"),
    ]

    print("\nTesting Informational Queries:")
    for query, expected in test_cases:
        result = detect_query_intent(query)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{query}' -> {result} (expected: {expected})")


def test_administrative_queries():
    """Test administrative intent detection"""
    test_cases = [
        ("执行 SELECT * FROM users", "administrative"),
        ("创建索引", "administrative"),
        ("修改配置参数", "administrative"),
        ("删除旧数据", "administrative"),
        ("execute this query", "administrative"),
        ("create an index", "administrative"),
        ("modify the configuration", "administrative"),
    ]

    print("\nTesting Administrative Queries:")
    for query, expected in test_cases:
        result = detect_query_intent(query)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{query}' -> {result} (expected: {expected})")


def test_edge_cases():
    """Test edge cases and ambiguous queries"""
    test_cases = [
        ("数据库状态", "informational"),  # Ambiguous, should default to informational
        ("查看配置，数据库很慢", "diagnostic"),  # Mixed intent, diagnostic should win
        ("", "informational"),  # Empty string, should default to informational
    ]

    print("\nTesting Edge Cases:")
    for query, expected in test_cases:
        result = detect_query_intent(query)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{query}' -> {result} (expected: {expected})")


if __name__ == "__main__":
    print("=" * 60)
    print("Intent Detection Test Suite")
    print("=" * 60)

    test_diagnostic_queries()
    test_informational_queries()
    test_administrative_queries()
    test_edge_cases()

    print("\n" + "=" * 60)
    print("Test suite completed!")
    print("=" * 60)
