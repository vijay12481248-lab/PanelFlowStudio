-- PanelFlow AI Gateway - Database Migration 001
-- Provider Configurations Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_provider_configs (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    auth_type TEXT DEFAULT 'api_key',
    credential_ref TEXT,
    endpoint_url TEXT,
    settings JSON,
    privacy_options JSON,
    routing_priority INTEGER DEFAULT 100,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_provider_configs_enabled ON ai_provider_configs(enabled);
CREATE INDEX IF NOT EXISTS idx_ai_provider_configs_type ON ai_provider_configs(provider_type);
