# Apply AI Gateway Database Migrations

## Command
Use when applying or rolling back AI Gateway database migrations. <one-line behavior>

## Behavior
Apply versioned SQL migrations to the PanelFlow SQLite database (`panelflow.db`). Migrations are stored in `engine/database/migrations/` and create the following tables:

1. `ai_provider_configs` - Provider configurations with routing priorities
2. `ai_model_catalog` - Discovered models with capabilities and pricing
3. `ai_routing_profiles` - Per-project routing strategies
4. `ai_inference_requests` - Request audit trail
5. `ai_inference_attempts` - Per-attempt tracking (provider, model, cost, latency, error)
6. `ai_provider_health` - Health state monitoring
7. `ai_usage_records` - Usage tracking (requests, tokens, cost)
8. `ai_budget_policies` - Budget policies (global, project, thresholds)

## Migration Runner
Run migrations using `engine/database/migrations/run_ai_migrations.py`:
```bash
cd "C:/Users/Vijaya sekhar/Tools/PanelFlow Studio"
.venv/Scripts/python.exe engine/database/migrations/run_ai_migrations.py
```

The runner:
- Creates the `ai_gateway_migrations` tracking table if missing
- Checks which migrations have already been applied
- Executes pending migration SQL files in sorted order
- Commits each migration as a transaction
- Reports which migrations were applied or skipped

## Migration Files (8 total)
1. `001_ai_provider_configs.sql` - Provider configurations table
2. `002_ai_model_catalog.sql` - Model catalog table
3. `003_ai_routing_profiles.sql` - Routing profiles table
4. `004_ai_inference_requests.sql` - Inference requests table
5. `005_ai_inference_attempts.sql` - Inference attempts table
6. `006_ai_provider_health.sql` - Provider health table
7. `007_ai_usage_records.sql` - Usage records table
8. `008_ai_budget_policies.sql` - Budget policies table

## Verification
After running migrations, verify tables exist:
```bash
.venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('C:/Users/Vijaya sekhar/AppData/Local/PanelFlow Studio/database/panelflow.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ai_%'\")
tables = [row[0] for row in cursor.fetchall()]
print('AI Gateway tables:', tables)
conn.close()
"
```