from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class SkillParameter(BaseModel):
    name: str
    type: str  # string, integer, number, boolean, array, object
    required: bool = True
    default: Optional[Any] = None
    description: str
    # Extended validation
    min: Optional[float] = None  # For integer/float range validation
    max: Optional[float] = None  # For integer/float range validation
    pattern: Optional[str] = None  # For string pattern validation (regex)
    enum: Optional[List[Any]] = None  # For restricted value sets
    items: Optional[Dict[str, Any]] = None  # For array item validation


class SkillDefinition(BaseModel):
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    author: Optional[str] = None
    category: Optional[str] = None
    description: str
    tags: List[str] = []
    parameters: List[SkillParameter] = []
    dependencies: List[str] = []
    permissions: List[str] = []
    timeout: Optional[int] = None  # Execution timeout in seconds (optional)
    code: str

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        valid_permissions = {
            "execute_query",
            "execute_command",
            "read_logs",
            "modify_config",
            "access_kb",
            "read_datasource",
            "execute_any_sql",  # Dangerous: Execute any SQL including DDL/DML
            "execute_any_os_command",  # Dangerous: Execute any OS command
            "access_external_api",  # Access external APIs (web search, etc.)
            "admin",  # Administrative privileges
        }
        for perm in v:
            if perm not in valid_permissions:
                raise ValueError(f"Invalid permission: {perm}")
        return v


class SkillCreate(BaseModel):
    skill: SkillDefinition
    is_enabled: bool = True


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    is_enabled: Optional[bool] = None
    code: Optional[str] = None


class SkillResponse(BaseModel):
    id: str
    name: str
    version: str
    author_id: Optional[int]
    category: Optional[str]
    description: str
    tags: List[str]
    parameters: List[SkillParameter]
    dependencies: List[str]
    permissions: List[str]
    timeout: Optional[int]
    code: str
    is_builtin: bool
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SkillExecutionRequest(BaseModel):
    skill_id: str
    parameters: Dict[str, Any]
    session_id: Optional[int] = None


class SkillExecutionResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int


class SkillRatingCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class SkillRatingResponse(BaseModel):
    id: int
    skill_id: str
    user_id: int
    rating: int
    comment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
