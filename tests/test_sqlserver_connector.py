from backend.services.sqlserver_service import SQLServerConnector


def test_sqlserver_conn_string_respects_extra_params():
    connector = SQLServerConnector(
        host="127.0.0.1",
        port=1433,
        username="sa",
        password="secret",
        database="master",
        encrypt=False,
        trust_server_certificate=False,
        odbc_driver="ODBC Driver 17 for SQL Server",
        connection_timeout=9,
    )

    conn_string = connector._get_conn_string()

    assert "DRIVER={ODBC Driver 17 for SQL Server}" in conn_string
    assert "Encrypt=no" in conn_string
    assert "TrustServerCertificate=no" in conn_string
    assert "Connection Timeout=9" in conn_string


def test_sqlserver_defaults_are_backward_compatible():
    connector = SQLServerConnector(
        host="127.0.0.1",
        port=1433,
        username="sa",
        password="secret",
        database="master",
    )

    conn_string = connector._get_conn_string()

    assert "Encrypt=no" in conn_string
    assert connector._resolve_driver_name(pyodbc_module=type("MockPyodbc", (), {"drivers": staticmethod(lambda: ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"])})()) == "ODBC Driver 17 for SQL Server"


def test_sqlserver_ssl_protocol_error_message_is_actionable():
    message = SQLServerConnector._build_ssl_protocol_error_message(
        "('08001', '[Microsoft][ODBC Driver 18 for SQL Server]SSL Provider: unsupported protocol')",
        "ODBC Driver 18 for SQL Server",
    )

    assert "Encrypt=no" in message
    assert "ODBC Driver 17" in message
    assert "TLS 1.2" in message
