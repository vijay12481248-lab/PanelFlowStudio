# PanelFlow Studio — Character Entity Model & Resolution

## 1. Overview
The Character Entity subsystem tracks, resolves, and maintains consistent character identities across pages and panels. Comics frequently use partial names, nicknames, titles ("The Commander", "Captain"), and visual pronouns without repeating the character's full name.

The Character Model ensures that:
1. Every dialogue utterance maps to a known character identity, `NARRATOR`, or `SFX`.
2. Multiple aliases and mentions are unified under a single **Canonical Name**.
3. Human operators can merge accidental duplicate entities or split erroneously lumped characters.
4. Changes to character identities automatically invalidate downstream script segments via the dependency graph.

---

## 2. Character Entity Schema

```typescript
export interface CharacterEntity {
  character_id: string;             // Unique identifier (char_XXXXXXXX)
  project_id: string;               // Owning project ID
  display_name: string;             // UI presentation label
  canonical_name: string;           // Normalized true name
  aliases: string[];                // Alternate names, nicknames, titles
  description: string;              // Personality and role description
  visual_traits: string[];          // Recognized visual descriptors
  role: CharacterRole;              // PROTAGONIST, ANTAGONIST, SUPPORTING, MINOR
  first_panel_id?: string | null;   // Panel ID of initial appearance
  reference_panel_ids: string[];    // Exemplar panels for visual reference
  status: CharacterStatus;          // CONFIRMED, LIKELY, UNCERTAIN, MANUAL
  manual_override: boolean;         // True if modified by human operator
}
```

---

## 3. Lifecycle & State Transitions

```
[Vision LLM / OCR] ──▶ UNCERTAIN ──▶ LIKELY ──▶ CONFIRMED
                             │                      ▲
                             ▼                      │
                          MANUAL ───────────────────┘
```

1. **Detection (UNCERTAIN)**: Initial candidate discovered from visual analysis or named dialogue mention.
2. **Resolution (LIKELY)**: Corroborated by recurrence across panels, visual trait continuity, or dialogue address.
3. **Approval (CONFIRMED)**: Confirmed through automated continuity audit or accepted during Story Review.
4. **Manual Intervention (MANUAL)**: Any modification made by the user in the UI flags the character as `MANUAL` with `manual_override = true`. Manual records are permanently protected from being deleted or overwritten during re-analysis.

---

## 4. Entity Disambiguation Operations

### A. Character Merge
When two discovered character records represent the same individual (e.g. "The Scout" and "Valerian"):
- **Endpoint**: `POST /api/projects/{project_id}/characters/merge`
- **Payload**:
  ```json
  {
    "source_character_id": "char_002",
    "target_character_id": "char_001"
  }
  ```
- **Execution**:
  1. All `text_regions` attributed to `source_character_id` are reassigned to `target_character_id`.
  2. All narrative `events` where `source_character_id` is actor or target are updated to `target_character_id`.
  3. The aliases of `source_character_id` (plus its display name) are appended to `target_character_id.aliases`.
  4. The source record is removed from the database.
  5. The target record is marked `manual_override = true`.
  6. Downstream script dependencies are invalidated (`dependency_graph.invalidate(project_id, CHARACTER)`).

### B. Character Split
When an automated run conflated two distinct characters into one identity:
- **Endpoint**: `POST /api/projects/{project_id}/characters/{character_id}/split`
- **Payload**:
  ```json
  {
    "new_name": "Aria",
    "panel_ids": ["panel_003", "panel_004"]
  }
  ```
- **Execution**:
  1. A new `CharacterEntity` is created with `new_name`.
  2. Text regions and events within the specified `panel_ids` belonging to the original character are reassigned to the new character.
  3. Both records are flagged with `manual_override = true`.
  4. Downstream script dependencies are invalidated.
