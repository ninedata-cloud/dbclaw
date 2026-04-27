"""Backward-compatible re-export for skill ORM models."""

from backend.models.skill import Skill, SkillExecution, SkillRating

__all__ = ["Skill", "SkillExecution", "SkillRating"]
