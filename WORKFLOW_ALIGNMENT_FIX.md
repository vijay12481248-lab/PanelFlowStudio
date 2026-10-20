# Workflow Alignment Fix - Panel Review & Story Editor Synchronization

## Problem Statement
The user reported that the Panel Review workflow (normal/panel-wise workflow) and Video Editor workflow (Story Editor) were not coordinating properly. Changes made in one workflow were not affecting the other, and at video generation time, the Video Editor was using stale data instead of the latest panel modifications.

## Root Causes Identified

1. **One-way synchronization**: Panel geometry was being reconciled at read/save time, but scene structure wasn't validated
2. **No panel change detection**: Story Editor didn't know when panels were added/removed/reordered in Panel Review
3. **Silent failures**: When panels were deleted in Panel Review, layers referencing them remained in Story Editor without warning
4. **No visual feedback**: Users had no indication that panels had changed between workflows

## Changes Made

### Backend (engine/)

#### 1. Enhanced Panel Reconciliation (`engine/projects/service.py`)
- **Enhanced `reconcile_story_editor_state_with_panels()`** to:
  - Detect and remove layers referencing deleted panels
  - Track panel usage and removed layers
  - Detect when panels have been added/removed/reordered
  - Add metadata about panel sync status
  - Track panel updates with timestamps

#### 2. Panel Confirmation Sync (`engine/projects/service.py`)
- **Modified `confirm_panels()`** to mark Story Editor state as stale when panels are confirmed
- Updates `panel_review_sync` metadata to trigger refresh in Story Editor

### Frontend (apps/desktop/src/)

#### 1. Story Editor Panel Sync Alert (`apps/desktop/src/screens/StoryEditorScreen.tsx`)
- Added `panelSyncAlert` state to track sync notifications
- Check for panel sync issues when loading saved state
- Display visual alert when panels have changed
- Show specific messages for removed panels vs general changes

## How It Works

1. **When panels change in Panel Review**:
   - User modifies panels (add/delete/reorder/split/merge)
   - When panels are confirmed, backend marks Story Editor state as stale

2. **When loading Story Editor**:
   - Backend reconciles panel geometry with current panel data
   - Detects deleted panels and removes references
   - Sets `panels_stale` and `panel_sync_required` flags
   - Frontend displays alert if panels have changed

3. **During render**:
   - Backend reconciliation ensures latest panel geometry is used
   - Layers referencing deleted panels are filtered out
   - Metadata tracks what changed for debugging

## Testing Recommendations

1. **Test panel deletion**:
   - Create project with panels → Open Story Editor → Go to Panel Review → Delete a panel → Return to Story Editor → Verify alert shows and layer is removed

2. **Test panel reordering**:
   - Create project → Modify panel order in Panel Review → Confirm → Return to Story Editor → Verify scenes reflect new order

3. **Test panel modification**:
   - Create project → Modify panel crop in Panel Review → Return to Story Editor → Verify geometry updated

4. **Test concurrent workflows**:
   - Open both workflows in separate tabs → Modify in Panel Review → Refresh Story Editor → Verify sync

## Files Modified

### Backend
- `engine/projects/service.py`:
  - Enhanced `reconcile_story_editor_state_with_panels()` (lines 54-120)
  - Updated `confirm_panels()` to mark state as stale (lines 1415-1430)

### Frontend
- `apps/desktop/src/screens/StoryEditorScreen.tsx`:
  - Added `panelSyncAlert` state (line 68)
  - Added panel sync check on state load (lines 374-386)
  - Added visual alert component (lines 839-853)

## Benefits

1. **Data consistency**: Story Editor always uses latest panel data
2. **User awareness**: Clear alerts when panels change
3. **Error prevention**: Deleted panels don't cause render failures
4. **Audit trail**: Metadata tracks when and how panels were synced
5. **Non-destructive**: Panel Review remains source of truth, Story Editor preserves user-authored motion

## Future Improvements

1. **Automatic scene rebuilding**: When panels are reordered, rebuild scene sequence automatically
2. **Conflict resolution UI**: Allow users to resolve panel changes manually
3. **Real-time sync**: Use websockets for immediate updates without page refresh
4. **Panel diff view**: Show visual comparison of panel changes between workflows
