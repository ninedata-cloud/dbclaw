"""
YAML skill loader
"""
import yaml
from typing import Dict, Any
from backend.skills.schema import SkillDefinition, SkillParameter


class SkillLoader:
    """Loads skills from YAML format"""

    @staticmethod
    def load_from_yaml(yaml_content: str) -> SkillDefinition:
        """Parse YAML content and return SkillDefinition"""
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {str(e)}")

        # Convert parameters to SkillParameter objects
        parameters = []
        for param in data.get("parameters", []):
            parameters.append(SkillParameter(**param))

        # Build SkillDefinition
        skill_def = SkillDefinition(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            author=data.get("author"),
            category=data.get("category"),
            description=data["description"],
            tags=data.get("tags", []),
            parameters=parameters,
            dependencies=data.get("dependencies", []),
            permissions=data.get("permissions", []),
            timeout=data.get("timeout"),
            code=data["code"],
        )

        return skill_def

    @staticmethod
    def dump_to_yaml(skill_def: SkillDefinition) -> str:
        """Convert SkillDefinition to YAML string"""
        data = {
            "id": skill_def.id,
            "name": skill_def.name,
            "version": skill_def.version,
            "author": skill_def.author,
            "category": skill_def.category,
            "description": skill_def.description,
            "tags": skill_def.tags,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                }
                for p in skill_def.parameters
            ],
            "dependencies": skill_def.dependencies,
            "permissions": skill_def.permissions,
            "timeout": skill_def.timeout,
            "code": skill_def.code,
        }

        return yaml.dump(data, default_flow_style=False, sort_keys=False)
