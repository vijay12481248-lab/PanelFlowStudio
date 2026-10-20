-- PanelFlow AI Gateway - Database Migration 003
-- Routing Profiles Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_routing_profiles (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    profile_name TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'BALANCED',
    preferences JSON,
    restrictions JSON,
    budget_limits JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_routing_profiles_project ON ai_routing_profiles(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_routing_profiles_strategy ON ai_routing_profiles(strategy);
