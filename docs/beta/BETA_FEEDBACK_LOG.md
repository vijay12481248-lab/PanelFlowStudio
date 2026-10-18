# PANELFLOW STUDIO — BETA FEEDBACK LOG (EVIDENCE AUDIT EDITION)
**Application**: PanelFlow Studio  
**Target Release**: v1.0.0-beta.2  
**Audit Date**: October 17, 2026  
**Document Status**: Official Provenance & Integrity Record  

---

## 1. EVIDENCE CLASSIFICATION TAXONOMY

In accordance with strict evidence integrity standards, every entry is categorized by its factual source:

- `REAL_EXTERNAL_USER`: Verifiable feedback independently provided by an external human user.
- `USER_PROVIDED`: Data, logs, or issues supplied by an external participant.
- `LOCAL_AUTOMATED_TEST`: Executed by pytest, Playwright, or automated CI scripts on the local host.
- `LOCAL_MANUAL_TEST`: Executed by developer testing interactive desktop UI features locally.
- `SIMULATED_PERSONA`: Synthetic persona scenario modeled to anticipate user friction points.
- `AGENT_INFERRED`: Derived algorithmically or analytically by the engineering agent.
- `UNKNOWN`: Unverified provenance without supporting raw logs.

---

## 2. PROVENANCE AUDIT OF PREVIOUSLY LOGGED ITEMS

| ID | Origin Classification | Description | Original Stage | Severity | Factual Technical Basis | Real External Evidence Status |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **FB-001** | `LOCAL_MANUAL_TEST` | Missing FFmpeg halted final render initiation when testing unconfigured environment. | Render | P1 | Verified via manual test on local machine with FFmpeg removed from PATH. Engine returned 424 Failed Dependency. | **INTERNAL QA ONLY** (Not reported by external user) |
| **FB-002** | `LOCAL_MANUAL_TEST` | Launching with Python < 3.12 triggers version warning in Tauri desktop launcher. | Setup | P2 | Verified in `apps/desktop/src-tauri/src/main.rs` check routine against Python 3.11. | **INTERNAL QA ONLY** (Simulated persona attribution removed) |
| **FB-003** | `AGENT_INFERRED` | Rights Gate modal lacked explicit "Original Author / All Rights Reserved" wording. | Project | P2 | Code review of `NewProjectScreen.tsx` revealed missing explicit original artist license choice. | **INTERNAL CODE REVIEW ONLY** (Simulated quote removed) |
| **FB-004** | `LOCAL_MANUAL_TEST` | Manga reading order requires explicit RTL toggle setting in panelization pipeline. | OCR | P3 | Verified on local 4-koma test images in test suite. | **INTERNAL QA ONLY** (Simulated quote removed) |
| **FB-005** | `LOCAL_MANUAL_TEST` | Motion camera drag sensitivity calibration on high-DPI displays. | Motion | P3 | Verified on local 1440p monitor testing canvas mouse events. | **INTERNAL QA ONLY** (Simulated quote removed) |
| **FB-006** | `LOCAL_AUTOMATED_TEST` | Procedural TTS fallback volume headroom adjustment (-4 dB vs BGM bed). | Audio | P3 | Discovered during automated RMS audio level regression test. | **INTERNAL QA ONLY** (Simulated quote removed) |
| **FB-007** | `AGENT_INFERRED` | Documentation clarification regarding non-admin winget usage in README.txt. | Setup | P3 | Discovered during documentation audit of Windows installation commands. | **INTERNAL DOC REVIEW ONLY** |
| **FB-008** | `LOCAL_MANUAL_TEST` | UI affordance for opening rendered video destination folder in Explorer. | Render | P3 | Tested in desktop webview button click handler. | **INTERNAL QA ONLY** |
| **FB-009** | `AGENT_INFERRED` | Feature request: Multi-aspect ratio batch rendering (16:9 + 9:16 vertical). | Export | P4 | Architectural roadmap consideration. | **INTERNAL ROADMAP ONLY** |
| **FB-010** | `AGENT_INFERRED` | Feature request: One-click publishing/upload to YouTube Studio. | Export | P4 | Architectural roadmap consideration. | **INTERNAL ROADMAP ONLY** |
| **FB-011** | `AGENT_INFERRED` | Feature request: Multi-character voice allocation per speech balloon. | Script | P4 | Architectural roadmap consideration. | **INTERNAL ROADMAP ONLY** |
| **FB-012** | `LOCAL_MANUAL_TEST` | Feature request: Headless command-line batch runner for pipelines. | Runtime | P4 | Developer testing CLI execution options. | **INTERNAL QA ONLY** |
| **FB-013** | `AGENT_INFERRED` | Feature request: 2.5D AI depth map layer separation for parallax motion. | Motion | P4 | Research backlog consideration. | **INTERNAL ROADMAP ONLY** |
| **FB-014** | `AGENT_INFERRED` | Feature request: Motion editor canvas audio waveform scrub visualization. | Audio | P4 | UI backlog consideration. | **INTERNAL ROADMAP ONLY** |

---

## 3. REAL EXTERNAL TESTER FEEDBACK LEDGER

*(This section is strictly reserved for verified, independently submitted external beta tester entries. Currently 0 submissions received.)*

| ID | Tester ID | Date | Version | Category | Severity | Stage | Description | Raw Artifact Ref | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| *None* | — | — | — | — | — | — | *Awaiting external beta tester submissions in `docs/beta/real_testers/`* | — | **PENDING EXTERNAL TESTING** |

---

## 4. INTEGRITY SUMMARY

- **Genuinely Verified External Testers**: **0**
- **Simulated Personas**: **8** (T-01 to T-08 reclassified from "external users" to synthetic model archetypes)
- **Fabricated Quotes Removed**: **14** (All invented quotes stripped from the record)
- **Fabricated Hardware Profiles Removed**: **8** (All non-local hardware claims stripped from external validation)
- **Internal Technical Fixes Preserved**: 8 legitimate bug fixes and UX improvements discovered during local developer and automated testing remain active in v1.0.0-beta.2.
