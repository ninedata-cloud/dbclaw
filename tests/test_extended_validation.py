#!/usr/bin/env python3
"""
Test extended parameter validation features
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.skills.validator import SkillValidator


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


async def test_range_validation():
    """Test min/max range validation"""
    print("\n1. Testing Range Validation")
    print("=" * 60)

    results = TestResults()

    # Define parameter with range
    param_defs = [
        {
            "name": "limit",
            "type": "integer",
            "required": True,
            "description": "Result limit",
            "min": 1,
            "max": 100
        }
    ]

    # Test valid value within range
    is_valid, errors = SkillValidator.validate_parameters({"limit": 50}, param_defs)
    if is_valid:
        results.record_pass("Value within range accepted")
    else:
        results.record_fail("Value within range accepted", ', '.join(errors))

    # Test value at minimum
    is_valid, errors = SkillValidator.validate_parameters({"limit": 1}, param_defs)
    if is_valid:
        results.record_pass("Value at minimum accepted")
    else:
        results.record_fail("Value at minimum accepted", ', '.join(errors))

    # Test value at maximum
    is_valid, errors = SkillValidator.validate_parameters({"limit": 100}, param_defs)
    if is_valid:
        results.record_pass("Value at maximum accepted")
    else:
        results.record_fail("Value at maximum accepted", ', '.join(errors))

    # Test value below minimum
    is_valid, errors = SkillValidator.validate_parameters({"limit": 0}, param_defs)
    if not is_valid and any("below minimum" in e for e in errors):
        results.record_pass("Value below minimum rejected")
    else:
        results.record_fail("Value below minimum rejected", "Should reject value < min")

    # Test value above maximum
    is_valid, errors = SkillValidator.validate_parameters({"limit": 101}, param_defs)
    if not is_valid and any("exceeds maximum" in e for e in errors):
        results.record_pass("Value above maximum rejected")
    else:
        results.record_fail("Value above maximum rejected", "Should reject value > max")

    return results.summary()


async def test_pattern_validation():
    """Test regex pattern validation"""
    print("\n2. Testing Pattern Validation")
    print("=" * 60)

    results = TestResults()

    # Define parameter with pattern
    param_defs = [
        {
            "name": "email",
            "type": "string",
            "required": True,
            "description": "Email address",
            "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        }
    ]

    # Test valid email
    is_valid, errors = SkillValidator.validate_parameters(
        {"email": "user@example.com"}, param_defs
    )
    if is_valid:
        results.record_pass("Valid email pattern accepted")
    else:
        results.record_fail("Valid email pattern accepted", ', '.join(errors))

    # Test invalid email (missing @)
    is_valid, errors = SkillValidator.validate_parameters(
        {"email": "userexample.com"}, param_defs
    )
    if not is_valid and any("pattern" in e for e in errors):
        results.record_pass("Invalid email pattern rejected")
    else:
        results.record_fail("Invalid email pattern rejected", "Should reject invalid pattern")

    # Test invalid email (missing domain)
    is_valid, errors = SkillValidator.validate_parameters(
        {"email": "user@"}, param_defs
    )
    if not is_valid and any("pattern" in e for e in errors):
        results.record_pass("Incomplete email pattern rejected")
    else:
        results.record_fail("Incomplete email pattern rejected", "Should reject incomplete pattern")

    return results.summary()


async def test_enum_validation():
    """Test enum (restricted values) validation"""
    print("\n3. Testing Enum Validation")
    print("=" * 60)

    results = TestResults()

    # Define parameter with enum
    param_defs = [
        {
            "name": "status",
            "type": "string",
            "required": True,
            "description": "Status value",
            "enum": ["active", "inactive", "pending"]
        }
    ]

    # Test valid enum value
    is_valid, errors = SkillValidator.validate_parameters(
        {"status": "active"}, param_defs
    )
    if is_valid:
        results.record_pass("Valid enum value accepted")
    else:
        results.record_fail("Valid enum value accepted", ', '.join(errors))

    # Test another valid enum value
    is_valid, errors = SkillValidator.validate_parameters(
        {"status": "pending"}, param_defs
    )
    if is_valid:
        results.record_pass("Another valid enum value accepted")
    else:
        results.record_fail("Another valid enum value accepted", ', '.join(errors))

    # Test invalid enum value
    is_valid, errors = SkillValidator.validate_parameters(
        {"status": "unknown"}, param_defs
    )
    if not is_valid and any("must be one of" in e for e in errors):
        results.record_pass("Invalid enum value rejected")
    else:
        results.record_fail("Invalid enum value rejected", "Should reject value not in enum")

    # Test numeric enum
    numeric_param_defs = [
        {
            "name": "priority",
            "type": "integer",
            "required": True,
            "description": "Priority level",
            "enum": [1, 2, 3, 4, 5]
        }
    ]

    is_valid, errors = SkillValidator.validate_parameters(
        {"priority": 3}, numeric_param_defs
    )
    if is_valid:
        results.record_pass("Valid numeric enum accepted")
    else:
        results.record_fail("Valid numeric enum accepted", ', '.join(errors))

    is_valid, errors = SkillValidator.validate_parameters(
        {"priority": 10}, numeric_param_defs
    )
    if not is_valid and any("must be one of" in e for e in errors):
        results.record_pass("Invalid numeric enum rejected")
    else:
        results.record_fail("Invalid numeric enum rejected", "Should reject value not in enum")

    return results.summary()


async def test_array_items_validation():
    """Test array item type validation"""
    print("\n4. Testing Array Items Validation")
    print("=" * 60)

    results = TestResults()

    # Define parameter with array items validation
    param_defs = [
        {
            "name": "kb_ids",
            "type": "array",
            "required": True,
            "description": "Knowledge base IDs",
            "items": {"type": "integer"}
        }
    ]

    # Test valid array of integers
    is_valid, errors = SkillValidator.validate_parameters(
        {"kb_ids": [1, 2, 3, 4]}, param_defs
    )
    if is_valid:
        results.record_pass("Valid array of integers accepted")
    else:
        results.record_fail("Valid array of integers accepted", ', '.join(errors))

    # Test empty array
    is_valid, errors = SkillValidator.validate_parameters(
        {"kb_ids": []}, param_defs
    )
    if is_valid:
        results.record_pass("Empty array accepted")
    else:
        results.record_fail("Empty array accepted", ', '.join(errors))

    # Test array with wrong item type
    is_valid, errors = SkillValidator.validate_parameters(
        {"kb_ids": [1, 2, "three", 4]}, param_defs
    )
    if not is_valid and any("[2]" in e and "type" in e for e in errors):
        results.record_pass("Array with wrong item type rejected")
    else:
        results.record_fail("Array with wrong item type rejected", "Should reject wrong item type")

    # Test string array
    string_param_defs = [
        {
            "name": "tags",
            "type": "array",
            "required": True,
            "description": "Tags",
            "items": {"type": "string"}
        }
    ]

    is_valid, errors = SkillValidator.validate_parameters(
        {"tags": ["tag1", "tag2", "tag3"]}, string_param_defs
    )
    if is_valid:
        results.record_pass("Valid array of strings accepted")
    else:
        results.record_fail("Valid array of strings accepted", ', '.join(errors))

    is_valid, errors = SkillValidator.validate_parameters(
        {"tags": ["tag1", 123, "tag3"]}, string_param_defs
    )
    if not is_valid and any("[1]" in e and "type" in e for e in errors):
        results.record_pass("String array with integer rejected")
    else:
        results.record_fail("String array with integer rejected", "Should reject wrong item type")

    return results.summary()


async def test_combined_validation():
    """Test combining multiple validation rules"""
    print("\n5. Testing Combined Validation")
    print("=" * 60)

    results = TestResults()

    # Define parameters with multiple validation rules
    param_defs = [
        {
            "name": "port",
            "type": "integer",
            "required": True,
            "description": "Port number",
            "min": 1,
            "max": 65535
        },
        {
            "name": "protocol",
            "type": "string",
            "required": True,
            "description": "Protocol",
            "enum": ["http", "https", "tcp", "udp"]
        },
        {
            "name": "host",
            "type": "array",
            "required": False,
            "description": "Host list",
            "items": {"type": "string"}
        }
    ]

    # Test all valid
    is_valid, errors = SkillValidator.validate_parameters(
        {
            "port": 8080,
            "protocol": "https",
            "host": ["host1", "host2"]
        },
        param_defs
    )
    if is_valid:
        results.record_pass("All valid parameters accepted")
    else:
        results.record_fail("All valid parameters accepted", ', '.join(errors))

    # Test multiple errors
    is_valid, errors = SkillValidator.validate_parameters(
        {
            "port": 70000,  # Out of range
            "protocol": "ftp",  # Not in enum
            "host": ["host1", 123]  # Wrong item type
        },
        param_defs
    )
    if not is_valid:
        has_port_error = any("port" in e and "maximum" in e for e in errors)
        has_protocol_error = any("protocol" in e and "must be one of" in e for e in errors)
        has_host_error = any("host" in e and "type" in e for e in errors)

        if has_port_error and has_protocol_error and has_host_error:
            results.record_pass("Multiple validation errors detected")
        else:
            results.record_fail("Multiple validation errors detected",
                              f"Missing errors. Port: {has_port_error}, Protocol: {has_protocol_error}, Hosts: {has_host_error}")
    else:
        results.record_fail("Multiple validation errors detected", "Should detect all errors")

    return results.summary()


async def main():
    """Run all extended validation tests"""
    print("\n" + "=" * 60)
    print("Extended Parameter Validation - Test Suite")
    print("=" * 60)

    test_results = []

    # Run all test suites
    test_results.append(await test_range_validation())
    test_results.append(await test_pattern_validation())
    test_results.append(await test_enum_validation())
    test_results.append(await test_array_items_validation())
    test_results.append(await test_combined_validation())

    # Summary
    print("\n" + "=" * 60)
    if all(test_results):
        print("✓ All extended validation tests passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
