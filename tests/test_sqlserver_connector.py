from backend.services.sqlserver_service import SQLServerConnector


def test_sqlserver_conn_string_defaults():
    """测试默认连接字符串包含 SQL Server 2012 兼容参数"""
    connector = SQLServerConnector(
        host="127.0.0.1",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    conn_string = connector._get_conn_string()

    assert "DRIVER={ODBC Driver 18 for SQL Server}" in conn_string
    assert "TrustServerCertificate=yes" in conn_string
    assert "Encrypt=no" in conn_string
    assert "Connection Timeout=5" in conn_string


def test_sqlserver_custom_timeout():
    """测试自定义连接超时"""
    connector = SQLServerConnector(
        host="127.0.0.1",
        port=1433,
        username="sa",
        password="secret",
        database="master",
        connection_timeout=10,
    )

    conn_string = connector._get_conn_string()
    assert "Connection Timeout=10" in conn_string

