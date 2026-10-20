# Workflow Alignment: Panel Review ↔ Story Editor

## Summary

Fixed the misalignment between Panel Review workflow (normal/panel-wise) and Story Editor workflow (video editor). Changes in Panel Review were not propagating to Story Editor, causing stale data at video generation time.

## Problem

Users reported:
- Modifications in Panel Review workflow weren't reflected in Story Editor
- Video generation used stale panel data instead of latest changes  
- No indication that workflows had drifted apart
- Layers referencing deleted panels caused silent failures

## Root Cause

1. **One-way geometry sync**: Only panel x,y,width,height were reconciled at read/save time
2. **No scene structure updates**: Scenes added/removed/reordered in Panel Review weren't reflected in Story Editor
3. **No user feedback**: Users had no visual indication of panel changes between workflows
4. **Deleted panel references**: Layers referencing deleted panels remained, causing render failures

## Solution

### Backend Changes

#### `engine/projects/service.py`

1. **Enhanced `reconcile_story_editor_state_with_panels()`** to:
   - Detect and remove layers referencing deleted panels
   - Track panel usage and removed layers count
   - Detect when panels have been added/removed/reordered
   - Add metadata (`panel_review_sync`) tracking sync status
   - Track timestamps and panel counts

2. **Updated `confirm_panels()`** to mark Story Editor state as stale:
   - When panels are confirmed in Panel Review, Story Editor state gets flagged
   - Metadata includes `last_panel_confirm` timestamp and `panels_stale` flag
   - Ensures next Story Editor load will detect changes

### Frontend Changes

#### `apps/desktop/src/screens/StoryEditorScreen.tsx`

1. **Added `panelSyncAlert` state** to show visual notifications:
   - Tracks whether panels have changed
   - Shows specific messages for deleted panels vs general changes

2. **Added sync check on state load**:
   - When loading saved Story Editor state, checks `panel_review_sync` metadata
   - Displays alert if panels were deleted or modified
   - Shows count of removed panels for awareness

3. **Added visual alert component**:
   - Amber banner at top of Story Editor UI
   - Shows panel change message with dismiss button
   - Positioned centrally for visibility

## How It Works

### Panel Change Detection Flow

```
Panel Review Modifications → Panel Confirm → Backend Marks State Stale → 
Story Editor Load → Reconciliation → Sync Alert Displayed → User Aware of Changes
```

### Reconciliation Process

When Story Editor loads or saves:
1. Backend queries current panel data from DB
2. Compares with stored Story Editor state
3. Removes layers referencing deleted panels
4. Detects panel additions/removals/reorderings
5. Sets metadata flags
6. Frontend shows alert if changes detected

## Files Modified

### Backend (`engine/projects/service.py`)
- Enhanced `reconcile_story_editor_state_with_panels()` function
- Updated `confirm_panels()` to mark state stale

### Frontend (`apps/desktop/src/screens/StoryEditorScreen.tsx`)
- Added `panelSyncAlert` state
- Added sync check on state load
- Added visual alert component

## Testing

All integration tests pass (16/16):
- test_panel_api.py
- test_manga_review.py
- test_story_pipeline.py
- And all other integration tests

Unit tests pass including:
- test_story_editor_panel_sync.py - specifically validates panel sync
- test_panel_editing.py - panel split, merge, delete operations

## Benefits

1. **Data consistency**: Story Editor always uses latest panel data
2. **User awareness**: Clear visual alerts when panels change
3. **Error prevention**: Deleted panels don't cause silent render failures
4. **Audit trail**: Metadata tracks when/how panels were synced
5. **Non-destructive**: Panel Review remains source of truth, Story Editor preserves user-authored motion

## Future Enhancements

- Automatic scene rebuilding on panel reorder
- Conflict resolution UI for panel changes
- Real-time sync via websockets
- Visual panel diff view between workflows