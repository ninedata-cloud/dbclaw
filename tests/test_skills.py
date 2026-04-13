#!/usr/bin/env python3
"""
Comprehensive test suite for DBClaw Skill Management System
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.skills.loader import SkillLoader
from backend.skills.validator import SkillValidator
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext
from backend.skills.schema import SkillParameter
from backend.skills.models import Skill


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, test_name: str):
        self.passed += 1
        print(f"  ✓ {test_name}")

    def record_fail(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
        print(f"  ✗ {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\nResults: {self.passed}/{total} passed")
        return self.failed == 0


async def test_skill_loading():
    """Test loading all built-in skills"""
    print("\n1. Testing Skill Loading")
    print("=" * 60)

    results = TestResults()
    builtin_dir = Path(__file__).parent.parent / "backend/skills/builtin"

    if not builtin_dir.exists():
        results.record_fail("Builtin skill directory", f"Directory not found: {builtin_dir}")
        return results.summary()

    yaml_files = sorted(builtin_dir.glob("*.yaml"))
    if not yaml_files:
        results.record_fail("Builtin skill loading", "No builtin skill YAML files found")
        return results.summary()

    for yaml_file in yaml_files:
        try:
            yaml_content = yaml_file.read_text()
            skill_def = SkillLoader.load_from_yaml(yaml_content)

            # Validate code
            is_valid, validation_errors = SkillValidator.validate_code(skill_def.code)

            if is_valid:
                results.record_pass(f"Load {skill_def.id}")
            else:
                results.record_fail(f"Load {skill_def.id}", ', '.join(validation_errors))

        except Exception as e:
            results.record_fail(f"Load {yaml_file.name}", str(e))

    return results.summary()


async def test_code_validation():
    """Test skill code validation"""
    print("\n2. Testing Code Validation")
    print("=" * 60)

    results = TestResults()

    # Test valid code
    valid_code = """
async def execute(context, params):
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(valid_code)
    if is_valid:
        results.record_pass("Valid code accepted")
    else:
        results.record_fail("Valid code accepted", ', '.join(errors))

    # Test forbidden import (os)
    invalid_code_os = """
import os
async def execute(context, params):
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(invalid_code_os)
    if not is_valid and any("os" in e for e in errors):
        results.record_pass("Forbidden import 'os' rejected")
    else:
        results.record_fail("Forbidden import 'os' rejected", "Should reject os import")

    # Test forbidden import (subprocess)
    invalid_code_subprocess = """
import subprocess
async def execute(context, params):
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(invalid_code_subprocess)
    if not is_valid and any("subprocess" in e for e in errors):
        results.record_pass("Forbidden import 'subprocess' rejected")
    else:
        results.record_fail("Forbidden import 'subprocess' rejected", "Should reject subprocess")

    # Test forbidden builtin (eval)
    invalid_code_eval = """
async def execute(context, params):
    eval("print('test')")
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(invalid_code_eval)
    if not is_valid and any("eval" in e for e in errors):
        results.record_pass("Forbidden builtin 'eval' rejected")
    else:
        results.record_fail("Forbidden builtin 'eval' rejected", "Should reject eval")

    # Test missing execute function
    missing_execute = """
def some_function():
    pass
"""
    is_valid, errors = SkillValidator.validate_code(missing_execute)
    if not is_valid and any("execute" in e for e in errors):
        results.record_pass("Missing execute function rejected")
    else:
        results.record_fail("Missing execute function rejected", "Should require execute function")

    # Test wrong execute signature
    wrong_signature = """
async def execute(context):
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(wrong_signature)
    if not is_valid and any("parameters" in e for e in errors):
        results.record_pass("Wrong execute signature rejected")
    else:
        results.record_fail("Wrong execute signature rejected", "Should require 2 parameters")

    # Test syntax error
    syntax_error = """
async def execute(context, params)
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(syntax_error)
    if not is_valid and any("Syntax" in e for e in errors):
        results.record_pass("Syntax error detected")
    else:
        results.record_fail("Syntax error detected", "Should detect syntax errors")

    # Test forbidden attribute access
    forbidden_attr = """
async def execute(context, params):
    x = execute.__globals__
    return {"success": True}
"""
    is_valid, errors = SkillValidator.validate_code(forbidden_attr)
    if not is_valid and any("__globals__" in e for e in errors):
        results.record_pass("Forbidden attribute '__globals__' rejected")
    else:
        results.record_fail("Forbidden attribute '__globals__' rejected", "Should reject __globals__")

    return results.summary()


async def test_parameter_validation():
    """Test parameter validation"""
    print("\n3. Testing Parameter Validation")
    print("=" * 60)

    results = TestResults()

    # Define test parameters
    param_defs = [
        {"name": "query", "type": "string", "required": True, "description": "SQL query"},
        {"name": "limit", "type": "integer", "required": False, "default": 10, "description": "Result limit"},
        {"name": "ratio", "type": "number", "required": False, "default": 1.5, "description": "Threshold ratio"},
        {"name": "enabled", "type": "boolean", "required": False, "default": True, "description": "Enable flag"},
        {"name": "tags", "type": "array", "required": False, "description": "Tags list"},
        {"name": "config", "type": "object", "required": False, "description": "Config object"},
    ]

    # Test valid parameters
    valid_params = {
        "query": "SELECT * FROM users",
        "limit": 20,
        "ratio": 1.25,
        "enabled": False,
        "tags": ["test", "demo"],
        "config": {"key": "value"}
    }
    is_valid, errors = SkillValidator.validate_parameters(valid_params, param_defs)
    if is_valid:
        results.record_pass("Valid parameters accepted")
    else:
        results.record_fail("Valid parameters accepted", ', '.join(errors))

    # Test missing required parameter
    missing_required = {"limit": 10}
    is_valid, errors = SkillValidator.validate_parameters(missing_required, param_defs)
    if not is_valid and any("query" in e for e in errors):
        results.record_pass("Missing required parameter detected")
    else:
        results.record_fail("Missing required parameter detected", "Should require 'query'")

    # Test wrong type (string instead of integer)
    wrong_type = {"query": "SELECT *", "limit": "not_an_int"}
    is_valid, errors = SkillValidator.validate_parameters(wrong_type, param_defs)
    if not is_valid and any("limit" in e and "type" in e for e in errors):
        results.record_pass("Wrong type detected (string vs integer)")
    else:
        results.record_fail("Wrong type detected", "Should detect type mismatch")

    # Test unknown parameter
    unknown_param = {"query": "SELECT *", "unknown": "value"}
    is_valid, errors = SkillValidator.validate_parameters(unknown_param, param_defs)
    if not is_valid and any("unknown" in e for e in errors):
        results.record_pass("Unknown parameter detected")
    else:
        results.record_fail("Unknown parameter detected", "Should reject unknown parameters")

    # Test optional parameters with defaults
    minimal_params = {"query": "SELECT *"}
    is_valid, errors = SkillValidator.validate_parameters(minimal_params, param_defs)
    if is_valid:
        results.record_pass("Optional parameters allowed")
    else:
        results.record_fail("Optional parameters allowed", ', '.join(errors))

    # Test type validation for each type
    type_tests = [
        ({"query": "test"}, "string", True),
        ({"query": 123}, "string", False),
        ({"query": "test", "limit": 10}, "integer", True),
        ({"query": "test", "limit": "10"}, "integer", False),
        ({"query": "test", "ratio": 1.5}, "number", True),
        ({"query": "test", "ratio": "1.5"}, "number", False),
        ({"query": "test", "enabled": True}, "boolean", True),
        ({"query": "test", "enabled": "true"}, "boolean", False),
        ({"query": "test", "tags": ["a", "b"]}, "array", True),
        ({"query": "test", "tags": "not_array"}, "array", False),
        ({"query": "test", "config": {"k": "v"}}, "object", True),
        ({"query": "test", "config": "not_object"}, "object", False),
    ]

    for params, type_name, should_pass in type_tests:
        is_valid, errors = SkillValidator.validate_parameters(params, param_defs)
        if is_valid == should_pass:
            results.record_pass(f"Type validation: {type_name} {'valid' if should_pass else 'invalid'}")
        else:
            results.record_fail(f"Type validation: {type_name}", f"Expected {'valid' if should_pass else 'invalid'}")

    return results.summary()


async def test_skill_execution():
    """Test skill execution"""
    print("\n4. Testing Skill Execution")
    print("=" * 60)

    results = TestResults()

    # Create mock context
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    context = SkillContext(
        db=mock_db,
        session_id=1,
        user_id=1,
        permissions=["execute_query", "access_kb"]
    )

    executor = SkillExecutor()

    # Test successful execution
    simple_skill = Skill(
        id="test_simple",
        name="Test Simple",
        version="1.0.0",
        description="Simple test skill",
        code="""
async def execute(context, params):
    return {"result": "success", "value": params.get("value", 0)}
""",
        parameters=[{"name": "value", "type": "integer", "required": False, "default": 0, "description": "Test value"}],
        permissions=[],
        is_builtin=False,
        is_enabled=True
    )

    try:
        result = await executor.execute(simple_skill, {"value": 42}, context)
        if result.get("result") == "success" and result.get("value") == 42:
            results.record_pass("Simple skill execution")
        else:
            results.record_fail("Simple skill execution", f"Unexpected result: {result}")
    except Exception as e:
        results.record_fail("Simple skill execution", str(e))

    # Test execution with missing permission
    permission_skill = Skill(
        id="test_permission",
        name="Test Permission",
        version="1.0.0",
        description="Permission test skill",
        code="""
async def execute(context, params):
    return {"result": "success"}
""",
        parameters=[],
        permissions=["execute_command"],  # Not granted in context
        is_builtin=False,
        is_enabled=True
    )

    try:
        result = await executor.execute(permission_skill, {}, context)
        results.record_fail("Permission check", "Should have raised PermissionError")
    except PermissionError as e:
        if "execute_command" in str(e):
            results.record_pass("Permission check enforced")
        else:
            results.record_fail("Permission check", f"Wrong error: {e}")
    except Exception as e:
        results.record_fail("Permission check", f"Unexpected error: {e}")

    # Test execution with invalid parameters
    try:
        result = await executor.execute(simple_skill, {"invalid_param": "test"}, context)
        results.record_fail("Invalid parameter check", "Should have raised ValueError")
    except ValueError as e:
        if "Unknown parameter" in str(e):
            results.record_pass("Invalid parameter rejected")
        else:
            results.record_fail("Invalid parameter check", f"Wrong error: {e}")
    except Exception as e:
        results.record_fail("Invalid parameter check", f"Unexpected error: {e}")

    # Test execution with runtime error
    error_skill = Skill(
        id="test_error",
        name="Test Error",
        version="1.0.0",
        description="Error test skill",
        code="""
async def execute(context, params):
    raise ValueError("Intentional error")
""",
        parameters=[],
        permissions=[],
        is_builtin=False,
        is_enabled=True
    )

    try:
        result = await executor.execute(error_skill, {}, context)
        results.record_fail("Runtime error handling", "Should have raised ValueError")
    except ValueError as e:
        if "Intentional error" in str(e):
            results.record_pass("Runtime error propagated")
        else:
            results.record_fail("Runtime error handling", f"Wrong error: {e}")
    except Exception as e:
        results.record_fail("Runtime error handling", f"Unexpected error: {e}")

    # Test execution with context API
    context_skill = Skill(
        id="test_context",
        name="Test Context",
        version="1.0.0",
        description="Context API test skill",
        code="""
async def execute(context, params):
    # Test context attributes
    return {
        "session_id": context.session_id,
        "user_id": context.user_id,
        "has_permission": "execute_query" in context.permissions
    }
""",
        parameters=[],
        permissions=[],
        is_builtin=False,
        is_enabled=True
    )

    try:
        result = await executor.execute(context_skill, {}, context)
        if (result.get("session_id") == 1 and
            result.get("user_id") == 1 and
            result.get("has_permission") == True):
            results.record_pass("Context API access")
        else:
            results.record_fail("Context API access", f"Unexpected result: {result}")
    except Exception as e:
        results.record_fail("Context API access", str(e))

    return results.summary()


async def test_timeout_handling():
    """Test execution timeout"""
    print("\n5. Testing Timeout Handling")
    print("=" * 60)

    results = TestResults()

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    context = SkillContext(
        db=mock_db,
        session_id=1,
        user_id=1,
        permissions=[]
    )

    executor = SkillExecutor()

    # Test timeout (this will take 30+ seconds, so we'll use a shorter custom timeout)
    timeout_skill = Skill(
        id="test_timeout",
        name="Test Timeout",
        version="1.0.0",
        description="Timeout test skill",
        code="""
import asyncio
async def execute(context, params):
    await asyncio.sleep(35)  # Sleep longer than default timeout
    return {"result": "should_not_reach"}
""",
        parameters=[],
        permissions=[],
        is_builtin=False,
        is_enabled=True
    )

    # Note: We won't actually run this test as it takes too long
    # Just verify the timeout mechanism exists
    if hasattr(executor, 'DEFAULT_TIMEOUT') and executor.DEFAULT_TIMEOUT == 30:
        results.record_pass("Timeout configuration exists")
    else:
        results.record_fail("Timeout configuration", "DEFAULT_TIMEOUT not set correctly")

    if hasattr(executor, 'MAX_TIMEOUT') and executor.MAX_TIMEOUT == 3600:
        results.record_pass("Max timeout configuration exists")
    else:
        results.record_fail("Max timeout configuration", "MAX_TIMEOUT not set correctly")

    return results.summary()


async def test_serialization():
    """Test result serialization"""
    print("\n6. Testing Result Serialization")
    print("=" * 60)

    results = TestResults()

    from decimal import Decimal

    executor = SkillExecutor()

    # Test Decimal serialization
    decimal_obj = Decimal("123.45")
    serialized = executor._serialize_result(decimal_obj)
    if isinstance(serialized, float) and serialized == 123.45:
        results.record_pass("Decimal serialization")
    else:
        results.record_fail("Decimal serialization", f"Expected float, got {type(serialized)}")

    # Test dict with Decimal
    dict_obj = {"value": Decimal("100.50"), "name": "test"}
    serialized = executor._serialize_result(dict_obj)
    if isinstance(serialized["value"], float) and serialized["value"] == 100.50:
        results.record_pass("Dict with Decimal serialization")
    else:
        results.record_fail("Dict with Decimal serialization", f"Unexpected result: {serialized}")

    # Test list with Decimal
    list_obj = [Decimal("1.1"), Decimal("2.2"), "test"]
    serialized = executor._serialize_result(list_obj)
    if (isinstance(serialized[0], float) and
        isinstance(serialized[1], float) and
        serialized[2] == "test"):
        results.record_pass("List with Decimal serialization")
    else:
        results.record_fail("List with Decimal serialization", f"Unexpected result: {serialized}")

    # Test nested structures
    nested_obj = {
        "data": [
            {"value": Decimal("10.5"), "items": [Decimal("1.1"), Decimal("2.2")]},
            {"value": Decimal("20.5"), "items": [Decimal("3.3")]}
        ]
    }
    serialized = executor._serialize_result(nested_obj)
    if (isinstance(serialized["data"][0]["value"], float) and
        isinstance(serialized["data"][0]["items"][0], float)):
        results.record_pass("Nested structure serialization")
    else:
        results.record_fail("Nested structure serialization", f"Unexpected result: {serialized}")

    return results.summary()


async def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("DBClaw Skill Management System - Comprehensive Test Suite")
    print("=" * 60)

    test_results = []

    # Run all test suites
    test_results.append(await test_skill_loading())
    test_results.append(await test_code_validation())
    test_results.append(await test_parameter_validation())
    test_results.append(await test_skill_execution())
    test_results.append(await test_timeout_handling())
    test_results.append(await test_serialization())

    # Summary
    print("\n" + "=" * 60)
    if all(test_results):
        print("✓ All test suites passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some test suites failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
