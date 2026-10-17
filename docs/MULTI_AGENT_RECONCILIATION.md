# Multi-Agent Implementation Reconciliation Report

## 1. Executive Summary

During recent development cycles, multiple autonomous coding agents worked concurrently across overlapping milestones:
- **Stream A (Milestone 1.5 & 2)**: Focused on desktop hardening, page normalization, canonical panel data modeling, classical panel contour detection, reading order sorting, panel review UI (split, merge, drag/resize), and synthetic panel fixtures.
- **Stream B (Milestone 2.5 & 3)**: Focused on packaging, text region detection, pluggable OCR providers (Mock, PaddleOCR, MangaOCR, Vision LLM), deterministic OCR caching, OCR review UI, OCR quality gates, and webtoon stress tests.

This document details the architectural audit, conflict matrix, canonical design choices, and reconciliation actions taken to unite the repository into **ONE coherent canonical implementation**.

---

## 2. Multi-Agent Conflict Matrix

| Subsystem | Stream A Implementation | Stream B Implementation | Canonical Choice | Technical Rationale |
|---|---|---|---|---|
| **Desktop Engine Lifecycle** | Port check on `8765`, spawns `run_engine.py` via `Command::new`, stops child on `RunEvent::Exit`. UI shows reconnect screen. | Relied on manual or external engine launch without child process tracking. | **Stream A Enhanced with Health Validation** | Automatically manages engine lifecycle while validating that port `8765` actually serves PanelFlow Studio before skipping launch or killing processes. |
| **Tauri Packaging** | Multi-resolution icon generation (`.ico`, `.png`), updated `tauri.conf.json`, `cargo check` verified. | Focused on desktop window configurations and build targets. | **Unified Configuration** | Production-ready Tauri 2 setup with Windows resource icons, NSIS/MSI support, and headless compilation support. |
| **Page Normalization** | Non-destructive `source/` vs `normalized/`, EXIF transpose, alpha flattening, sRGB, `NormalizationRecord` table. | Reused normalized derivatives without independent metadata table. | **Stream A Pipeline** | Preserves raw acquisitions with cryptographic immutability and records structured operation logs in `page_normalizations`. |
| **Database Migrations** | Non-destructive `run_sqlite_migrations()` in `session.py` adding missing columns via `ALTER TABLE`. | Direct `Base.metadata.create_all()` assuming clean database. | **Stream A Non-Destructive Migrations** | Ensures Phase 1, Phase 2, and current databases upgrade seamlessly without dropping tables or losing user projects. |
| **Panel Model** | `PanelRecord` with dual coordinates (source pixels + normalized `0.0..1.0`), `PanelType`, `PanelStatus`. | `PanelRecord` extended with direct `ocr_result` relationship. | **Unified Panel Model** | Canonical entity with dual coordinates, `sequence_page`, `sequence_global`, plus relationships to both `TextRegionRecord` and legacy `OCRRecord`. |
| **Panel Detector** | `ContourPanelDetector` in `detector.py` with polarity-aware gutter sampling, morphological closing, and fallback. | `detector.py` with adaptive profile parameters and benchmark harness. | **Stream A Polarity-Aware Contour Detector** | Robustly detects panels on white, black, and colored gutters; achieves 100% precision and recall across synthetic benchmarks. |
| **Webtoon Tiling** | Sliced vertical tiling (3000px chunk, 1200px overlap) with global coordinate projection. | Tested webtoon stress test script (`tools/webtoon_stress_test.py`) up to 30,000px - 60,000px. | **Unified Webtoon Strategy** | Tiled chunking with 1200px overlap prevents panel slicing; passes the 60,000px (86.4 MP) stress test with 100% recall and bounded RAM. |
| **Reading Order** | Internal `_sort_reading_order` in `detector.py` with row clustering. | Dedicated `engine/imaging/panels/ordering.py` with inset placement and `sort_panel_boxes`. | **`engine/imaging/panels/ordering.py` (Separated)** | Separates detection responsibility (candidate generation) from narrative sequencing (reading order engine). |
| **Panel Editing & Review** | Full-featured interactive SVG canvas in `PanelReviewScreen.tsx` (drag, resize, draw, split, merge, undo/redo). | Basic panel review screen. | **Stream A `PanelReviewScreen.tsx`** | Complete visual review canvas with session undo history, split/merge tools, and sequence timeline. |
| **Text Regions** | Did not implement text regions (treated panels as atomic). | `TextRegionRecord` with 3 layers: Layer 1 (Raw OCR), Layer 2 (Corrected Text), Layer 3 (Speaker Attribution). | **Stream B 3-Layer Text Region Architecture** | Establishes the correct hierarchy: Project -> Page -> Panel -> TextRegion -> RawOCR -> CorrectedText. |
| **OCR Architecture** | Mock panel-level OCR with `adapted_blocks` JSON field in `OCRRecord`. | Pluggable `OCREngine` registry (`MockOCREngine`, `PaddleOCREngine`, `MangaOCREngine`, `VisionLLMOCREngine`). | **Unified OCR Engine Architecture** | Pluggable provider registry targeting TextRegions with panel-level fallback for backward compatibility. |
| **OCR Terminology** | Used `adapted_blocks` to describe human corrections of OCR. | Used `corrected_text` for OCR edits; reserved "adaptation" for Story IR. | **Stream B `corrected_text` Terminology** | Eliminates semantic confusion; "adaptation" is strictly reserved for Milestone 4 (Narrative & Story IR). |
| **OCR Caching** | No cache (re-ran OCR on every request). | Deterministic `OCRCacheRecord` (`ocr_cache` table) keyed by `crop_sha256 + engine_id + version + lang + settings`. | **Stream B Deterministic Cache** | Eliminates redundant OCR compute and preserves local battery and CPU. |
| **OCR Approval Semantics** | Directly approved OCR upon extraction. | Two distinct stages: `OCR_COMPLETE` (machine extracted) vs `OCR_APPROVED` (human confirmed). | **Stream B Strict Two-Stage Approval** | Requires explicit user sign-off via `POST /api/projects/{id}/ocr/confirm` before progressing to narrative generation. |
| **Frontend API Types** | Defined types in `packages/shared-types/src/index.ts`. | Extended types in `packages/shared-types` with `TextRegion` and `OCREngineInfo`. | **Unified `@panelflow/shared-types`** | Single canonical TypeScript contract source for all desktop and web UI consumers. |
| **Pipeline Stages** | `NEW -> RIGHTS_APPROVED -> ACQUIRED -> NORMALIZED -> PANELS_DETECTED`. | Extended with `OCR_COMPLETE -> OCR_APPROVED`. | **Unified Pipeline Sequence** | Complete, deterministic stage flow with explicit human gating at `PANELS_DETECTED` and `OCR_APPROVED`. |
| **Benchmark Suite** | 10 synthetic fixtures / 28 ground truth panels in `fixtures/synthetic/`. | 12 synthetic fixtures / 45 ground truth panels in `fixtures/panel_benchmarks/`. | **12-Fixture / 45-Panel Superset** | Establishes ONE canonical benchmark suite covering regular, manga RTL, irregular, insets, splash, borderless, webtoon, and mixed panels. |
| **Test Suite** | 26 unit and integration tests. | Extended to 40 unit and integration tests covering OCR and text regions. | **53 Canonical Tests** | Validates all features across acquisition, normalization, panels, text regions, OCR, and pipeline gating. |

---

## 3. Reconciliation Actions Executed

1. **Separation of Reading Order**: `detector.py` now delegates narrative ordering to `engine.imaging.panels.ordering.sort_panel_boxes()`, maintaining clean separation between candidate geometry detection and reading flow.
2. **Desktop Lifecycle Hardening**: `src-tauri/src/main.rs` probes `/api/system/health` to confirm that an active service is actually PanelFlow Studio before skipping launch, and terminates only the child process owned by this shell.
3. **Database Unification**: Maintained single canonical `models.py` with `ProjectRecord`, `PageRecord`, `NormalizationRecord`, `PanelRecord`, `TextRegionRecord`, `OCRRecord`, `OCRCacheRecord`, and `JobRecord`. Verified non-destructive SQLite column additions for legacy databases.
4. **OCR & Text Region Alignment**: Established `TextRegionRecord` as the primary text container with immutable Layer 1 (`raw_text`), human Layer 2 (`corrected_text`), and Layer 3 (`speaker_character_id` preparation). Retained whole-panel OCR only as a fallback.
5. **Route Deduplication**: Designated canonical routes (e.g. `/panels/confirm`, `/panels/reorder`, `/pages/{page_id}/normalized`) while maintaining deprecated aliases for backward compatibility.
6. **Benchmark Consolidation**: Adopted the 12-fixture / 45-panel suite as the canonical panel detection benchmark, standardizing evaluation across test suites and diagnostic tools.
