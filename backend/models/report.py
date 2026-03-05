from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from backend.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    report_type = Column(String(50), default="comprehensive")  # comprehensive, performance, security
    status = Column(String(20), default="generating")  # generating, completed, failed
    summary = Column(Text, nullable=True)
    content_md = Column(Text, nullable=True)
    content_html = Column(Text, nullable=True)
    findings = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
