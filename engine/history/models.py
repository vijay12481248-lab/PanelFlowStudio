from sqlalchemy import Column, String, Integer, JSON, ForeignKey
from engine.database.models import Base


class HistoryRecord(Base):
    __tablename__ = "project_history"
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    schema_version = Column(Integer, nullable=False, default=1)
    revision = Column(Integer, nullable=False, default=0)
    cursor = Column(Integer, nullable=False, default=0)
    entries = Column(JSON, nullable=False, default=list)
    fingerprint = Column(String(64), nullable=False)


class HistoryReceipt(Base):
    __tablename__ = "project_history_receipts"
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    operation_id = Column(String(36), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False)


class HistoryArchive(Base):
    __tablename__ = "project_history_archives"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    journal = Column(JSON, nullable=False)
