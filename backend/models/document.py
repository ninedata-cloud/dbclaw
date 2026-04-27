from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Index
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class DocCategory(Base):
    __tablename__ = "doc_category"
    __table_args__ = (
        Index('idx_doc_category_parent_sort', 'parent_id', 'sort_order'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(50), nullable=False)  # mysql/postgresql/oracle/sqlserver/general
    parent_id = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0)
    icon = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DocDocument(SoftDeleteMixin, Base):
    __tablename__ = "doc_document"
    __table_args__ = (
        Index('idx_doc_document_category_active_sort', 'category_id', 'is_active', 'is_deleted', 'sort_order'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)   # 完整 Markdown，最大约 50K 字符
    summary = Column(Text, nullable=True)    # 100 字内摘要，供 AI 目录使用
    is_builtin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    scope = Column(String(20), default="builtin")
    doc_kind = Column(String(30), default="reference")
    db_types = Column(JSON, nullable=True)
    issue_categories = Column(JSON, nullable=True)
    datasource_ids = Column(JSON, nullable=True)
    host_ids = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    priority = Column(Integer, default=0)
    freshness_level = Column(String(20), default="stable")
    enabled_in_diagnosis = Column(Boolean, default=True)
    diagnosis_profile = Column(JSON, nullable=True)
    compiled_snapshot = Column(JSON, nullable=True)
    compiled_at = Column(DateTime(timezone=True), nullable=True)
    quality_status = Column(String(20), default="draft")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, nullable=True)  # user id，内置文档为 NULL

    @property
    def compile_warnings(self) -> list[str]:
        snapshot = self.compiled_snapshot or {}
        warnings = snapshot.get("warnings") if isinstance(snapshot, dict) else []
        return warnings if isinstance(warnings, list) else []

    @property
    def compiled_snapshot_summary(self) -> dict:
        snapshot = self.compiled_snapshot or {}
        if not isinstance(snapshot, dict):
            return {"unit_count": 0, "unit_type_counts": {}, "skill_count": 0, "warning_count": 0}

        summary = snapshot.get("summary")
        if isinstance(summary, dict):
            return {
                "unit_count": int(summary.get("unit_count") or 0),
                "unit_type_counts": summary.get("unit_type_counts") or {},
                "skill_count": int(summary.get("skill_count") or 0),
                "warning_count": int(summary.get("warning_count") or 0),
            }

        units = snapshot.get("units") if isinstance(snapshot.get("units"), list) else []
        unit_type_counts: dict[str, int] = {}
        skill_ids: set[str] = set()
        for unit in units:
            if not isinstance(unit, dict):
                continue
            unit_type = str(unit.get("unit_type") or "citation")
            unit_type_counts[unit_type] = unit_type_counts.get(unit_type, 0) + 1
            for skill_id in unit.get("recommended_skills") or []:
                if skill_id:
                    skill_ids.add(str(skill_id))
        return {
            "unit_count": len(units),
            "unit_type_counts": unit_type_counts,
            "skill_count": len(skill_ids),
            "warning_count": len(self.compile_warnings),
        }
