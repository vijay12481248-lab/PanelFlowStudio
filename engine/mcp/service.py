"""Hermes Studio Director service."""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from engine.mcp.models import DirectorDecision, TaskEnvelope, ProjectScopeToken, DecisionLogEntry


class DirectorService:
    """Service for managing Hermes Studio Director integration."""
    
    @staticmethod
    def create_decision(
        db: Session,
        project_id: str,
        decision_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        requires_approval: bool = False,
    ) -> DirectorDecision:
        """Create a director decision."""
        decision = DirectorDecision(
            project_id=project_id,
            decision_id=f"decision-{idempotency_key}",
            decision_type=decision_type,
            status="PENDING_REVIEW" if requires_approval else "APPROVED",
            payload=payload,
            idempotency_key=idempotency_key,
            requires_approval=requires_approval,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision
    
    @staticmethod
    def find_by_idempotency_key(db: Session, idempotency_key: str) -> Optional[TaskEnvelope]:
        """Find task envelope by idempotency key."""
        return db.query(TaskEnvelope).filter(
            TaskEnvelope.idempotency_key == idempotency_key
        ).first()
    
    @staticmethod
    def create_task_envelope(
        db: Session,
        project_id: str,
        task_type: str,
        payload: Dict[str, Any],
        created_by: str,
        idempotency_key: str,
        requires_approval: bool = False,
        timeout_seconds: int = 300,
    ) -> TaskEnvelope:
        """Create a task envelope for bounded delegation."""
        # Check for duplicate
        existing = DirectorService.find_by_idempotency_key(db, idempotency_key)
        if existing:
            return existing
        
        envelope = TaskEnvelope(
            project_id=project_id,
            envelope_id=f"envelope-{idempotency_key}",
            task_type=task_type,
            status="PENDING_APPROVAL" if requires_approval else "QUEUED",
            payload=payload,
            created_by=created_by,
            idempotency_key=idempotency_key,
            requires_approval=requires_approval,
            timeout_seconds=timeout_seconds,
        )
        db.add(envelope)
        db.commit()
        db.refresh(envelope)
        return envelope
    
    @staticmethod
    def approve_task_envelope(
        db: Session,
        envelope_id: str,
        approved_by: str,
    ) -> TaskEnvelope:
        """Approve a task envelope."""
        envelope = db.query(TaskEnvelope).filter(
            TaskEnvelope.envelope_id == envelope_id
        ).first()
        if not envelope:
            raise ValueError(f"Task envelope not found: {envelope_id}")
        
        envelope.status = "APPROVED"
        envelope.approved_by = approved_by
        from engine.database.models import utc_now
        envelope.approved_at = utc_now()
        db.commit()
        db.refresh(envelope)
        return envelope
    
    @staticmethod
    def create_scope_token(
        db: Session,
        project_id: str,
        scope: str,
        permissions: List[str],
        created_by: str,
        expires_at: Optional[str] = None,
    ) -> ProjectScopeToken:
        """Create project-scoped token for Hermes."""
        token_id = f"token-{project_id}-{uuid.uuid4().hex[:8]}"
        token = ProjectScopeToken(
            project_id=project_id,
            token_id=token_id,
            scope=scope,
            permissions=permissions,
            created_by=created_by,
            expires_at=expires_at,
        )
        db.add(token)
        db.commit()
        db.refresh(token)
        return token


import uuid
