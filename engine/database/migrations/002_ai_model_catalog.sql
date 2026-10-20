-- PanelFlow AI Gateway - Database Migration 002
-- Model Catalog Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_model_catalog (
    id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL,
    provider_model_id TEXT NOT NULL,
    display_name TEXT,
    capabilities JSON,
    modalities_in JSON,
    modalities_out JSON,
    context_window INTEGER,
    output_limit INTEGER,
    supports_streaming BOOLEAN DEFAULT TRUE,
    supports_structured BOOLEAN DEFAULT TRUE,
    supports_tools BOOLEAN DEFAULT FALSE,
    supports_vision BOOLEAN DEFAULT FALSE,
    pricing_input_per_million DECIMAL(10, 6),
    pricing_output_per_million DECIMAL(10, 6),
    free_tier BOOLEAN DEFAULT FALSE,
    commercial_use BOOLEAN DEFAULT TRUE,
    privacy_retention TEXT DEFAULT 'standard',
    health_status TEXT DEFAULT 'HEALTHY',
    last_verified DATETIME,
    extra JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_model_catalog_provider ON ai_model_catalog(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_ai_model_catalog_provider_model ON ai_model_catalog(provider_config_id, provider_model_id);
CREATE INDEX IF NOT EXISTS idx_ai_model_catalog_capability ON ai_model_catalog(capabilities);
