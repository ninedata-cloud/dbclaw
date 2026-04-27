from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.sql import func

from backend.database import Base


class Skill(Base):
    __tablename__ = "skill"

    id = Column(String(100), primary_key=True)
    name = Column(String(200), nullable=False)
    version = Column(String(20), nullable=False)
    author_id = Column(Integer, nullable=True)
    category = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=False, default=list)  # List of strings
    parameters = Column(JSON, nullable=False, default=list)  # List of parameter definitions
    dependencies = Column(JSON, nullable=False, default=list)  # List of dependency specifications
    permissions = Column(JSON, nullable=False, default=list)  # List of required permissions
    timeout = Column(Integer, nullable=True)  # Execution timeout in seconds (optional)
    code = Column(Text, nullable=False)
    is_builtin = Column(Boolean, nullable=False, default=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SkillExecution(Base):
    __tablename__ = "skill_execution"
    __table_args__ = (
        Index('idx_skill_executions_skill_id_created_at', 'skill_id', 'created_at'),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    skill_id = Column(String(100), nullable=False, index=True)
    session_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    parameters = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SkillRating(Base):
    __tablename__ = "skill_rating"
    __table_args__ = (
        UniqueConstraint("skill_id", "user_id", name="uq_skill_rating_skill_user"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    skill_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    rating = Column(Integer, CheckConstraint("rating >= 1 AND rating <= 5"), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
