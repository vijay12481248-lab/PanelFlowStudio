# PANELFLOW STUDIO — REAL EXTERNAL TESTER EVIDENCE REPOSITORY

**Purpose**: This directory is reserved exclusively for authenticated, independently submitted artifacts from genuine external beta testers.

---

## 1. EVIDENCE SUBMISSION PROTOCOL

For every external tester who runs PanelFlow Studio, create a dedicated folder (`T-001/`, `T-002/`, etc.) containing:

1. **`FORM_SUBMISSION.md`**: Completed copy of [`docs/beta/REAL_BETA_TESTER_FORM.md`](file:///C:/Users/Vijaya%20sekhar/Tools/PanelFlow%20Studio/docs/beta/REAL_BETA_TESTER_FORM.md) signed by or transcribed from the actual user.
2. **`diagnostics.json`**: Real system diagnostics bundle exported directly from PanelFlow Studio (`GET /api/system/diagnostics`).
3. **`panelflow.log`**: Actual application execution log from `%LOCALAPPDATA%\PanelFlow Studio\logs\panelflow.log`.
4. **`rendered_video.mp4`**: The actual video rendered by the tester on their local machine.
5. **`project.json`**: The sanitized project manifest from the tester's project folder.

---

## 2. STRICT INTEGRITY RULES

- **DO NOT** create synthetic, mock, or simulated files in this directory.
- **DO NOT** copy developer machine benchmark runs and label them as external tester runs.
- **DO NOT** fabricate tester quotes, ratings, or hardware specifications.
- Folders must remain empty until an actual external tester provides authentic files.

---

## 3. EXTERNAL BETA GATE CRITERIA

Before PanelFlow Studio can proceed to **Stable v1 Preparation**, this directory must contain verified evidence for:
- Minimum requirement: **At least 3 verified real external testers**
- Production target: **At least 5 verified real external testers**
- Diverse backgrounds: **At least 2 non-programmers / non-technical creators**
