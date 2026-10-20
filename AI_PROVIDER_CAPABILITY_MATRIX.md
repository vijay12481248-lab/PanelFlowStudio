# AI Provider Capability Matrix

**Document version:** 1.0  
**Date:** 2026-10-20  
**Scope:** Provider and model capability mapping for Universal AI Gateway

## 1. Capability Definitions

### 1.1 Core Capability Categories

| Capability ID | Description | Input Modalities | Output Modalities | Example Use Cases |
|--------------|-------------|------------------|-------------------|-------------------|
| text.generate | General text generation | text | text | Narration, descriptions |
| text.reason | Complex reasoning | text | text | Story analysis, continuity |
| text.structured | JSON/schema output | text | structured | Panel data extraction |
| text.translate | Language translation | text | text | Localization |
| text.summarize | Text summarization | text | text | Chapter summaries |
| vision.understand | Image understanding | image | text | Panel descriptions |
| vision.ocr_assist | OCR enhancement | image + text | text | Text correction |
| vision.panel_analysis | Comic panel analysis | image | structured | Panel detection, reading order |
| vision.continuity_check | Visual continuity | image[] | text | Character consistency |
| audio.transcribe | Speech to text | audio | text | Dialogue extraction |
| audio.synthesize | Text to speech | text | audio | Narration generation |
| audio.analyze | Audio analysis | audio | text | Emotion detection |
| music.generate | Music composition | text | audio | Background scores |
| image.generate | Image generation | text | image | Concept art |
| image.edit | Image editing | image + text | image | Panel modifications |
| video.generate | Video generation | text/image | video | Motion sequences |
| embeddings.generate | Vector embeddings | text/image | vector | Similarity search |

### 1.2 Capability Dimensions

| Dimension | Options | Description |
|-----------|---------|-------------|
| streaming | yes/no | Supports real-time token streaming |
| tool_calling | yes/no | Supports function calling/tools |
| long_context | tokens | Maximum context window |
| batch | yes/no | Supports batch processing |
| structured | yes/no | Native structured output support |
| multimodal | yes/no | Handles multiple input types |

## 2. Provider Capability Matrix

### 2.1 Ollama (Local)

**Provider ID:** `ollama`  
**Deployment:** Local/Private remote  
**Authentication:** Token optional, IP allowlist for remote

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | qwen3.5:9b, qwen3.6:latest | Good general purpose |
| text.reason | ✅ | qwen3-coder:30b, qwen3.5:9b | Strong reasoning |
| text.structured | ✅ | All models | JSON format support |
| text.translate | ✅ | qwen3.5:9b | Decent translation |
| text.summarize | ✅ | qwen3.5:9b | Works well |
| vision.understand | ✅ | qwen3.5:9b, gemma4:latest | Vision models available |
| vision.ocr_assist | ✅ | qwen3.5:9b | Requires vision model |
| vision.panel_analysis | ✅ | qwen3.5:9b | Good for panels |
| vision.continuity_check | ✅ | qwen3.5:9b | Visual comparison |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ❌ | N/A | Not supported |
| image.edit | ❌ | N/A | Not supported |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ❌ | N/A | Not supported |

**Context Windows:**
- qwen3.5:9b: 32K tokens
- qwen3.6:latest: 32K tokens
- qwen3-coder:30b: 32K tokens

**Pricing:**
- Free (local compute)
- VRAM requirements vary by model

**Limitations:**
- Local compute only
- Model availability depends on user installation
- No audio/video capabilities

**Best For:**
- Privacy-sensitive projects
- Offline work
- Low-cost operation
- Full control over models

---

### 2.2 OpenAI API

**Provider ID:** `openai`  
**Deployment:** Cloud  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | gpt-4o, gpt-4-turbo | Excellent quality |
| text.reason | ✅ | gpt-4o, o1-preview | Strong reasoning |
| text.structured | ✅ | All models | Native structured output |
| text.translate | ✅ | gpt-4o | High quality |
| text.summarize | ✅ | gpt-4o | Excellent |
| vision.understand | ✅ | gpt-4o, gpt-4-vision | State-of-art |
| vision.ocr_assist | ✅ | gpt-4o | Excellent OCR |
| vision.panel_analysis | ✅ | gpt-4o | Very good |
| vision.continuity_check | ✅ | gpt-4o | Strong |
| audio.transcribe | ✅ | whisper-1 | Excellent transcription |
| audio.synthesize | ✅ | tts-1, tts-1-hd | High quality |
| audio.analyze | ❌ | N/A | Limited |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ✅ | dall-e-3 | High quality |
| image.edit | ✅ | dall-e-3 | Good editing |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ✅ | text-embedding-3-large | Excellent embeddings |

**Context Windows:**
- gpt-4o: 128K tokens
- gpt-4-turbo: 128K tokens
- o1-preview: 128K tokens

**Pricing (approximate):**
- gpt-4o: $2.50/$10 per M tokens
- gpt-4-turbo: $10/$30 per M tokens
- dall-e-3: $0.04-0.12 per image
- whisper: $0.006 per minute

**Limitations:**
- Requires API key
- Cost can escalate quickly
- Data privacy concerns
- Rate limits

**Best For:**
- High-quality outputs
- Complex reasoning
- When quality outweighs cost
- Production workflows

---

### 2.3 Anthropic Claude

**Provider ID:** `anthropic`  
**Deployment:** Cloud  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | claude-3-5-sonnet, opus | Excellent quality |
| text.reason | ✅ | claude-3-5-sonnet, opus | Strong reasoning |
| text.structured | ✅ | All models | Good support |
| text.translate | ✅ | claude-3-5-sonnet | Very good |
| text.summarize | ✅ | claude-3-5-sonnet | Excellent |
| vision.understand | ✅ | claude-3-5-sonnet | Strong vision |
| vision.ocr_assist | ✅ | claude-3-5-sonnet | Good OCR |
| vision.panel_analysis | ✅ | claude-3-5-sonnet | Very good |
| vision.continuity_check | ✅ | claude-3-5-sonnet | Strong |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ❌ | N/A | Not supported |
| image.edit | ❌ | N/A | Not supported |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ✅ | claude-3-5-sonnet | Via text |

**Context Windows:**
- claude-3-5-sonnet: 200K tokens
- claude-3-opus: 200K tokens

**Pricing (approximate):**
- claude-3-5-sonnet: $3/$15 per M tokens
- claude-3-opus: $15/$75 per M tokens

**Limitations:**
- No audio/image generation
- Cost
- Data privacy

**Best For:**
- Long context documents
- Complex reasoning
- Safety-conscious use
- Conversational tasks

---

### 2.4 Google Gemini

**Provider ID:** `gemini`  
**Deployment:** Cloud  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | gemini-1.5-pro, flash | Good quality |
| text.reason | ✅ | gemini-1.5-pro | Strong reasoning |
| text.structured | ✅ | gemini-1.5-pro | Good support |
| text.translate | ✅ | gemini-1.5-pro | Very good |
| text.summarize | ✅ | gemini-1.5-pro | Excellent |
| vision.understand | ✅ | gemini-1.5-pro | **Excellent** |
| vision.ocr_assist | ✅ | gemini-1.5-pro | **Excellent** |
| vision.panel_analysis | ✅ | gemini-1.5-pro | **Excellent** |
| vision.continuity_check | ✅ | gemini-1.5-pro | Very good |
| audio.transcribe | ✅ | gemini-1.5-pro | Good |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ✅ | gemini-1.5-pro | Basic |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ✅ | imagen-3 | Good quality |
| image.edit | ❌ | N/A | Limited |
| video.generate | ❌ | N/A | Not supported (veo in preview) |
| embeddings.generate | ✅ | text-embedding-004 | Good |

**Context Windows:**
- gemini-1.5-pro: 1M tokens
- gemini-1.5-flash: 1M tokens

**Pricing (approximate):**
- gemini-1.5-pro: $3.50/$10.50 per M tokens
- gemini-1.5-flash: $0.35/$1.05 per M tokens

**Limitations:**
- Cost
- Data privacy
- Rate limits

**Best For:**
- Very long context
- Vision-heavy tasks
- OCR
- Cost-effective high volume

---

### 2.5 Groq

**Provider ID:** `groq`  
**Deployment:** Cloud  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | llama-3.1-70b, mixtral | Good quality |
| text.reason | ✅ | llama-3.1-70b | Decent |
| text.structured | ✅ | llama-3.1-70b | Good |
| text.translate | ✅ | llama-3.1-70b | Good |
| text.summarize | ✅ | llama-3.1-70b | Good |
| vision.understand | ❌ | N/A | No vision |
| vision.ocr_assist | ❌ | N/A | No vision |
| vision.panel_analysis | ❌ | N/A | No vision |
| vision.continuity_check | ❌ | N/A | No vision |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ❌ | N/A | Not supported |
| image.edit | ❌ | N/A | Not supported |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ❌ | N/A | Not supported |

**Context Windows:**
- llama-3.1-70b: 131K tokens

**Pricing (approximate):**
- llama-3.1-70b: $0.59/$0.79 per M tokens
- mixtral-8x7b: $0.24/$0.24 per M tokens

**Limitations:**
- No vision
- No multimodal
- Text only

**Best For:**
- Fast text generation
- Low cost
- High throughput
- Text-only workflows

---

### 2.6 OpenRouter

**Provider ID:** `openrouter`  
**Deployment:** Cloud (aggregator)  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | 100+ models | Aggregator |
| text.reason | ✅ | 100+ models | Aggregator |
| text.structured | ✅ | Most models | Aggregator |
| text.translate | ✅ | 100+ models | Aggregator |
| text.summarize | ✅ | 100+ models | Aggregator |
| vision.understand | ✅ | Many models | Aggregator |
| vision.ocr_assist | ✅ | Many models | Aggregator |
| vision.panel_analysis | ✅ | Many models | Aggregator |
| vision.continuity_check | ✅ | Many models | Aggregator |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ❌ | N/A | Not supported |
| image.edit | ❌ | N/A | Not supported |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ✅ | Many models | Aggregator |

**Context Windows:**
- Varies by model (8K-200K+)

**Pricing:**
- Aggregated pricing
- Pay for what you use
- Often discounted vs direct

**Limitations:**
- Aggregator complexity
- Model availability varies
- Data privacy (via aggregator)

**Best For:**
- Testing multiple models
- Fallback routing
- Cost optimization
- Model flexibility

---

### 2.7 Cloudflare Workers AI

**Provider ID:** `cloudflare`  
**Deployment:** Cloud (edge)  
**Authentication:** API token

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | Llama 3.1, Mistral | Good |
| text.reason | ✅ | Llama 3.1 70B | Decent |
| text.structured | ✅ | Most models | Good |
| text.translate | ✅ | Llama 3.1 70B | Good |
| text.summarize | ✅ | Llama 3.1 70B | Good |
| vision.understand | ✅ | Llama 3.2 Vision | Basic |
| vision.ocr_assist | ✅ | Llama 3.2 Vision | Basic |
| vision.panel_analysis | ⚠️ | Llama 3.2 Vision | Limited |
| vision.continuity_check | ⚠️ | Llama 3.2 Vision | Limited |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ✅ | Stable Diffusion XL | Good |
| image.edit | ⚠️ | Stable Diffusion XL | Limited |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ✅ | Various | Good |

**Context Windows:**
- Llama 3.1 70B: 128K tokens

**Pricing:**
- Pay per token
- Often lower latency
- Free tier available

**Limitations:**
- Limited model selection
- Vision capabilities basic
- Edge deployment constraints

**Best For:**
- Low latency
- Edge deployment
- Cost-effective
- Image generation

---

### 2.8 Mistral

**Provider ID:** `mistral`  
**Deployment:** Cloud  
**Authentication:** API key

| Capability | Support | Models | Notes |
|------------|---------|--------|-------|
| text.generate | ✅ | Mistral Large, Medium | Good |
| text.reason | ✅ | Mistral Large | Strong |
| text.structured | ✅ | Mistral Large | Good |
| text.translate | ✅ | Mistral Large | Good |
| text.summarize | ✅ | Mistral Large | Good |
| vision.understand | ✅ | Pixtral 12B | Good |
| vision.ocr_assist | ✅ | Pixtral 12B | Good |
| vision.panel_analysis | ✅ | Pixtral 12B | Good |
| vision.continuity_check | ✅ | Pixtral 12B | Decent |
| audio.transcribe | ❌ | N/A | Not supported |
| audio.synthesize | ❌ | N/A | Not supported |
| audio.analyze | ❌ | N/A | Not supported |
| music.generate | ❌ | N/A | Not supported |
| image.generate | ❌ | N/A | Not supported |
| image.edit | ❌ | N/A | Not supported |
| video.generate | ❌ | N/A | Not supported |
| embeddings.generate | ✅ | Mistral Embed | Good |

**Context Windows:**
- Mistral Large: 32K tokens
- Pixtral 12B: 128K tokens

**Pricing (approximate):**
- Mistral Large: $8/$24 per M tokens
- Mistral Medium: $2.5/$7.5 per M tokens

**Limitations:**
- Cost
- Data privacy
- Limited audio/image

**Best For:**
- European providers
- GDPR compliance
- Vision tasks
- Text generation

## 3. Model-Specific Capabilities

### 3.1 Vision Model Comparison

| Model | OCR Quality | Panel Analysis | Continuity | Context | Speed |
|-------|-------------|----------------|------------|---------|-------|
| gemini-1.5-pro | ★★★★★ | ★★★★★ | ★★★★☆ | 1M | Medium |
| gpt-4o | ★★★★★ | ★★★★★ | ★★★★★ | 128K | Medium |
| claude-3-5-sonnet | ★★★★☆ | ★★★★☆ | ★★★★☆ | 200K | Medium |
| qwen3.5:9b (local) | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | 32K | Fast |
| pixtral-12b | ★★★★☆ | ★★★★☆ | ★★★☆☆ | 128K | Fast |

### 3.2 Text Generation Quality

| Model | Reasoning | Creativity | Speed | Cost | Context |
|-------|-----------|------------|-------|------|---------|
| gpt-4o | ★★★★★ | ★★★★★ | Medium | $$$$ | 128K |
| claude-3-5-sonnet | ★★★★★ | ★★★★★ | Medium | $$$ | 200K |
| gemini-1.5-pro | ★★★★☆ | ★★★★☆ | Medium | $$ | 1M |
| qwen3.5:9b (local) | ★★★☆☆ | ★★★☆☆ | Fast | Free | 32K |
| llama-3.1-70b | ★★★☆☆ | ★★★☆☆ | Very Fast | $ | 131K |

### 3.3 Cost Efficiency

| Use Case | Recommended | Why |
|----------|-------------|-----|
| Local privacy | Ollama | Free, private |
| High quality text | Claude 3.5 Sonnet | Best reasoning |
| Long context | Gemini 1.5 Pro | 1M tokens |
| Vision heavy | Gemini 1.5 Pro | Best vision/cost |
| Fast text | Groq Llama 3.1 | Low latency |
| Budget batch | OpenRouter | Aggregated pricing |
| Image generation | DALL-E 3 / Stable Diffusion | Quality options |

## 4. Capability Mapping for PanelFlow Workflows

### 4.1 Story Analysis Workflow

**Required capabilities:**
- `text.reason` (complex)
- `vision.understand` (panel images)
- `text.structured` (output schema)

**Recommended providers:**
1. **Primary:** Gemini 1.5 Pro (long context, good vision)
2. **Fallback:** GPT-4o (best quality)
3. **Local:** qwen3.5:9b (privacy)

### 4.2 Script Generation Workflow

**Required capabilities:**
- `text.generate` (creative)
- `text.reason` (continuity)
- `text.structured` (dialogue schema)

**Recommended providers:**
1. **Primary:** Claude 3.5 Sonnet (narrative quality)
2. **Fallback:** GPT-4o (versatile)
3. **Local:** qwen3.5:9b (privacy)

### 4.3 Panel Analysis Workflow

**Required capabilities:**
- `vision.panel_analysis` (detection)
- `vision.ocr_assist` (text extraction)
- `text.structured` (panel data)

**Recommended providers:**
1. **Primary:** Gemini 1.5 Pro (best vision/cost)
2. **Fallback:** GPT-4o (highest quality)
3. **Local:** qwen3.5:9b (vision capable)

### 4.4 OCR Correction Workflow

**Required capabilities:**
- `vision.ocr_assist` (text enhancement)
- `text.translate` (optional)

**Recommended providers:**
1. **Primary:** Gemini 1.5 Pro (excellent OCR)
2. **Fallback:** GPT-4o (excellent OCR)
3. **Local:** qwen3.5:9b (basic)

### 4.5 Motion Planning Workflow

**Required capabilities:**
- `text.reason` (camera planning)
- `vision.understand` (composition)
- `text.structured` (motion schema)

**Recommended providers:**
1. **Primary:** Claude 3.5 Sonnet (reasoning)
2. **Fallback:** GPT-4o (versatile)
3. **Local:** qwen3.5:9b (reasonable)

## 5. Free Tier Analysis

### 5.1 Free Provider Options

| Provider | Free Tier | Limitations | Commercial Use |
|----------|-----------|-------------|----------------|
| Ollama | Unlimited | Local compute | Yes |
| OpenAI | None (trial only) | No free tier | No |
| Anthropic | None | No free tier | No |
| Google Gemini | Limited | Rate limits | Yes (with limits) |
| Groq | Generous | Rate limits | Yes |
| OpenRouter | Limited | Credits | Yes |
| Cloudflare | Limited | Rate limits | Yes |
| Mistral | Limited | Rate limits | Yes |

### 5.2 Free-Only Workflow Strategy

**Free-tier capable workflows:**
1. **Local Ollama** - All text/vision tasks
2. **Groq** - Fast text generation
3. **Gemini Flash** - Vision and text (limited)
4. **Cloudflare** - Basic text and image

**Paid-required workflows:**
1. High-quality narration (paid TTS)
2. Commercial image generation
3. Advanced video generation
4. Large-scale processing

## 6. Privacy and Compliance

### 6.1 Data Handling

| Provider | Data Retention | Training Use | Commercial Safe |
|----------|----------------|--------------|-----------------|
| Ollama | None (local) | Never | ✅ Yes |
| OpenAI | 30 days | Opt-out | ⚠️ Limited |
| Anthropic | 30 days | Opt-out | ⚠️ Limited |
| Gemini | Varies | Opt-out | ⚠️ Limited |
| Groq | Varies | Unknown | ⚠️ Check |
| OpenRouter | Provider dependent | Varies | ⚠️ Check |
| Cloudflare | Minimized | Opt-out | ✅ Likely |
| Mistral | Varies | Opt-out | ⚠️ Check |

### 6.2 Project Restrictions

**Local-only projects:**
- Must use Ollama
- No cloud providers
- Air-gapped processing

**Privacy-sensitive projects:**
- Ollama preferred
- European providers (Mistral)
- Clear data processing agreements

**Commercial projects:**
- Verify commercial use rights
- Check attribution requirements
- Review licensing terms

## 7. Implementation Recommendations

### 7.1 Provider Priority

**Phase 1 (MVP):**
1. Ollama (existing)
2. OpenAI-compatible (existing)
3. OpenAI (high demand)
4. Anthropic Claude (quality)

**Phase 2:**
5. Google Gemini (vision)
6. Groq (speed/cost)
7. OpenRouter (flexibility)

**Phase 3:**
8. Cloudflare Workers AI
9. Mistral
10. Custom endpoints

### 7.2 Capability Rollout

**Priority 1:** Text generation, reasoning, structured output  
**Priority 2:** Vision understanding, OCR  
**Priority 3:** Audio transcription/synthesis  
**Priority 4:** Embeddings  
**Priority 5:** Image/video generation

## 8. Cost Management

### 8.1 Estimated Costs per 1000 Requests

| Provider | Text (2K tokens) | Vision (1 image) | Monthly Est. |
|----------|------------------|------------------|--------------|
| Ollama | $0 | $0 | $0 |
| OpenAI GPT-4o | $5 | $15 | $500-2000 |
| Claude 3.5 | $6 | $18 | $600-2400 |
| Gemini 1.5 Pro | $3 | $8 | $300-1200 |
| Groq | $0.70 | N/A | $70-300 |
| OpenRouter | $2-10 | $5-20 | $200-1000 |

### 8.2 Cost Optimization Strategies

1. **Route by capability** - Use best cost/performance ratio
2. **Cache responses** - Idempotency keys
3. **Batch requests** - Where supported
4. **Local first** - Ollama for non-critical tasks
5. **Free tier** - Maximize free usage
6. **Model selection** - Right-size models

## Matrix Conclusion

The capability matrix shows Ollama provides a solid foundation for local processing, while cloud providers offer specialized strengths (Gemini for vision, Claude for reasoning, Groq for speed). The Universal AI Gateway should prioritize providers based on workflow requirements, privacy constraints, and cost considerations.
