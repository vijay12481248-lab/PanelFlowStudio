"""Model registry for cataloging discovered AI models."""

from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import text
from engine.database.session import SessionLocal
from engine.ai_gateway.contracts import ModelInfo, CapabilityType, HealthStatus


class ModelRegistry:
    """Registry for discovered AI models."""
    
    def __init__(self):
        self._models: Dict[str, ModelInfo] = {}
        self._loaded = False
    
    def _get_db_session(self):
        return SessionLocal()
    
    def load_from_db(self) -> None:
        """Load all models from database."""
        if self._loaded:
            return
        
        db = self._get_db_session()
        try:
            result = db.execute(text("""
                SELECT id, provider_config_id, provider_model_id, display_name,
                       capabilities, context_window, output_limit, supports_streaming,
                       supports_structured, supports_tools, supports_vision,
                       pricing_input_per_million, pricing_output_per_million,
                       free_tier, commercial_use, privacy_retention,
                       health_status, last_verified
                FROM ai_model_catalog
            """))
            
            for row in result:
                model = ModelInfo(
                    model_id=row[0],
                    provider_id=row[1],
                    upstream_model_id=row[2],
                    display_name=row[3] or row[2],
                    capabilities=[],  # Would be parsed from JSON
                    modalities_in=["text"],  # Default
                    modalities_out=["text"],  # Default
                    context_window=row[7] or 8192,
                    output_limit=row[8] or 4096,
                    supports_streaming=bool(row[9]),
                    supports_structured=bool(row[10]),
                    supports_tools=bool(row[11]),
                    pricing_input_per_million=Decimal(str(row[14] or 0)),
                    pricing_output_per_million=Decimal(str(row[15] or 0)),
                    free_tier=bool(row[16]),
                    commercial_use=bool(row[17]),
                    health_status=HealthStatus(row[19])
                )
                self._models[model.model_id] = model
            
            self._loaded = True
        finally:
            db.close()
    
    def register_model(self, model: ModelInfo) -> str:
        """Register a model in the catalog."""
        db = self._get_db_session()
        try:
            import json
            db.execute(text("""
                INSERT OR REPLACE INTO ai_model_catalog (
                    id, provider_config_id, provider_model_id, display_name,
                    capabilities, modalities_in, modalities_out,
                    context_window, output_limit, supports_streaming,
                    supports_structured, supports_tools, supports_vision,
                    pricing_input_per_million, pricing_output_per_million,
                    free_tier, commercial_use, privacy_retention,
                    health_status, last_verified, updated_at
                ) VALUES (
                    :id, :provider_config_id, :provider_model_id, :display_name,
                    :capabilities, :modalities_in, :modalities_out,
                    :context_window, :output_limit, :supports_streaming,
                    :supports_structured, :supports_tools, :supports_vision,
                    :pricing_input_per_million, :pricing_output_per_million,
                    :free_tier, :commercial_use, :privacy_retention,
                    :health_status, :last_verified, :updated_at
                )
            """), {
                "id": model.model_id,
                "provider_config_id": model.provider_id,
                "provider_model_id": model.upstream_model_id,
                "display_name": model.display_name,
                "capabilities": json.dumps([c.value for c in model.capabilities]),
                "modalities_in": json.dumps(model.modalities_in),
                "modalities_out": json.dumps(model.modalities_out),
                "context_window": model.context_window,
                "output_limit": model.output_limit,
                "supports_streaming": model.supports_streaming,
                "supports_structured": model.supports_structured,
                "supports_tools": model.supports_tools,
                "supports_vision": model.supports_vision,
                "pricing_input_per_million": float(model.pricing_input_per_million),
                "pricing_output_per_million": float(model.pricing_output_per_million),
                "free_tier": model.free_tier,
                "commercial_use": model.commercial_use,
                "privacy_retention": model.privacy_retention,
                "health_status": model.health_status.value,
                "last_verified": model.last_verified.isoformat() if model.last_verified else None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            db.commit()
            self._models[model.model_id] = model
            return model.model_id
        finally:
            db.close()
    
    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        if not self._loaded:
            self.load_from_db()
        return self._models.get(model_id)
    
    def get_models_by_provider(self, provider_id: str) -> List[ModelInfo]:
        if not self._loaded:
            self.load_from_db()
        return [m for m in self._models.values() if m.provider_id == provider_id]
    
    def get_models_by_capability(
        self, 
        capability: CapabilityType,
        free_only: bool = False
    ) -> List[ModelInfo]:
        if not self._loaded:
            self.load_from_db()
        
        models = []
        for model in self._models.values():
            if capability in model.capabilities:
                if free_only and not model.free_tier:
                    continue
                models.append(model)
        
        return models
    
    def discover_models_for_provider(self, provider_id: str) -> List[ModelInfo]:
        """Discover models from provider API (to be implemented by adapters)."""
        # This is a hook for adapters to populate the catalog
        # Adapter-specific discovery logic goes here
        return []
    
    def update_model_health(self, model_id: str, health: HealthStatus):
        """Update model health status."""
        if model_id not in self._models:
            return False
        
        db = self._get_db_session()
        try:
            db.execute(text("""
                UPDATE ai_model_catalog
                SET health_status = :health_status,
                    last_verified = :last_verified,
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "health_status": health.value,
                "last_verified": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "id": model_id
            })
            db.commit()
            
            self._models[model_id].health_status = health
            return True
        finally:
            db.close()


# Global registry instance
model_registry = ModelRegistry()
