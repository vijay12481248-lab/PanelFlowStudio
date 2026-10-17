# PanelFlow Studio — End-to-End User Workflow Guide

A step-by-step walkthrough for creating a motion comic presentation from raw comic pages using the PanelFlow Studio desktop application.

---

## Workflow Steps

### 1. New Project & Source Ingestion
1. Launch **PanelFlow Studio**.
2. Click **New Project**.
3. Choose your source type: **Local Folder**, **ZIP Archive**, or **Authorized URL**.
4. Select your source folder containing comic pages (PNG / JPG / WEBP).
5. Review the **Rights Status** declaration and select your authorization basis (e.g. `User Owned`, `Public Domain`, `Licensed`).
6. Click **Create Project**.

### 2. Page Review & Normalization
1. Inspect the extracted pages in the gallery view.
2. Verify reading direction (Left-to-Right, Right-to-Left, or Vertical Webtoon).
3. Click **Proceed to Panels**.

### 3. Panel Review
1. PanelFlow automatically segments comic panels and establishes the reading flow.
2. Inspect panel bounding boxes on each page.
3. Click **Proceed to OCR**.

### 4. OCR & Transcript Review
1. Text balloons are detected and transcribed.
2. Inspect dialogue regions; edit any misheard words or speech bubble boundaries.
3. Click **Approve OCR** → **Proceed to Story**.

### 5. Story & Narrative Review
1. The Story Director identifies speaking characters and scene transitions.
2. Verify character names and assign recurring characters across chapters.
3. Click **Approve Story** → **Proceed to Script**.

### 6. Script Adaptation
1. Choose an adaptation profile: **Faithful**, **Condensed**, **Dramatic Narration**, or **Accessible Recap**.
2. Click **Generate Script** to create timed spoken dialogue segments.
3. Click **Approve Script** → **Proceed to Audio**.

### 7. Audio Director
1. Click **Generate Master Audio** to synthesize speech via local F5-TTS neural voices and align the ACE-Step musical score.
2. Listen to individual lines via the embedded audio preview.
3. Use **Regenerate** on any specific line to create an alternate take without touching other dialogue files.
4. Click **Approve Audio** → **Proceed to Motion**.

### 8. Motion Director
1. Select a cinematic motion style preset (**Cinematic**, **Action Dynamic**, **Slow Burn**, **Minimal**, **Webtoon Scroll**).
2. Click **Plan Shots** to calculate camera zooms, pans, and focus trajectories.
3. Click **Approve Motion** → **Proceed to Render**.

### 9. Production Render
1. Choose your output resolution (**Production 1080p**, **Vertical Shorts**, or **Draft 720p**).
2. Set music volume and dialogue gain if desired.
3. Click **Start Render**.
4. Watch real-time encoding progress and frame counter.
5. When complete, play the video directly in the app, or click **Open Video File** to view in your system media player.
