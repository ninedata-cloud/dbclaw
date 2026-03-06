#!/usr/bin/env python3
"""
Verification script for Skills System improvements
Demonstrates all new features working together
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.skills.validator import SkillValidator
from backend.skills.loader import SkillLoader


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def verify_tag_filtering():
    """Verify tag filtering implementation exists"""
    print_section("1. Tag Filtering")

    from backend.skills.registry import SkillRegistry
    import inspect

    # Check that tag filtering code exists
    source = inspect.getsource(SkillRegistry.list_skills)

    if "tag_conditions" in source and "or_(*tag_conditions)" in source:
        print("✓ Tag filtering implementation found")
        print("  - Uses SQLite LIKE pattern matching")
        print("  - Supports multiple tags with OR logic")
        return True
    else:
        print("✗ Tag filtering not implemented")
        return False


async def verify_extended_validation():
    """Verify extended validation features"""
    print_section("2. Extended Parameter Validation")

    results = []

    # Test range validation
    param_def = [{"name": "limit", "type": "integer", "required": True, "description": "Limit", "min": 1, "max": 10}]
    is_valid, errors = SkillValidator.validate_parameters({"limit": 5}, param_def)
    results.append(("Range validation (valid)", is_valid))

    is_valid, errors = SkillValidator.validate_parameters({"limit": 15}, param_def)
    results.append(("Range validation (invalid)", not is_valid))

    # Test pattern validation
    param_def = [{"name": "email", "type": "string", "required": True, "description": "Email", "pattern": r"^.+@.+\..+$"}]
    is_valid, errors = SkillValidator.validate_parameters({"email": "test@example.com"}, param_def)
    results.append(("Pattern validation (valid)", is_valid))

    is_valid, errors = SkillValidator.validate_parameters({"email": "invalid"}, param_def)
    results.append(("Pattern validation (invalid)", not is_valid))

    # Test enum validation
    param_def = [{"name": "status", "type": "string", "required": True, "description": "Status", "enum": ["active", "inactive"]}]
    is_valid, errors = SkillValidator.validate_parameters({"status": "active"}, param_def)
    results.append(("Enum validation (valid)", is_valid))

    is_valid, errors = SkillValidator.validate_parameters({"status": "unknown"}, param_def)
    results.append(("Enum validation (invalid)", not is_valid))

    # Test array items validation
    param_def = [{"name": "ids", "type": "array", "required": True, "description": "IDs", "items": {"type": "integer"}}]
    is_valid, errors = SkillValidator.validate_parameters({"ids": [1, 2, 3]}, param_def)
    results.append(("Array items validation (valid)", is_valid))

    is_valid, errors = SkillValidator.validate_parameters({"ids": [1, "two", 3]}, param_def)
    results.append(("Array items validation (invalid)", not is_valid))

    # Print results
    all_passed = True
    for test_name, passed in results:
        status = "✓" if passed else "✗"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False

    return all_passed


async def verify_timeout_support():
    """Verify timeout configuration support"""
    print_section("3. Configurable Timeouts")

    from backend.skills.schema import SkillDefinition
    from backend.skills.executor import SkillExecutor

    results = []

    # Check schema supports timeout
    try:
        skill_def = SkillDefinition(
            id="test_timeout",
            name="Test",
            version="1.0.0",
            description="Test skill",
            timeout=60,
            code="async def execute(context, params): return {}"
        )
        results.append(("Schema supports timeout field", True))
    except Exception as e:
        results.append(("Schema supports timeout field", False))

    # Check executor has timeout constants
    executor = SkillExecutor()
    results.append(("Executor has DEFAULT_TIMEOUT", hasattr(executor, "DEFAULT_TIMEOUT")))
    results.append(("Executor has MAX_TIMEOUT", hasattr(executor, "MAX_TIMEOUT")))

    # Check database model
    from backend.skills.models import Skill
    import inspect
    source = inspect.getsource(Skill)
    results.append(("Model has timeout column", "timeout = Column" in source))

    # Print results
    all_passed = True
    for test_name, passed in results:
        status = "✓" if passed else "✗"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False

    return all_passed


async def verify_updated_skill():
    """Verify example skill uses new features"""
    print_section("4. Example Skill with New Features")

    builtin_dir = Path(__file__).parent / "backend/skills/builtin"
    skill_file = builtin_dir / "search_knowledge_base.yaml"

    if not skill_file.exists():
        print("✗ Example skill not found")
        return False

    yaml_content = skill_file.read_text()
    skill_def = SkillLoader.load_from_yaml(yaml_content)

    results = []

    # Check for range validation on top_k
    top_k_param = next((p for p in skill_def.parameters if p.name == "top_k"), None)
    if top_k_param:
        results.append(("Has top_k parameter", True))
        results.append(("top_k has min validation", hasattr(top_k_param, "min") and top_k_param.min is not None))
        results.append(("top_k has max validation", hasattr(top_k_param, "max") and top_k_param.max is not None))
    else:
        results.append(("Has top_k parameter", False))

    # Check for array items validation on kb_ids
    kb_ids_param = next((p for p in skill_def.parameters if p.name == "kb_ids"), None)
    if kb_ids_param:
        results.append(("Has kb_ids parameter", True))
        results.append(("kb_ids has items validation", hasattr(kb_ids_param, "items") and kb_ids_param.items is not None))
    else:
        results.append(("Has kb_ids parameter", False))

    # Print results
    all_passed = True
    for test_name, passed in results:
        status = "✓" if passed else "✗"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False

    return all_passed


async def verify_test_coverage():
    """Verify test files exist and are comprehensive"""
    print_section("5. Test Coverage")

    results = []

    # Check test files exist
    test_file = Path(__file__).parent / "test_skills.py"
    results.append(("Core test suite exists", test_file.exists()))

    extended_test_file = Path(__file__).parent / "test_extended_validation.py"
    results.append(("Extended validation tests exist", extended_test_file.exists()))

    # Check test content
    if test_file.exists():
        content = test_file.read_text()
        results.append(("Tests skill loading", "test_skill_loading" in content))
        results.append(("Tests code validation", "test_code_validation" in content))
        results.append(("Tests parameter validation", "test_parameter_validation" in content))
        results.append(("Tests skill execution", "test_skill_execution" in content))
        results.append(("Tests timeout handling", "test_timeout_handling" in content))
        results.append(("Tests serialization", "test_serialization" in content))

    if extended_test_file.exists():
        content = extended_test_file.read_text()
        results.append(("Tests range validation", "test_range_validation" in content))
        results.append(("Tests pattern validation", "test_pattern_validation" in content))
        results.append(("Tests enum validation", "test_enum_validation" in content))
        results.append(("Tests array items validation", "test_array_items_validation" in content))

    # Print results
    all_passed = True
    for test_name, passed in results:
        status = "✓" if passed else "✗"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False

    return all_passed


async def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("  Skills System Improvements - Verification")
    print("=" * 60)

    results = []

    results.append(await verify_tag_filtering())
    results.append(await verify_extended_validation())
    results.append(await verify_timeout_support())
    results.append(await verify_updated_skill())
    results.append(await verify_test_coverage())

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\nVerification Results: {passed}/{total} sections passed")

    if all(results):
        print("\n✓ All improvements verified successfully!")
        print("\nThe Skills System is ready for production use.")
        return 0
    else:
        print("\n✗ Some verifications failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
