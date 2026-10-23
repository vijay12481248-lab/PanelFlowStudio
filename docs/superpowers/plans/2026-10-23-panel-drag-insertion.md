# Panel drag insertion implementation plan
Goal: One drop inserts exactly its selected panels, in order, at the indicated scene boundary; existing panels reuse their scenes.
1. Reproduce bubbling duplicates with DOM tests and add position, repeat-drop, batch-order, lock and source selection regressions.
2. Add typed shared panel payload decoder and coordinate boundary resolver; insert a batch in one state update, reusing matching scenes and aligning linked narration. Capture source drops once; leave internal scene/layer drag behavior intact.
3. Source browser: Ctrl/Cmd toggle and Shift range selection, count/instructions, one ordered payload and cropped-thumbnail drag preview; dragging an unselected item uses that item only.
4. Run focused source/timeline tests, npm test, TypeScript/Vite and Tauri release build; review diff and write Agent Hub handoff.
Constraints: preserve all existing edits, no new dependencies; keep undo one action per drop. No native gesture claim without testing it.

## Completed verification
- Reproduced duplicate insertion before fix: one drop created 5 scenes instead of 4.
- Full editor suite: 132 passing before the final cancellation regression; final npm test passes 37 history + 89 focused/API/shortcut/config checks (includes cancellation).
- Chromium mouse drags on isolated QA fixture verified Ctrl batch selection [panel-1,panel-3], insertion of panel-2 between them, panel-4 at beginning, existing panel-2 moved to start without duplication, Shift selection of 4 and drag preserving unique reading order. Preview element removed after drop.
- Production frontend build passed. Running native app locked default executable, so built side-by-side with cargo rustc --release --bin panelflow-desktop -- -o <absolute target path>. Exit 0; verified executable embeds latest index-BxWD_UtM.js.
- Artifact: apps/desktop/src-tauri/target/release/panelflow-desktop-panel-drag-20261023.exe.
