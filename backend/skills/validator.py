"""
Skill validation logic
"""
import ast
import re
from typing import List, Tuple


class SkillValidator:
    """Validates skill code for security and correctness"""

    FORBIDDEN_IMPORTS = {
        "os",
        "subprocess",
    }

    FORBIDDEN_BUILTINS = {
        "eval",
    }

    @staticmethod
    def validate_code(code: str) -> Tuple[bool, List[str]]:
        """
        Validate skill code for security issues.
        Returns (is_valid, list_of_errors)
        """
        errors = []

        # Check for forbidden imports
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"Syntax error: {str(e)}"]

        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in SkillValidator.FORBIDDEN_IMPORTS:
                        errors.append(f"Forbidden import: {alias.name}")

            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in SkillValidator.FORBIDDEN_IMPORTS:
                    errors.append(f"Forbidden import: {node.module}")

            # Check for forbidden builtins
            if isinstance(node, ast.Name):
                if node.id in SkillValidator.FORBIDDEN_BUILTINS:
                    errors.append(f"Forbidden builtin: {node.id}")

            # Check for dangerous attribute access
            if isinstance(node, ast.Attribute):
                if node.attr in ["__globals__", "__code__", "__builtins__"]:
                    errors.append(f"Forbidden attribute access: {node.attr}")

        # Check for required execute function
        has_execute = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute":
                has_execute = True
                # Check function signature
                if len(node.args.args) != 2:
                    errors.append(
                        "execute() must have exactly 2 parameters: (context, params)"
                    )
                break

        if not has_execute:
            errors.append("Skill must define an async execute(context, params) function")

        return len(errors) == 0, errors

    @staticmethod
    def validate_parameters(params: dict, param_definitions: List[dict]) -> Tuple[bool, List[str]]:
        """
        Validate execution parameters against skill parameter definitions.
        Returns (is_valid, list_of_errors)
        """
        errors = []
        param_defs = {p["name"]: p for p in param_definitions}

        # Check required parameters
        for param_def in param_definitions:
            if param_def.get("required", True) and param_def["name"] not in params:
                errors.append(f"Missing required parameter: {param_def['name']}")

        # Check parameter types and extended validation
        for param_name, param_value in params.items():
            if param_name not in param_defs:
                errors.append(f"Unknown parameter: {param_name}")
                continue

            param_def = param_defs[param_name]
            expected_type = param_def["type"]

            # Type check
            if not SkillValidator._check_type(param_value, expected_type):
                errors.append(
                    f"Parameter {param_name} has wrong type. Expected {expected_type}, got {type(param_value).__name__}"
                )
                continue

            # Extended validation
            validation_errors = SkillValidator._validate_extended(param_name, param_value, param_def)
            errors.extend(validation_errors)

        return len(errors) == 0, errors

    @staticmethod
    def _check_type(value, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)

        if expected_type not in type_map:
            return True  # Unknown type, skip validation

        return isinstance(value, type_map[expected_type])

    @staticmethod
    def _validate_extended(param_name: str, param_value, param_def: dict) -> List[str]:
        """
        Perform extended validation (range, pattern, enum, array items).
        Returns list of error messages.
        """
        errors = []

        # Range validation for integers and floats
        if param_def["type"] in ["integer", "float", "number"] and isinstance(param_value, (int, float)):
            if "min" in param_def and param_def["min"] is not None:
                if param_value < param_def["min"]:
                    errors.append(
                        f"Parameter {param_name} value {param_value} is below minimum {param_def['min']}"
                    )
            if "max" in param_def and param_def["max"] is not None:
                if param_value > param_def["max"]:
                    errors.append(
                        f"Parameter {param_name} value {param_value} exceeds maximum {param_def['max']}"
                    )

        # Pattern validation for strings
        if param_def["type"] == "string" and isinstance(param_value, str):
            if "pattern" in param_def and param_def["pattern"] is not None:
                if not re.match(param_def["pattern"], param_value):
                    errors.append(
                        f"Parameter {param_name} value does not match required pattern: {param_def['pattern']}"
                    )

        # Enum validation for restricted values
        if "enum" in param_def and param_def["enum"] is not None:
            if param_value not in param_def["enum"]:
                errors.append(
                    f"Parameter {param_name} value must be one of: {', '.join(map(str, param_def['enum']))}"
                )

        # Array item validation
        if param_def["type"] == "array" and isinstance(param_value, list):
            if "items" in param_def and param_def["items"] is not None:
                items_def = param_def["items"]
                if "type" in items_def:
                    expected_item_type = items_def["type"]
                    for i, item in enumerate(param_value):
                        if not SkillValidator._check_type(item, expected_item_type):
                            errors.append(
                                f"Parameter {param_name}[{i}] has wrong type. Expected {expected_item_type}, got {type(item).__name__}"
                            )

        return errors
