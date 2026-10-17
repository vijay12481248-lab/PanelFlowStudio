# PanelFlow Studio — Extraction Strategies Specification

This document details the responsibilities, inputs, heuristics, and outputs of each extraction strategy in the extraction ladder.

---

## 1. `DIRECT_DOCUMENT` (Stage 1)
- **Cost**: Extremely low (0 ms overhead)
- **Target**: URLs ending in `.jpg`, `.jpeg`, `.png`, `.webp`, `.avif`, `.gif` or returning direct image MIME types.
- **Behavior**: Emits a 1-page `ChapterManifest` immediately without HTML parsing or browser initialization.
- **Archive Detection**: Flags `.cbz`, `.zip`, `.cbr` archives for handoff to the archive ingestion pipeline.

---

## 2. `STATIC_DOM` (Stage 2)
- **Cost**: Low (Fast HTTP GET + BeautifulSoup parsing)
- **Target**: Static HTML delivered by the web server.
- **Behavior**:
  - Traverses `img.src`, `img.srcset`, and `<picture>` tags.
  - Normalizes relative and protocol-relative URLs (`//example.com/...`).
  - Preserves DOM order, DOM path, and attributes.
  - Scores candidates using `CandidateScorer` and groups them via `CandidateClusterer`.

---

## 3. `READER_CONTAINER` (Stage 3)
- **Cost**: Low (DOM Tree analysis)
- **Target**: Semantic reader container elements (`div`, `article`, `main`, `section`).
- **Behavior**:
  - Evaluates image density, image-to-text ratio, sibling repetition, and container class hints (`.chapter-content`, `.reader-container`).
  - Restricts candidate extraction strictly within the dominant container.
  - Filters out extraneous images in headers, footers, sidebars, and comments.

---

## 4. `LAZY_IMAGES` (Stage 4)
- **Cost**: Low (Attribute inspection)
- **Target**: Dynamic image elements with deferred loading attributes.
- **Behavior**:
  - Inspects `data-src`, `data-lazy-src`, `data-original`, `data-url`, `data-image`, `data-file`, etc.
  - Replaces dummy placeholders (`loading.gif`, `pixel.gif`, `blank.png`) with the high-resolution target.
  - Captures the relationship between placeholder URL and resolved content URL.

---

## 5. `EMBEDDED_JSON` (Stage 7)
- **Cost**: Low (JSON parsing, zero JS execution)
- **Target**: Structured data delivered with the page.
- **Behavior**:
  - Inspects `<script type="application/json">`, `<script type="application/ld+json">`.
  - Parses Next.js `__NEXT_DATA__` and Nuxt `__NUXT__` hydration blobs.
  - Safely extracts page arrays (`pages[]`, `images[]`, `chapter.pages`, `slides[]`) without executing downloaded JavaScript code.

---

## 6. `API_MANIFEST` (Stage 8)
- **Cost**: Moderate (Targeted JSON API query)
- **Target**: Public or documented chapter manifest endpoints referenced in page scripts or configuration.
- **Behavior**:
  - Discovers manifest URLs referenced in document `<link>` or `<script>` tags.
  - Queries the safe endpoint and parses the declared page array.
  - Never scans dictionary endpoints or brute-forces hidden URLs.

---

## 7. `RENDERED_DOM` (Stage 9 & 10)
- **Cost**: High (Headless Chromium instance via Playwright)
- **Target**: Dynamic single-page applications (SPAs) and heavy client-side readers.
- **Behavior**:
  - Launches headless Chromium and navigates to the authorized chapter URL.
  - Waits for DOM stabilization.
  - Executes controlled progressive scrolling (viewport increments of 800px) to trigger scroll-based lazy loading.
  - Evaluates `img.currentSrc`, `naturalWidth`, `naturalHeight`, and bounding client rects.

---

## 8. `BROWSER_NETWORK` (Stage 11)
- **Cost**: High (Concurrent with browser rendering)
- **Target**: Images and manifests requested over the network as the user scrolls.
- **Behavior**:
  - Listens to HTTP responses naturally emitted during browser execution.
  - Captures `image/*` MIME type responses and chapter API payloads.
  - Gathers resources that were rendered via canvas or CSS background rather than standard DOM image tags.

---

## 9. `RESOURCE_TIMING` (Stage 12)
- **Cost**: Low (In-browser Performance API query)
- **Target**: `performance.getEntriesByType("resource")`
- **Behavior**:
  - Supplements the network observer by inspecting browser performance resource timings.
  - Discovers resources initiated by `img`, `fetch`, or `xmlhttprequest`.

---

## 10. `RENDERED_CAPTURE` (Stage 13)
- **Cost**: High (Canvas rasterization)
- **Target**: Visible content displayed through `<canvas>` or custom client-side WebGL engines without accessible raw image URLs.
- **Behavior**:
  - Rasterizes visible reader canvas elements into high-resolution PNG data.
  - Explicitly flags all pages with `source_quality = RENDERED_CAPTURE`.
  - Never attempts to reverse-engineer DRM or decrypt protected memory; only captures what is already visibly rendered for the authorized user.
