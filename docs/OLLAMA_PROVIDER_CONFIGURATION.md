# Ollama Provider Configuration & Official REST API Guide

## 1. Overview

PanelFlow Studio connects directly to local or trusted remote instances of [Ollama](https://ollama.ai) via its official REST API. This document details connection configuration, capability detection, SSRF protection, and model recommendation heuristics.

---

## 2. Configuration Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `endpoint_url` | String | `http://127.0.0.1:11434` | Target Ollama REST base URL |
| `is_remote` | Boolean | `false` | True if connecting to an external or cloud server |
| `auth_token` | String (Secret) | `""` | Optional Bearer token or API key for protected endpoints |
| `vision_model` | String | `qwen3.5:9b` | Model assigned to multimodal panel image inspection |
| `reasoning_model`| String | `qwen3.5:9b` | Model assigned to chapter-wide story reasoning |
| `narration_model`| String | `qwen3.5:9b` | Model assigned to original spoken narration writing |
| `concurrency_mode`| Enum | `MANUAL` | `AUTO` (headroom-based) or `MANUAL` |
| `max_gpu_concurrency`| Integer | `1` | Max concurrent Ollama inference requests ($1, 2, \text{or } 4$) |
| `timeout_sec` | Float | `180.0` | HTTP request timeout for large vision/reasoning payloads |
| `context_window`| Integer | `32768` | Input context window token limit (`num_ctx`) |

---

## 3. Official Ollama REST API Integration

PanelFlow utilizes three primary Ollama endpoints:

### A. Model Discovery (`GET /api/tags`)
Lists all models pulled locally or available on the remote server:
```json
{
  "models": [
    {
      "name": "qwen3.5:9b",
      "model": "qwen3.5:9b",
      "size": 6618370538,
      "details": {
        "format": "gguf",
        "family": "qwen35",
        "parameter_size": "9.7B",
        "quantization_level": "Q4_K_M"
      }
    }
  ]
}
```

### B. Deep Capability Inspection (`POST /api/show`)
Querying the model definition allows PanelFlow to inspect **actual architectural capabilities**, rather than guessing from the model name:
```json
// Request: POST /api/show {"name": "qwen3.5:9b"}
// Response excerpts:
{
  "capabilities": ["completion", "vision", "tools", "thinking"],
  "details": {
    "family": "qwen35",
    "families": ["qwen35"],
    "parameter_size": "9.7B"
  },
  "model_info": {
    "general.architecture": "qwen35",
    "qwen35.vision.embedding_length": 1152
  }
}
```
**Capability Rules**:
- `supports_vision`: True if `'vision' in capabilities` OR any key in `model_info` contains `'vision'` or `'clip'` OR family is `'mllama'`, `'qwen2vl'`, or `'qwen35'`.
- `supports_tools`: True if `'tools' in capabilities`.
- `supports_thinking`: True if `'thinking' in capabilities`.

### C. Live Telemetry & VRAM Allocation (`GET /api/ps`)
Returns running models, allocated VRAM bytes, and active contexts:
```json
{
  "models": [
    {
      "name": "qwen3.5:9b",
      "size_vram": 6618370538,
      "context_length": 32768,
      "runner": "llamacpp"
    }
  ]
}
```

---

## 4. Automatic Model Recommendation Logic

When the user clicks **"Refresh Models"** or opens the configuration modal, PanelFlow categorizes installed models:

1. **Vision Role Candidate**:
   - Filter: `supports_vision == True`.
   - Priority 1: Models sized between $7\text{B} - 14\text{B}$ (e.g. `qwen3.5:9b`, `gemma4:latest`). They provide fast panel throughput with excellent visual grounding.
   - Priority 2: Larger vision models (e.g. `qwen3.6:latest`, `qwen-extended:latest`, `36B+`) if GPU VRAM $\ge 16\text{ GB}$.
2. **Story Reasoning Candidate**:
   - Priority 1: `qwen3-coder:30b` or `qwen3.6:latest` (deep reasoning, high logic consistency).
   - Priority 2: `qwen3.5:9b` (solid chapter narrative synthesis).
3. **Narration Writing Candidate**:
   - Priority 1: Fluent conversational models (`qwen3.6:latest`, `qwen3.5:9b`).

---

## 5. Security & SSRF Protection

To prevent Server-Side Request Forgery (SSRF) and malicious LAN scanning:
1. **Scheme Validation**: Only `http://` and `https://` protocols are accepted.
2. **Local vs Remote Classification**:
   - `127.0.0.1` and `localhost` are permitted default local endpoints.
   - If `is_remote` is `true`, requests targeting link-local addresses (`169.254.x.x`), multicast addresses, or loopback aliases other than standard localhost are rejected.
3. **Credential Storage**:
   - Auth tokens are encrypted in local app configuration storage.
   - Tokens are never exposed in frontend console logs, network responses to `GET /api/system/ollama/config`, or project archives.
