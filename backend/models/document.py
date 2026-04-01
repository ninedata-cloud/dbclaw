from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base


class DocCategory(Base):
    __tablename__ = "doc_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(50), nullable=False)  # mysql/postgresql/oracle/sqlserver/general
    parent_id = Column(Integer, ForeignKey("doc_categories.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class DocDocument(Base):
    __tablename__ = "doc_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("doc_categories.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)   # 完整 Markdown，最大约 50K 字符
    summary = Column(Text, nullable=True)    # 100 字内摘要，供 AI 目录使用
    is_builtin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, nullable=True)  # user id，内置文档为 NULL
