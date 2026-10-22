# Story Service Gateway Integration

## Command
Use when integrating the Universal AI Gateway into story service workflows. <one-line behavior>

## Behavior
The `StoryService` (`engine/story/service.py`) has been updated to route all LLM requests through the Universal AI Gateway, providing:
- Provider-agnostic capability routing
- Automatic fallback on failures
- Circuit breaker protection
- Rate limit enforcement
- Budget enforcement
- Audit logging of all attempts

### Integrated Workflows
1. **Character Discovery** (`discover_characters`) - Uses gateway for structured character identification from panel text
2. **Event Extraction** (`extract_events`) - Uses gateway for event/incident extraction from panel text
3. **Scene Segmentation** (`segment_scenes`) - Uses gateway for scene boundary detection and scene labeling
4. **Narration Generation** (`generate_narration`) - Uses gateway for coherent narration generation
5. **Dialogue Generation** (`generate_dialogue`) - Uses gateway for character-appropriate dialogue
6. **Continuity Checking** (`check_continuity`) - Uses gateway for narrative continuity analysis

### Gateway Execution Flow
All story service AI requests flow through `_execute_gateway_request()` which:
1. Builds a `NormalizedRequest` with the appropriate capability, prompt, and context
2. Executes via `adapter_factory.execute_request()` which handles:
   - Strategy selection (via `RoutingEngine`)
   - Circuit breaker protection
   - Rate limit checking
   - Fallback coordination
   - Budget enforcement
   - Attempt history recording
3. Returns the validated result or raises an appropriate error

### Backward Compatibility
The original `llm_registry`-based methods (`_resolve_pinned_provider`, `resolve_script_provider_identity`, `resolve_pinned_script_provider`) are **preserved** for backward compatibility:
- The original persisted provider IDs are still respected
- Existing workflows using the legacy methods continue to function
- New code should use the gateway integration for new workflows

### Example Usage
```python
# New way - through gateway
result = await story_service.discover_characters(
    panels_text=panel_texts,
    project_id=project_id,
    job_id=job_id,
)

# Legacy way - still works
provider = await story_service._resolve_pinned_provider(provider_id)
```

## Integration Points
- **ProviderRegistry** - Enabled providers, routing priorities, credentials
- **ModelRegistry** - Capability indexing, free_tier flags, pricing
- **AdapterFactory** - Instantiates correct adapter per provider
- **CircuitBreaker** - Per-provider failure isolation
- **RateLimiter** - Per-constraint rate tracking
- **BudgetEnforcer** - Free-first policy and spending limits