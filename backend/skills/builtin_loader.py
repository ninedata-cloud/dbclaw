"""
Built-in skill loader - loads skills from builtin directory on startup
"""
from pathlib import Path
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from backend.skills.registry import SkillRegistry
from backend.skills.loader import SkillLoader
from backend.skills.builtin_metadata import normalize_builtin_skill_definition
from backend.models.skill import Skill


async def load_builtin_skills(db: AsyncSession) -> List[Skill]:
    """Load all built-in skills from the builtin directory"""
    builtin_dir = Path(__file__).parent / "builtin"
    registry = SkillRegistry(db)
    loaded_skills = []

    if not builtin_dir.exists():
        return loaded_skills

    for yaml_file in sorted(builtin_dir.glob("*.yaml")):
        try:
            yaml_content = yaml_file.read_text()
            skill_def = SkillLoader.load_from_yaml(yaml_content)
            skill_def = normalize_builtin_skill_definition(skill_def)
            skill = await registry.register_skill(skill_def, is_builtin=True)
            loaded_skills.append(skill)
            print(f"Loaded built-in skill: {skill.id}")
        except Exception as e:
            print(f"Error loading skill from {yaml_file}: {str(e)}")

    return loaded_skills
