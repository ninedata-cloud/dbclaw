from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: bool = True


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    collection_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    document_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    status: str


class SearchResult(BaseModel):
    content: str
    filename: str
    kb_name: str
    distance: float
    metadata: dict
