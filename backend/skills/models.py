from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, CheckConstraint, UniqueConstraint
from sqlalchemy.sql import func
from backend.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    version = Column(String(20), nullable=False)
    author_id = Column(Integer, nullable=True)
    category = Column(String(50))
    description = Column(Text)
    tags = Column(JSON)  # List of strings
    parameters = Column(JSON)  # List of parameter definitions
    dependencies = Column(JSON)  # List of dependency specifications
    permissions = Column(JSON)  # List of required permissions
    timeout = Column(Integer, nullable=True)  # Execution timeout in seconds (optional)
    code = Column(Text, nullable=False)
    is_builtin = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SkillExecution(Base):
    __tablename__ = "skill_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(String(100), nullable=False)
    session_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    parameters = Column(JSON)
    result = Column(JSON)
    error = Column(Text)
    execution_time_ms = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class SkillRating(Base):
    __tablename__ = "skill_ratings"
    __table_args__ = (
        UniqueConstraint("skill_id", "user_id", name="uq_skill_ratings_skill_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(String(100), nullable=False)
    user_id = Column(Integer, nullable=False)
    rating = Column(Integer, CheckConstraint("rating >= 1 AND rating <= 5"), nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
