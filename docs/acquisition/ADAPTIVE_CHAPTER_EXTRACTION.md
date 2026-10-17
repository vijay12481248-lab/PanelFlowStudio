# PanelFlow Studio — Adaptive Resilient Chapter Extraction Engine

## 1. Vision & Architecture

The **Adaptive Resilient Chapter Extraction Engine** is a local-first, multi-strategy discovery and evidence-fusion subsystem designed to convert arbitrary authorized web comic, manga, manhwa, manhua, and webtoon chapters into structured `ChapterManifest`s.

The engine strictly rejects site-specific hardcoding in favor of **generic structural discovery**, **explainable candidate scoring**, **multi-source evidence fusion**, and **self-healing reader recipes**.

---

## 2. Extraction Ladder (Cost & Execution Order)

The engine traverses strategies in strict order from **cheapest (HTTP static)** to **most expensive (headless browser / canvas capture)**, exiting as early as high confidence and completeness thresholds are satisfied:

```mermaid
flowchart TD
    Start["URL Input"] --> S0["Stage 0: SSRF & Safety Guard"]
    S0 -->|Unsafe/Localhost| ErrSSRF["INVALID_URL / ACCESS_RESTRICTED"]
    S0 --> S0Classify["Stage 0: URL & Page Classifier"]
    S0Classify -->|Login Page| ErrAuth["AUTHENTICATION_REQUIRED"]
    S0Classify -->|Series/TOC| ErrTOC["NOT_A_CHAPTER"]
    S0Classify --> S1["Stage 1: Direct Document Strategy"]
    
    S1 -->|Direct Image| DoneDirect["EXTRACTED (Single Page)"]
    S1 --> RecipeCheck{"Recipe in Store?"}
    
    RecipeCheck -->|Yes| FastPath["Recipe Fast-Path"]
    FastPath -->|Valid| DoneFast["EXTRACTED (Recipe)"]
    FastPath -->|Stale/Changed| StaleHeal["Invalidate Stale Recipe & Fallback"]
    
    RecipeCheck -->|No| GenericLadder["Generic Discovery Cascade"]
    StaleHeal --> GenericLadder
    
    GenericLadder --> S2["Stage 2: Static DOM Strategy"]
    S2 --> S3["Stage 3: Reader Container Strategy"]
    S3 --> S4["Stage 4: Lazy Images Strategy"]
    S4 --> Fusion1["Global Candidate Pool Fusion"]
    
    Fusion1 -->|Conf >= 0.90 & Comp >= 0.85| DoneStatic["EXTRACTED (Static HTML Fusion)"]
    Fusion1 --> S7["Stage 7: Embedded JSON & Hydration Manifest"]
    
    S7 --> Fusion2["Evidence Fusion"]
    Fusion2 -->|Conf >= 0.90 & Comp >= 0.85| DoneJSON["EXTRACTED (Embedded JSON)"]
    Fusion2 --> S8["Stage 8: Public API Manifest Strategy"]
    
    S8 --> Fusion3["Evidence Fusion"]
    Fusion3 -->|Conf >= 0.90| DoneAPI["EXTRACTED (API Manifest)"]
    Fusion3 --> S9["Stage 9-10: Rendered DOM (Playwright Progressive Scroll)"]
    
    S9 --> S11["Stage 11: Browser Network Observation"]
    S11 --> S12["Stage 12: Performance Resource Timing"]
    S12 --> Fusion4["Browser & Network Fusion"]
    
    Fusion4 -->|Conf >= 0.75| DoneBrowser["EXTRACTED (Rendered & Network Fusion)"]
    Fusion4 --> S13["Stage 13: Rendered Capture (Canvas Fallback)"]
    
    S13 -->|Canvas Elements Present| DoneCapture["EXTRACTED (RENDERED_CAPTURE)"]
    S13 --> TeachMode{"Candidates Exist?"}
    
    TeachMode -->|Yes| NeedsReview["NEEDS_REVIEW (Teach Mode Selection)"]
    TeachMode -->|No| ErrFail["NO_CONTENT_IMAGES / UNSUPPORTED_READER"]
```

---

## 3. Core Architectural Subsystems

1. **`GlobalCandidatePool`**: Unifies observations of candidates across Static DOM, Rendered DOM, Network events, and Resource Timings. Prevents duplicate extraction while amplifying multi-source confidence.
2. **`CandidateClusterer`**: Organizes image candidates by CDN host, URL path parent, and DOM container. Discovers the dominant chapter cluster while filtering thumbnails, sidebar covers, and user avatars.
3. **`CandidateScorer`**: Evaluates individual candidates with explainable positive (large dimensions, comic aspect ratios, reader container, dominant cluster) and negative (thumbnails, ads, navigation, micro-dimensions) signals.
4. **`SequenceResolver`**: Enforces deterministic natural numeric ordering (e.g. `1, 2, ..., 9, 10, 11`), preventing alphabetical sort anomalies (`1, 10, 11, 2`).
5. **`ChapterValidator` & `ImageProbe`**: Verifies magic bytes (`\xff\xd8\xff`, `\x89PNG`, `RIFF...WEBP`), rejects HTML error pages masquerading as images, guards against decompression bombs, and calculates cryptographic SHA-256 hashes.
6. **`ResumableChapterDownloader`**: Supports bounded concurrency, domain rate-limiting, and resume functionality. Skips already-downloaded valid files upon application restart.
