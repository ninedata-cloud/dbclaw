"""
Skill management API endpoints
"""
import logging

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from backend.database import get_db
from backend.i18n.errors import ApiError
from backend.models.user import User
from backend.dependencies import get_current_user
from backend.skills.registry import SkillRegistry
from backend.skills.builtin_metadata import sort_skill_categories
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext
from backend.skills.loader import SkillLoader
from backend.skills.schema import (
    SkillCreate,
    SkillUpdate,
    SkillResponse,
    SkillExecutionRequest,
    SkillExecutionResponse,
    SkillRatingCreate,
    SkillRatingResponse,
)
from backend.models.skill import Skill, SkillRating, SkillExecution
from sqlalchemy import select, func
from backend.i18n.locale import get_active_locale, message_payload, translate

router = APIRouter(prefix="/api/skills", tags=["skills"])
logger = logging.getLogger(__name__)


def _serialize_skill(skill: Skill, locale: str) -> dict:
    """Localize built-in metadata while leaving user-authored skills untouched."""
    payload = SkillResponse.model_validate(skill).model_dump(mode="json")
    if not skill.is_builtin:
        return payload
    translation = (getattr(skill, "i18n", None) or {}).get(locale)
    if not isinstance(translation, dict):
        return payload
    payload["name"] = translation.get("name") or payload["name"]
    payload["description"] = translation.get("description") or payload["description"]
    parameter_descriptions = translation.get("parameter_descriptions") or {}
    for parameter in payload["parameters"]:
        parameter["description"] = parameter_descriptions.get(
            parameter["name"], parameter["description"]
        )
    return payload


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise ApiError(403, "auth.admin_required")


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    category: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    is_builtin: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all skills with optional filters"""
    registry = SkillRegistry(db)
    skills = await registry.list_skills(
        category=category, is_enabled=is_enabled, is_builtin=is_builtin
    )
    return [_serialize_skill(skill, get_active_locale()) for skill in skills]


@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all skill categories"""
    result = await db.execute(
        select(Skill.category).distinct().where(Skill.category.isnot(None))
    )
    categories = sort_skill_categories(row[0] for row in result.all())
    return {"categories": categories}


@router.get("/search")
async def search_skills(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search skills by name or description"""
    registry = SkillRegistry(db)
    skills = await registry.search_skills(q)
    return [_serialize_skill(skill, get_active_locale()) for skill in skills]


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific skill by ID"""
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)
    if not skill:
        raise ApiError(404, "skill.not_found")
    return _serialize_skill(skill, get_active_locale())


@router.post("", response_model=SkillResponse)
async def create_skill(
    skill_create: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new skill"""
    _require_admin(current_user)
    registry = SkillRegistry(db)
    try:
        skill = await registry.register_skill(
            skill_create.skill, author_id=current_user.id, is_builtin=False
        )
        return _serialize_skill(skill, get_active_locale())
    except ValueError as e:
        raise ApiError(400, "operation.failed") from e


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    skill_update: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing skill"""
    _require_admin(current_user)
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)

    if not skill:
        raise ApiError(404, "skill.not_found")

    # Update fields
    if skill_update.name is not None:
        skill.name = skill_update.name
    if skill_update.description is not None:
        skill.description = skill_update.description
    if skill_update.tags is not None:
        skill.tags = skill_update.tags
    if skill_update.is_enabled is not None:
        skill.is_enabled = skill_update.is_enabled
    if skill_update.code is not None:
        # Validate code
        from backend.skills.validator import SkillValidator

        is_valid, errors = SkillValidator.validate_code(skill_update.code)
        if not is_valid:
            raise ApiError(400, "request.validation.invalid", {"errors": errors})
        skill.code = skill_update.code

    await db.commit()
    await db.refresh(skill)
    return _serialize_skill(skill, get_active_locale())


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a skill"""
    _require_admin(current_user)
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)

    if not skill:
        raise ApiError(404, "skill.not_found")

    if skill.is_builtin:
        raise ApiError(403, "operation.not_allowed")

    try:
        await registry.unregister_skill(skill_id)
        return message_payload("skill.deleted", success=True)
    except ValueError as e:
        raise ApiError(400, "operation.failed") from e


@router.post("/{skill_id}/test", response_model=SkillExecutionResponse)
async def test_skill(
    skill_id: str,
    execution_request: SkillExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test a skill execution"""
    _require_admin(current_user)
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)

    if not skill:
        raise ApiError(404, "skill.not_found")
    if not skill.is_builtin:
        raise ApiError(403, "operation.not_allowed")

    # Determine timeout for testing (use skill timeout or default)
    from backend.skills.executor import SkillExecutor
    timeout = skill.timeout if skill.timeout else SkillExecutor.DEFAULT_TIMEOUT

    # Create execution context with all permissions for testing
    context = SkillContext(
        db=db,
        user_id=current_user.id,
        session_id=execution_request.session_id,
        permissions=skill.permissions or [],
        timeout=timeout,
    )

    # Execute skill
    executor = SkillExecutor()
    import time

    start_time = time.time()
    try:
        result = await executor.execute(skill, execution_request.parameters, context)
        execution_time_ms = int((time.time() - start_time) * 1000)
        return SkillExecutionResponse(
            success=True, result=result, execution_time_ms=execution_time_ms
        )
    except Exception as e:
        logger.exception("Built-in skill test failed: skill_id=%s", skill_id)
        execution_time_ms = int((time.time() - start_time) * 1000)
        return SkillExecutionResponse(
            success=False,
            error=translate(get_active_locale(), "operation.failed"),
            error_code="operation.failed",
            execution_time_ms=execution_time_ms,
        )


@router.post("/import", response_model=SkillResponse)
async def import_skill(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import a skill from YAML file"""
    _require_admin(current_user)
    if not file.filename.endswith((".yaml", ".yml")):
        raise ApiError(400, "upload.unsupported_type")

    try:
        content = await file.read()
        yaml_content = content.decode("utf-8")
        skill_def = SkillLoader.load_from_yaml(yaml_content)

        registry = SkillRegistry(db)
        skill = await registry.register_skill(
            skill_def, author_id=current_user.id, is_builtin=False
        )
        return skill
    except Exception as e:
        raise ApiError(400, "request.validation.invalid") from e


@router.get("/{skill_id}/export")
async def export_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a skill as YAML"""
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)

    if not skill:
        raise ApiError(404, "skill.not_found")

    # Convert to SkillDefinition
    from backend.skills.schema import SkillDefinition, SkillParameter, SkillTranslation

    skill_def = SkillDefinition(
        id=skill.id,
        name=skill.name,
        version=skill.version,
        author=None,
        category=skill.category,
        description=skill.description,
        tags=skill.tags or [],
        parameters=[SkillParameter(**p) for p in (skill.parameters or [])],
        dependencies=skill.dependencies or [],
        permissions=skill.permissions or [],
        code=skill.code,
        i18n={
            locale: SkillTranslation(**translation)
            for locale, translation in (skill.i18n or {}).items()
        },
    )

    yaml_content = SkillLoader.dump_to_yaml(skill_def)

    from fastapi.responses import Response

    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f"attachment; filename={skill_id}.yaml"},
    )


@router.post("/{skill_id}/rate", response_model=SkillRatingResponse)
async def rate_skill(
    skill_id: str,
    rating_create: SkillRatingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rate a skill"""
    registry = SkillRegistry(db)
    skill = await registry.get_skill(skill_id)

    if not skill:
        raise ApiError(404, "skill.not_found")

    # Check if user already rated this skill
    result = await db.execute(
        select(SkillRating).where(
            SkillRating.skill_id == skill_id, SkillRating.user_id == current_user.id
        )
    )
    existing_rating = result.scalar_one_or_none()

    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating_create.rating
        existing_rating.comment = rating_create.comment
        rating = existing_rating
    else:
        # Create new rating
        rating = SkillRating(
            skill_id=skill_id,
            user_id=current_user.id,
            rating=rating_create.rating,
            comment=rating_create.comment,
        )
        db.add(rating)

    await db.commit()
    await db.refresh(rating)
    return rating


@router.get("/{skill_id}/executions")
async def get_skill_executions(
    skill_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get execution history for a skill"""
    result = await db.execute(
        select(SkillExecution)
        .where(SkillExecution.skill_id == skill_id)
        .order_by(SkillExecution.created_at.desc())
        .limit(limit)
    )
    executions = result.scalars().all()

    return [
        {
            "id": e.id,
            "parameters": e.parameters,
            "result": e.result,
            "error": e.error,
            "execution_time_ms": e.execution_time_ms,
            "created_at": e.created_at.isoformat(),
        }
        for e in executions
    ]
