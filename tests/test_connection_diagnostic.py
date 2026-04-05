#!/usr/bin/env python3
"""Connection diagnostic tests."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.connection_diagnostic_service import ConnectionDiagnosticService


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def record_pass(self, name: str):
        self.passed += 1
        print(f"  ✓ {name}")

    def record_fail(self, name: str, error: str):
        self.failed += 1
        print(f"  ✗ {name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\nResults: {self.passed}/{total} passed")
        return self.failed == 0


async def test_classification_rules():
    print("\n1. Testing diagnostic classification")
    print("=" * 60)
    results = TestResults()
    service = ConnectionDiagnosticService(MagicMock())

    cases = [
        ("Connection refused", "port_unreachable"),
        ("password authentication failed for user postgres", "authentication_failed"),
        ("Unknown database 'demo'", "database_not_found"),
        ("ORA-01034: ORACLE not available", "database_not_open"),
        ("SSL handshake failed", "ssl_handshake_failed"),
        ("random unexpected failure", "unknown_error"),
    ]

    for message, expected in cases:
        classification = service._classify_exception_message(message)
        if classification["category"] == expected:
            results.record_pass(f"{message} -> {expected}")
        else:
            results.record_fail(f"{message} -> {expected}", f"got {classification['category']}")

    return results.summary()


async def test_tcp_failure_short_circuit():
    print("\n2. Testing TCP failure diagnostics")
    print("=" * 60)
    results = TestResults()
    service = ConnectionDiagnosticService(MagicMock())

    with patch.object(service, "_run_tcp_check", new=AsyncMock(return_value={
        "layer": "tcp",
        "name": "tcp_connect",
        "success": False,
        "error": "Connection refused",
        "latency_ms": 1.2,
        "details": None,
        "skipped": False,
        "reason": None,
    })):
        diagnosis = await service.diagnose_connection_params(
            db_type="postgresql",
            host="127.0.0.1",
            port=5432,
            include_host_checks=False,
            include_tcp_checks=True,
        )

    if not diagnosis["success"] and diagnosis["classification"]["category"] == "port_unreachable":
        results.record_pass("TCP failure categorized as port_unreachable")
    else:
        results.record_fail("TCP failure categorized as port_unreachable", str(diagnosis))

    return results.summary()


async def test_successful_connection():
    print("\n3. Testing successful connection result")
    print("=" * 60)
    results = TestResults()
    service = ConnectionDiagnosticService(MagicMock())
    fake_connector = AsyncMock()
    fake_connector.test_connection = AsyncMock(return_value="PostgreSQL 16")

    with patch.object(service, "_run_tcp_check", new=AsyncMock(return_value={
        "layer": "tcp",
        "name": "tcp_connect",
        "success": True,
        "details": "TCP 端口可达",
        "error": None,
        "latency_ms": 1.0,
        "skipped": False,
        "reason": None,
    })):
        with patch("backend.services.connection_diagnostic_service.get_connector", return_value=fake_connector):
            diagnosis = await service.diagnose_connection_params(
                db_type="postgresql",
                host="127.0.0.1",
                port=5432,
                include_host_checks=False,
                include_tcp_checks=True,
            )

    if diagnosis["success"] and diagnosis.get("version") == "PostgreSQL 16":
        results.record_pass("Successful connection returns version")
    else:
        results.record_fail("Successful connection returns version", str(diagnosis))

    return results.summary()


async def main():
    print("Testing connection diagnostic service")
    print("=" * 60)

    test_functions = [
        test_classification_rules,
        test_tcp_failure_short_circuit,
        test_successful_connection,
    ]

    passed = 0
    failed = 0
    for test_func in test_functions:
        try:
            if await test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ {test_func.__name__} crashed: {e}")

    print("\n" + "=" * 60)
    print(f"Overall: {passed}/{passed + failed} test groups passed")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
