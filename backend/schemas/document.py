# backend/schemas/document.py
from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel
from backend.schemas.base import TimestampSerializerMixin


class DocDiagnosisProfile(BaseModel):
    symptom_tags: List[str] = []
    signal_tags: List[str] = []
    recommended_skills: List[str] = []
    applicability_rules: List[Dict[str, Any]] = []
    evidence_requirements: List[Dict[str, Any]] = []
    related_doc_ids: List[int] = []


class DocCategoryResponse(TimestampSerializerMixin, BaseModel):
    id: int
    name: str
    db_type: str
    parent_id: Optional[int] = None
    sort_order: int
    icon: Optional[str] = None
    created_at: datetime
    children: List["DocCategoryResponse"] = []
    document_count: int = 0

    class Config:
        from_attributes = True

DocCategoryResponse.model_rebuild()


class DocCategoryCreate(BaseModel):
    name: str
    db_type: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    icon: Optional[str] = None


class DocDocumentCreate(BaseModel):
    title: str
    content: str
    summary: Optional[str] = None
    category_id: int
    scope: Optional[str] = None
    doc_kind: Optional[str] = None
    db_types: Optional[List[str]] = None
    issue_categories: Optional[List[str]] = None
    datasource_ids: Optional[List[int]] = None
    host_ids: Optional[List[int]] = None
    tags: Optional[List[str]] = None
    priority: int = 0
    freshness_level: Optional[str] = None
    enabled_in_diagnosis: bool = True
    diagnosis_profile: Optional[DocDiagnosisProfile] = None
    sort_order: int = 0


class DocDocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    scope: Optional[str] = None
    doc_kind: Optional[str] = None
    db_types: Optional[List[str]] = None
    issue_categories: Optional[List[str]] = None
    datasource_ids: Optional[List[int]] = None
    host_ids: Optional[List[int]] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = None
    freshness_level: Optional[str] = None
    enabled_in_diagnosis: Optional[bool] = None
    diagnosis_profile: Optional[DocDiagnosisProfile] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DocDocumentListItem(TimestampSerializerMixin, BaseModel):
    """目录列表项，不含完整 content"""
    id: int
    title: str
    summary: Optional[str]
    category_id: int
    is_builtin: bool
    is_active: bool
    scope: Optional[str] = None
    doc_kind: Optional[str] = None
    db_types: Optional[List[str]] = None
    issue_categories: Optional[List[str]] = None
    datasource_ids: Optional[List[int]] = None
    host_ids: Optional[List[int]] = None
    tags: Optional[List[str]] = None
    priority: int = 0
    freshness_level: Optional[str] = None
    enabled_in_diagnosis: bool = True
    diagnosis_profile: Optional[DocDiagnosisProfile] = None
    quality_status: Optional[str] = None
    compiled_at: Optional[datetime] = None
    compile_warnings: List[str] = []
    compiled_snapshot_summary: Optional[Dict[str, Any]] = None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocDocumentResponse(DocDocumentListItem):
    """完整文档，含 content"""
    content: str

    class Config:
        from_attributes = True
