"""Hermes Studio Director MCP models."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from engine.database.models import Base, utc_now
import uuid


class DirectorDecision(Base):
    """Director decisions persisted in PanelFlow."""
    __tablename__ = "director_decisions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_id = Column(String(64), nullable=False, unique=True, index=True)
    decision_type = Column(String(64), nullable=False)  # RENDER_APPROVE, STORYBOARD_UPDATE, etc.
    status = Column(String(32), nullable=False, default="PENDING")  # PENDING, APPROVED, REJECTED, PENDING_REVIEW
    payload = Column(JSON, default=dict, nullable=False)
    approved_by = Column(String(256), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    requires_approval = Column(Boolean, default=False, nullable=False)
    
    project = relationship("ProjectRecord", back_populates="director_decisions")


class TaskEnvelope(Base):
    """Task envelopes for bounded delegation."""
    __tablename__ = "task_envelopes"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    envelope_id = Column(String(64), nullable=False, unique=True, index=True)
    task_type = Column(String(64), nullable=False)  # RENDER_CREATE, STORYBOARD_MODIFY, etc.
    status = Column(String(32), nullable=False, default="QUEUED")  # QUEUED, IN_PROGRESS, COMPLETED, FAILED, PENDING_APPROVAL, APPROVED
    payload = Column(JSON, default=dict, nullable=False)
    created_by = Column(String(256), nullable=False)
    approved_by = Column(String(256), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    requires_approval = Column(Boolean, default=False, nullable=False)
    timeout_seconds = Column(Integer, default=300, nullable=False)
    error_message = Column(Text, nullable=True)
    
    project = relationship("ProjectRecord", back_populates="task_envelopes")


class ProjectScopeToken(Base):
    """Project-scoped access tokens for Hermes."""
    __tablename__ = "project_scope_tokens"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    token_id = Column(String(128), nullable=False, unique=True, index=True)
    scope = Column(String(32), nullable=False, default="READ_ONLY")  # READ_ONLY, READ_WRITE
    permissions = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(String(256), nullable=True)  # ISO format
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(256), nullable=False)
    
    project = relationship("ProjectRecord", back_populates="scope_tokens")
    
    def is_valid(self) -> bool:
        """Check if token is valid (active and not expired)."""
        if not self.is_active:
            return False
        if self.expires_at:
            try:
                exp_date = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
                return datetime.utcnow().replace(tzinfo=exp_date.tzinfo) < exp_date
            except:
                return False
        return True
    
    def has_permission(self, permission: str) -> bool:
        """Check if token has specific permission."""
        return permission in (self.permissions or [])


class DecisionLogEntry(Base):
    """Audit trail for director decisions."""
    __tablename__ = "decision_logs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)  # DECISION_CREATED, DECISION_APPROVED, etc.
    actor = Column(String(256), nullable=False)
    timestamp = Column(DateTime, default=utc_now, nullable=False)
    details = Column(JSON, default=dict, nullable=False)
    
    project = relationship("ProjectRecord", back_populates="decision_logs")
