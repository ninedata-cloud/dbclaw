"""
Skill executor - runs skills in a sandboxed environment
"""
import asyncio
import time
import json
from decimal import Decimal
from typing import Dict, Any
from backend.skills.models import Skill
from backend.skills.context import SkillContext
from backend.skills.validator import SkillValidator


class SkillExecutor:
    """Executes skills in a controlled environment"""

    DEFAULT_TIMEOUT = 30  # seconds
    MAX_TIMEOUT = 300  # 5 minutes

    @staticmethod
    def _serialize_result(obj):
        """Convert non-serializable objects to serializable format"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: SkillExecutor._serialize_result(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [SkillExecutor._serialize_result(item) for item in obj]
        return obj

    async def execute(
        self, skill: Skill, params: Dict[str, Any], context: SkillContext
    ) -> Dict[str, Any]:
        """
        Execute a skill with given parameters and context.
        Returns the skill's result or raises an exception.
        """
        # Validate parameters
        param_definitions = skill.parameters or []
        is_valid, errors = SkillValidator.validate_parameters(params, param_definitions)
        if not is_valid:
            raise ValueError(f"Invalid parameters: {', '.join(errors)}")

        # Check permissions
        skill_permissions = skill.permissions or []
        for perm in skill_permissions:
            if perm not in context.permissions:
                raise PermissionError(
                    f"Skill requires permission '{perm}' which is not granted"
                )

        # Execute with timeout
        start_time = time.time()
        try:
            # Use skill-specific timeout if provided, otherwise use default
            timeout = skill.timeout if skill.timeout else self.DEFAULT_TIMEOUT
            # Cap at MAX_TIMEOUT for safety
            timeout = min(timeout, self.MAX_TIMEOUT)

            result = await asyncio.wait_for(
                self._execute_code(skill.code, params, context),
                timeout=timeout,
            )
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log execution
            await self._log_execution(
                skill, params, result, None, execution_time_ms, context
            )

            return result

        except asyncio.TimeoutError:
            execution_time_ms = int((time.time() - start_time) * 1000)
            timeout_used = skill.timeout if skill.timeout else self.DEFAULT_TIMEOUT
            error = f"Skill execution timed out after {timeout_used}s"
            await self._log_execution(
                skill, params, None, error, execution_time_ms, context
            )
            raise TimeoutError(error)

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error = str(e)
            await self._log_execution(
                skill, params, None, error, execution_time_ms, context
            )
            raise

    async def _execute_code(
        self, code: str, params: Dict[str, Any], context: SkillContext
    ) -> Dict[str, Any]:
        """Execute the skill code in a restricted environment"""
        # Create restricted globals
        restricted_globals = {
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "set": set,
                "range": range,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "sum": sum,
                "min": min,
                "max": max,
                "abs": abs,
                "round": round,
                "any": any,
                "all": all,
                "isinstance": isinstance,
                "hasattr": hasattr,
                "getattr": getattr,
                "Exception": Exception,
                "ValueError": ValueError,
                "TypeError": TypeError,
                "KeyError": KeyError,
                "IndexError": IndexError,
                "AttributeError": AttributeError,
                "__import__": __import__,
            },
            "json": __import__("json"),
            "re": __import__("re"),
            "datetime": __import__("datetime"),
            "asyncio": asyncio,
        }

        # Execute code to define functions
        exec(code, restricted_globals)

        # Call the execute function
        if "execute" not in restricted_globals:
            raise ValueError("Skill code must define an 'execute' function")

        execute_func = restricted_globals["execute"]
        result = await execute_func(context, params)

        return result

    async def _log_execution(
        self,
        skill: Skill,
        params: Dict[str, Any],
        result: Any,
        error: str,
        execution_time_ms: int,
        context: SkillContext,
    ):
        """Log skill execution to database"""
        from backend.skills.models import SkillExecution

        # Serialize result to handle Decimal and other non-JSON types
        serialized_result = None
        if result is not None:
            serialized_result = self._serialize_result(result)

        execution = SkillExecution(
            skill_id=skill.id,
            session_id=context.session_id,
            user_id=context.user_id,
            parameters=params,
            result=serialized_result,
            error=error,
            execution_time_ms=execution_time_ms,
        )

        context.db.add(execution)
        await context.db.commit()
