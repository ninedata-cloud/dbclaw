"""Test inspection endpoints including expression validation"""
import asyncio
from sqlalchemy import select
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.inspection_config import InspectionConfig


async def test_validation_endpoint():
    """Test expression validation endpoint"""
    print("\n=== Testing Expression Validation Endpoint ===\n")
    
    # Import here to avoid circular imports
    from backend.routers.inspections import validate_threshold_expression, ExpressionValidationRequest
    
    # Test valid expressions
    valid_expressions = [
        "cpu_usage > 50",
        "cpu_usage > 50 and connections > 20",
        "cpu_usage > 80 or disk_usage > 90",
        "(cpu_usage > 50 and memory_usage > 70) or connections > 100",
        "qps > 1000 and tps > 500"
    ]
    
    print("Testing valid expressions:")
    for expr in valid_expressions:
        request = ExpressionValidationRequest(expression=expr)
        result = await validate_threshold_expression(request)
        assert result.valid is True, f"Expression should be valid: {expr}"
        print(f"  ✓ {expr}")
    
    # Test invalid expressions
    invalid_expressions = [
        "cpu_usage > 50 and",  # Syntax error
        "cpu_usage >",  # Incomplete
        "import os",  # Not an expression
        "def foo(): pass",  # Statement, not expression
        "cpu_usage > 50; print('hello')"  # Multiple statements
    ]
    
    print("\nTesting invalid expressions:")
    for expr in invalid_expressions:
        request = ExpressionValidationRequest(expression=expr)
        result = await validate_threshold_expression(request)
        assert result.valid is False, f"Expression should be invalid: {expr}"
        print(f"  ✓ {expr} -> {result.error}")
    
    print("\n✓ Expression validation endpoint works correctly\n")


async def test_config_with_thresholds():
    """Test creating/updating inspection config with threshold rules"""
    print("\n=== Testing Inspection Config with Thresholds ===\n")
    
    async with async_session() as db:
        # Get first datasource
        result = await db.execute(select(Datasource).limit(1))
        datasource = result.scalar_one_or_none()
        
        if not datasource:
            print("No datasource found. Please create a datasource first.")
            return
        
        print(f"Using datasource: {datasource.name} (ID: {datasource.id})")
        
        # Test 1: Create config with preset thresholds
        print("\nTest 1: Creating config with preset thresholds")
        config = InspectionConfig(
            datasource_id=datasource.id,
            enabled=True,
            schedule_interval=86400,
            use_ai_analysis=True,
            threshold_rules={
                "cpu_usage": {"threshold": 50, "duration": 60},
                "disk_usage": {"threshold": 80, "duration": 300},
                "connections": {"threshold": 20, "duration": 120}
            }
        )
        
        # Check if config exists
        existing = await db.execute(
            select(InspectionConfig).where(InspectionConfig.datasource_id == datasource.id)
        )
        existing_config = existing.scalar_one_or_none()
        
        if existing_config:
            # Update existing
            existing_config.threshold_rules = config.threshold_rules
            existing_config.enabled = config.enabled
            await db.commit()
            await db.refresh(existing_config)
            config = existing_config
            print("  ✓ Updated existing config")
        else:
            # Create new
            db.add(config)
            await db.commit()
            await db.refresh(config)
            print("  ✓ Created new config")
        
        assert "cpu_usage" in config.threshold_rules
        assert config.threshold_rules["cpu_usage"]["threshold"] == 50
        assert config.threshold_rules["disk_usage"]["threshold"] == 80
        assert config.threshold_rules["connections"]["threshold"] == 20
        print("  ✓ Preset thresholds saved correctly")
        
        # Test 2: Update config with custom expression
        print("\nTest 2: Updating config with custom expression")
        config.threshold_rules = {
            "custom_expression": {
                "expression": "cpu_usage > 50 and connections > 20",
                "duration": 60
            }
        }
        await db.commit()
        await db.refresh(config)
        
        assert "custom_expression" in config.threshold_rules
        assert config.threshold_rules["custom_expression"]["expression"] == "cpu_usage > 50 and connections > 20"
        assert config.threshold_rules["custom_expression"]["duration"] == 60
        print("  ✓ Custom expression saved correctly")
        
        # Test 3: Update back to preset thresholds
        print("\nTest 3: Updating back to preset thresholds")
        config.threshold_rules = {
            "cpu_usage": {"threshold": 70, "duration": 120}
        }
        await db.commit()
        await db.refresh(config)
        
        assert "cpu_usage" in config.threshold_rules
        assert "custom_expression" not in config.threshold_rules
        assert config.threshold_rules["cpu_usage"]["threshold"] == 70
        print("  ✓ Switched back to preset thresholds")
        
        # Test 4: Empty threshold rules
        print("\nTest 4: Empty threshold rules")
        config.threshold_rules = {}
        await db.commit()
        await db.refresh(config)
        
        assert config.threshold_rules == {}
        print("  ✓ Empty threshold rules handled correctly")
        
        print("\n✓ Inspection config with thresholds works correctly\n")


async def run_all_tests():
    """Run all endpoint tests"""
    print("\n" + "="*60)
    print("Running Inspection Endpoint Tests")
    print("="*60)
    
    await test_validation_endpoint()
    await test_config_with_thresholds()
    
    print("="*60)
    print("All Tests Passed ✓")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
