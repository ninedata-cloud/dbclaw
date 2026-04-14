"""Test script to verify uptime fields in all database services"""
import asyncio
from backend.services.mysql_service import MySQLConnector
from backend.services.postgres_service import PostgreSQLConnector
from backend.services.oracle_service import OracleConnector
from backend.services.sqlserver_service import SQLServerConnector
from backend.services.opengauss_service import OpenGaussConnector


async def test_service_uptime_fields():
    """Test that all database services return uptime-related fields"""
    
    services = {
        'MySQL': MySQLConnector,
        'PostgreSQL': PostgreSQLConnector,
        'Oracle': OracleConnector,
        'SQL Server': SQLServerConnector,
        'openGauss': OpenGaussConnector,
    }
    
    print("Checking uptime field support in database services:\n")
    print(f"{'Database':<15} {'Has uptime':<12} {'Has boot_time':<15} {'Has uptime_in_seconds':<20}")
    print("-" * 70)
    
    for name, service_class in services.items():
        # Create a dummy instance to check the get_status method
        try:
            import inspect
            source = inspect.getsource(service_class.get_status)
            
            has_uptime = '"uptime"' in source or "'uptime'" in source
            has_boot_time = '"boot_time"' in source or "'boot_time'" in source
            has_uptime_in_seconds = '"uptime_in_seconds"' in source or "'uptime_in_seconds'" in source
            
            status = "✓" if (has_uptime or has_uptime_in_seconds) else "✗"
            print(f"{name:<15} {str(has_uptime):<12} {str(has_boot_time):<15} {str(has_uptime_in_seconds):<20} {status}")
        except Exception as e:
            print(f"{name:<15} Error: {e}")
    
    print("\n✓ = Service returns uptime field")
    print("✗ = Service missing uptime field")


if __name__ == "__main__":
    asyncio.run(test_service_uptime_fields())
