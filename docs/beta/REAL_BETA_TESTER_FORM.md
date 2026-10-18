# PANELFLOW STUDIO — REAL BETA TESTER SUBMISSION FORM
**Version**: PanelFlow Studio v1.0.0-beta.2  
**Instructions**: This form must be completed by or on behalf of an independent external beta tester using their actual hardware and test results. Do not fabricate, simulate, or auto-generate entries.

---

## 1. TESTER & SYSTEM PROFILE

| Field | Value / Response |
| :--- | :--- |
| **Tester ID** | *(Assigned sequentially, e.g., T-001)* |
| **Date of Test** | *(YYYY-MM-DD)* |
| **Tester Name / Handle (Optional)** | |
| **Primary Creator Background** | *(e.g., Comic Artist, Manga Creator, Game Dev, Video Producer, Non-Technical)* |
| **PanelFlow Studio Version** | *(e.g., v1.0.0-beta.2)* |
| **Installer Type Used** | `Setup.exe` (NSIS) / `.msi` (WiX) / `Portable.exe` |
| **Windows OS & Build** | *(e.g., Windows 11 Home 23H2 Build 22631)* |
| **CPU (Processor)** | *(e.g., AMD Ryzen 7 5700X / Intel Core i5-12400)* |
| **System RAM** | *(e.g., 16 GB / 32 GB)* |
| **GPU (Graphics Card & VRAM)** | *(e.g., NVIDIA RTX 3060 12GB / Intel Iris Xe / None)* |

---

## 2. DEPENDENCY & RUNTIME VERIFICATION

| Component | Status | Notes / Errors Observed |
| :--- | :--- | :--- |
| **Installer Execution** | `SUCCESS` / `FAILED` | |
| **Python 3.12+ 64-bit Setup** | `PRE-EXISTING` / `WINGET_SUCCESS` / `FAILED` | |
| **FFmpeg Video Encoder** | `DETECTED` / `WINGET_INSTALLED` / `MISSING` | |
| **Ollama Story Engine** | `CONNECTED` / `OFFLINE_FALLBACK` / `NOT_INSTALLED` | |
| **F5-TTS Neural Voice** | `NEURAL_READY` / `PROCEDURAL_FALLBACK` | |
| **ACE-Step Music Director** | `NEURAL_READY` / `PROCEDURAL_FALLBACK` | |

---

## 3. PIPELINE STAGE CHECKPOINTS

| Stage | Completed? (YES / NO) | Notes / Friction Observed |
| :--- | :---: | :--- |
| **1. Project Creation** | | |
| **2. Rights Declaration Gate** | | *(Selected license type: Original / CC / Public Domain)* |
| **3. Source Ingestion** | | *(Source type: Local Folder / CBZ / Web)* |
| **4. Panel Detection & Splitting**| | |
| **5. OCR Text & Balloon Review** | | |
| **6. Story Pacing & Beat Review** | | |
| **7. Script Dialogue Editing** | | |
| **8. Audio Timeline Generation** | | |
| **9. Motion Camera Keyframing** | | |
| **10. Video Rendering (MP4)** | | *(Selected profile: standard_1080p / mobile_720p)* |
| **11. Final Video Playback** | | *(Played in-app and in external player?)* |

---

## 4. TIME & USABILITY METRICS

| Metric | Measured Value |
| :--- | :--- |
| **Time to First Video (TTFV)** | *(Minutes and seconds from installer start to finished MP4)* |
| **User Interaction / Editing Time** | *(Time spent actively reviewing panels, text, motion)* |
| **Automated Render Time** | *(Seconds required for FFmpeg MP4 export)* |
| **Number of Support Interventions** | *(0 = Completed independently without developer assistance)* |
| **Nature of Any Developer Assistance** | *(None / Documentation clarification / Bug triage)* |

---

## 5. USER FEEDBACK & QUALITY EVALUATION

1. **Was installation easy and clear?**  
   `[ ] Yes  [ ] No  [ ] Mixed`  
   *Comments*:

2. **Did you clearly understand that Python 3.12 is required for the backend?**  
   `[ ] Yes  [ ] No`  
   *Comments*:

3. **Did the application clearly communicate which models/tools were available vs fallback?**  
   `[ ] Yes  [ ] No`  
   *Comments*:

4. **What was the single most confusing step during the workflow?**  
   *Response*:

5. **Did anything crash, freeze, or display an unhandled error message?**  
   `[ ] No crashes  [ ] Yes (describe below)`  
   *Crash Details*:

6. **Rate the final rendered video quality (Scale 1–10):**  
   `Score: ____ / 10`  
   *Comments on visuals, voice pacing, music, camera motion*:

7. **Would you use PanelFlow Studio again for your creative projects?**  
   `[ ] Yes  [ ] No  [ ] Undecided`

8. **What ONE improvement or change would make you most likely to use PanelFlow regularly?**  
   *Response*:

---

## 6. VERIFICATION & ATTACHMENTS

- **Project Directory Archive**: *(Path or zip reference, e.g., `real_testers/T-001/project_data/`)*
- **Rendered Output Video**: *(Path to MP4, e.g., `real_testers/T-001/final_render.mp4`)*
- **Diagnostic Bundle**: *(Export from Tools & Models > Diagnostics, saved to `real_testers/T-001/diagnostics.json`)*
- **Log File**: *(Copied from `%LOCALAPPDATA%\PanelFlow Studio\logs\panelflow.log`)*

---
*Sign-off: This submission represents an actual run performed by an independent human tester on the indicated hardware without simulated data.*
