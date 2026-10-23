# Provider Management UI

## Command
Use when configuring or managing AI provider settings through the PanelFlow desktop UI. <one-line behavior>

## Behavior
The `ProviderManagementScreen` (`apps/desktop/src/components/ai-gateway/ProviderManagementScreen.tsx`) provides a complete provider management interface with 6 sections:

### Section: Provider Overview
- Card grid displaying all configured providers
- Status badges (Enabled/Disabled)
- Capability chips (text, vision, etc.)
- Free/paid indicators
- Clickable to view detailed provider configuration

### Section: Add Provider
- Provider type selector (Ollama, OpenAI, Gemini, FreeLLM)
- API key input (masked password field)
- Endpoint URL configuration
- Test connection button
- Provider type description and capabilities

### Section: Model Explorer
- Filterable model table by:
  - Capability (text.generate, vision.understand, etc.)
  - Price tier (free, paid, all)
- Full model metadata display:
  - Context window size
  - Pricing (input/output per 1K tokens)
  - Free-tier status
  - Commercial use status
  - Privacy retention policy
- Filter and search functionality

### Section: Intelligent Routing
- Strategy selection (7 strategies):
  - LOCAL_FIRST, FREE_FIRST, LOWEST_COST, QUALITY_FIRST
  - LOWEST_LATENCY, BALANCED, MANUAL
- Free-only policy toggle
- Budget settings (global monthly, per-project limits)
- Privacy rules configuration
- Real-time routing preview and explanation

### Section: Usage Dashboard
- Request volume chart by provider
- Success/failure rate trends
- Latency monitoring
- Cost analysis and attribution
- Token usage tracking

### Section: Diagnostics
- Routing explanation ("Why this model was selected")
- Why other models were excluded
- Current cooldown state (circuit breaker)
- Error categories (rate limit, transient, auth, unsupported)
- Provider health status

### UI Features
- Dark theme matching PanelFlow design system
- Keyboard navigation and focus states
- Responsive layout for mobile/desktop
- Proper error handling and validation
- No API key exposure in UI
- Real-time health updates from backend

### Navigation
- Accessible via `AI Provider Management` button in the app toolbar
- Screen mode: `ai_provider_management`
- Back navigation to main dashboard
- Conditional rendering based on user role

## Integration with Backend
The UI communicates with the backend via the `AdapterFactory`:
- `adapter_factory.list_providers()` - List registered providers
- `adapter_factory.health_check_all()` - Health check all providers
- `adapter_factory.check_capability(provider_id, capability)` - Check capability support
- `adapter_factory.execute_request(provider_id, request)` - Execute request through gateway

## UI Conventions
- Dark theme colors matching PanelFlow design system
- Proper error and success state management
- Keyboard accessible with proper focus states
- Responsive layout for different screen sizes
- Tooltips and helper text for complex fields
- No API key exposure in UI or logs