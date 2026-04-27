"""
Skill registry - central registry for all skills
"""
from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, Text
from backend.models.skill import Skill
from backend.skills.schema import SkillDefinition
from backend.skills.validator import SkillValidator


class SkillRegistry:
    """Central registry for skill management"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: Dict[str, Skill] = {}

    async def register_skill(
        self, skill_def: SkillDefinition, author_id: Optional[int] = None, is_builtin: bool = False
    ) -> Skill:
        """Register a new skill or update existing one"""
        # Validate code
        is_valid, errors = SkillValidator.validate_code(skill_def.code)
        if not is_valid:
            raise ValueError(f"Invalid skill code: {', '.join(errors)}")

        # Check if skill exists
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_def.id)
        )
        existing_skill = result.scalar_one_or_none()

        if existing_skill:
            # Update existing skill
            existing_skill.name = skill_def.name
            existing_skill.version = skill_def.version
            existing_skill.category = skill_def.category
            existing_skill.description = skill_def.description
            existing_skill.tags = skill_def.tags
            existing_skill.parameters = [p.model_dump() for p in skill_def.parameters]
            existing_skill.dependencies = skill_def.dependencies
            existing_skill.permissions = skill_def.permissions
            existing_skill.timeout = skill_def.timeout
            existing_skill.code = skill_def.code
            skill = existing_skill
        else:
            # Create new skill
            skill = Skill(
                id=skill_def.id,
                name=skill_def.name,
                version=skill_def.version,
                author_id=author_id,
                category=skill_def.category,
                description=skill_def.description,
                tags=skill_def.tags,
                parameters=[p.model_dump() for p in skill_def.parameters],
                dependencies=skill_def.dependencies,
                permissions=skill_def.permissions,
                timeout=skill_def.timeout,
                code=skill_def.code,
                is_builtin=is_builtin,
                is_enabled=True,
            )
            self.db.add(skill)

        await self.db.commit()
        await self.db.refresh(skill)

        # Update cache
        self._cache[skill.id] = skill

        return skill

    async def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID"""
        # Check cache first
        if skill_id in self._cache:
            return self._cache[skill_id]

        # Query database
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id)
        )
        skill = result.scalar_one_or_none()

        if skill:
            self._cache[skill_id] = skill

        return skill

    async def list_skills(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_enabled: Optional[bool] = None,
        is_builtin: Optional[bool] = None,
    ) -> List[Skill]:
        """List skills with optional filters"""
        query = select(Skill)

        if category:
            query = query.where(Skill.category == category)

        if is_enabled is not None:
            query = query.where(Skill.is_enabled == is_enabled)

        if is_builtin is not None:
            query = query.where(Skill.is_builtin == is_builtin)

        # Tag filtering (JSON contains)
        if tags:
            # Check if any of the provided tags exist in the JSON array
            tag_conditions = []
            for tag in tags:
                tag_conditions.append(cast(Skill.tags, Text).like(f'%"{tag}"%'))
            if tag_conditions:
                query = query.where(or_(*tag_conditions))

        result = await self.db.execute(query)
        skills = result.scalars().all()

        return list(skills)

    async def search_skills(self, query: str) -> List[Skill]:
        """Search skills by id, name, description, tags, or code (case-insensitive)"""
        result = await self.db.execute(
            select(Skill).where(
                or_(
                    Skill.id.ilike(f"%{query}%"),
                    Skill.name.ilike(f"%{query}%"),
                    Skill.description.ilike(f"%{query}%"),
                    cast(Skill.tags, Text).like(f'%"{query}"%'),  # JSON array contains (case-sensitive for JSON)
                    Skill.code.ilike(f"%{query}%"),
                )
            )
        )
        skills = result.scalars().all()
        return list(skills)

    async def unregister_skill(self, skill_id: str) -> bool:
        """Remove a skill from the registry"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return False

        # Don't allow deleting built-in skills
        if skill.is_builtin:
            raise ValueError("Cannot delete built-in skills")

        await self.db.delete(skill)
        await self.db.commit()

        # Remove from cache
        if skill_id in self._cache:
            del self._cache[skill_id]

        return True

    async def toggle_skill(self, skill_id: str, enabled: bool) -> bool:
        """Enable or disable a skill"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return False

        skill.is_enabled = enabled
        await self.db.commit()

        # Update cache
        self._cache[skill_id] = skill

        return True


# Global registry instance (will be initialized per request)
_registry_instance = None


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry instance"""
    return _registry_instance


def set_skill_registry(registry: SkillRegistry):
    """Set the global skill registry instance"""
    global _registry_instance
    _registry_instance = registry
