"""Provider registry for managing AI provider configurations."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from engine.database.session import SessionLocal
from engine.ai_gateway.contracts import ProviderConfig, HealthStatus


class ProviderRegistry:
    """Central registry for AI provider configurations."""
    
    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}
        self._loaded = False
    
    def _get_db_session(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def load_from_db(self) -> None:
        """Load all providers from database."""
        if self._loaded:
            return
        
        db = self._get_db_session()
        try:
            result = db.execute(text("""
                SELECT id, provider_type, display_name, enabled, auth_type,
                       credential_ref, endpoint_url, settings, privacy_options,
                       routing_priority, created_at, updated_at
                FROM ai_provider_configs
            """))
            
            for row in result:
                provider = ProviderConfig(
                    config_id=row[0],
                    provider_type=row[1],
                    display_name=row[2],
                    enabled=row[3],
                    auth_type=row[4] or "api_key",
                    credential_ref=row[5],
                    endpoint_url=row[6],
                    settings={},  # Would be parsed from JSON
                    privacy_options={},
                    routing_priority=row[10] or 100
                )
                self._providers[provider.config_id] = provider
            
            self._loaded = True
        finally:
            db.close()
    
    def register(self, provider: ProviderConfig) -> str:
        """Register a new provider configuration."""
        if not provider.config_id:
            provider.config_id = str(uuid.uuid4())
        
        db = self._get_db_session()
        try:
            db.execute(text("""
                INSERT INTO ai_provider_configs (
                    id, provider_type, display_name, enabled, auth_type,
                    credential_ref, endpoint_url, settings, privacy_options,
                    routing_priority, created_at, updated_at
                ) VALUES (
                    :id, :provider_type, :display_name, :enabled, :auth_type,
                    :credential_ref, :endpoint_url, :settings, :privacy_options,
                    :routing_priority, :created_at, :updated_at
                )
            """), {
                "id": provider.config_id,
                "provider_type": provider.provider_type,
                "display_name": provider.display_name,
                "enabled": provider.enabled,
                "auth_type": provider.auth_type,
                "credential_ref": provider.credential_ref,
                "endpoint_url": provider.endpoint_url,
                "settings": "{}",
                "privacy_options": "{}",
                "routing_priority": provider.routing_priority,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            db.commit()
            
            self._providers[provider.config_id] = provider
            return provider.config_id
        finally:
            db.close()
    
    def update(self, provider_id: str, updates: Dict) -> bool:
        """Update provider configuration."""
        if provider_id not in self._providers:
            return False
        
        db = self._get_db_session()
        try:
            # Build dynamic update query
            set_clauses = []
            params = {"id": provider_id}
            
            if "display_name" in updates:
                set_clauses.append("display_name = :display_name")
                params["display_name"] = updates["display_name"]
            
            if "enabled" in updates:
                set_clauses.append("enabled = :enabled")
                params["enabled"] = updates["enabled"]
            
            if "endpoint_url" in updates:
                set_clauses.append("endpoint_url = :endpoint_url")
                params["endpoint_url"] = updates["endpoint_url"]
            
            if "routing_priority" in updates:
                set_clauses.append("routing_priority = :routing_priority")
                params["routing_priority"] = updates["routing_priority"]
            
            set_clauses.append("updated_at = :updated_at")
            params["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            query = f"""
                UPDATE ai_provider_configs
                SET {', '.join(set_clauses)}
                WHERE id = :id
            """
            
            db.execute(text(query), params)
            db.commit()
            
            # Update cache
            if provider_id in self._providers:
                for key, value in updates.items():
                    if hasattr(self._providers[provider_id], key):
                        setattr(self._providers[provider_id], key, value)
            
            return True
        finally:
            db.close()
    
    def delete(self, provider_id: str) -> bool:
        """Remove provider configuration."""
        if provider_id not in self._providers:
            return False
        
        db = self._get_db_session()
        try:
            db.execute(text(
                "DELETE FROM ai_provider_configs WHERE id = :id"
            ), {"id": provider_id})
            db.commit()
            
            del self._providers[provider_id]
            return True
        finally:
            db.close()
    
    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get provider by ID."""
        if not self._loaded:
            self.load_from_db()
        
        return self._providers.get(provider_id)
    
    def list_providers(self, enabled_only: bool = True) -> List[ProviderConfig]:
        """List all providers."""
        if not self._loaded:
            self.load_from_db()
        
        providers = list(self._providers.values())
        if enabled_only:
            providers = [p for p in providers if p.enabled]
        
        return sorted(providers, key=lambda p: p.routing_priority)
    
    def get_provider_by_type(self, provider_type: str) -> Optional[ProviderConfig]:
        """Get first provider of given type."""
        if not self._loaded:
            self.load_from_db()
        
        for provider in self._providers.values():
            if provider.provider_type == provider_type and provider.enabled:
                return provider
        return None


# Global registry instance
provider_registry = ProviderRegistry()
