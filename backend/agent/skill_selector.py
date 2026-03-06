"""
AI Agent skill selector - converts skills to OpenAI function format
"""
from typing import List, Dict, Any
from backend.skills.models import Skill


def skill_to_openai_function(skill: Skill) -> Dict[str, Any]:
    """Convert a Skill to OpenAI function calling format"""
    properties = {}
    required = []

    for param in skill.parameters or []:
        param_def = {
            "type": param["type"],
            "description": param["description"],
        }

        if param.get("default") is not None:
            param_def["default"] = param["default"]

        properties[param["name"]] = param_def

        if param.get("required", True):
            required.append(param["name"])

    return {
        "type": "function",
        "function": {
            "name": skill.id,
            "description": skill.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


async def get_available_skills_as_tools(
    db, disabled_tools: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all enabled skills and convert them to OpenAI function format.
    Filters out disabled tools.
    """
    from backend.skills.registry import SkillRegistry

    registry = SkillRegistry(db)
    skills = await registry.list_skills(is_enabled=True)

    disabled_set = set(disabled_tools) if disabled_tools else set()

    tools = []
    for skill in skills:
        if skill.id not in disabled_set:
            tools.append(skill_to_openai_function(skill))

    return tools
