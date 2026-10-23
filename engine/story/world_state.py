"""Deterministic, non-destructive replay of approved narrative state transitions.

Event list order is canonical. No fact is inferred from prose or event type.
Uncertain or invalid events produce ERROR diagnostics and are skipped atomically.
The returned state is a replay snapshot, not a new approval of any input artifact.
"""
from collections import Counter
from hashlib import sha256
from typing import List

from pydantic import BaseModel, Field

from engine.story.models import (
    ContinuityWarningEntity, NarrativeDocument, ProvenanceReference,
    StateApproval, StateValue, WorldState,
)


class WorldStateReplay(BaseModel):
    state: WorldState
    warnings: List[ContinuityWarningEntity] = Field(default_factory=list)
    applied_event_ids: List[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(w.severity == "ERROR" for w in self.warnings)


def replay_world_state(doc: NarrativeDocument) -> WorldStateReplay:
    """Replay explicit changes; preserve every input field and approval record."""
    result = WorldStateReplay(state=doc.initial_world_state.model_copy(deep=True))
    chars = {c.character_id for c in doc.characters}
    locations = {loc.location_id for loc in doc.locations}
    panels = {p.panel_id for p in doc.observations}
    panels.update(u.panel_id for u in doc.utterances)
    text_panels = {}
    for utterance in doc.utterances:
        text_panels.setdefault(utterance.text_region_id, set()).add(utterance.panel_id)

    def warn(kind: str, detail: str, index: int = -1) -> None:
        event = doc.events[index] if index >= 0 else None
        token = sha256(f"{index}:{kind}:{detail}".encode()).hexdigest()[:16]
        result.warnings.append(ContinuityWarningEntity(
            warning_id=f"state_{token}", warning_type=kind, severity="ERROR",
            description=detail, affected_panel_ids=list(event.panel_ids) if event else [],
            affected_character_ids=[event.actor_character_id] if event and event.actor_character_id else [],
        ))

    def approved(approval: StateApproval) -> bool:
        return approval.status == "APPROVED" and bool(approval.approved_by and approval.approved_by.strip())

    def grounded(evidence: ProvenanceReference) -> bool:
        return bool(evidence.panel_ids or evidence.text_region_ids) and (
            all(p in panels for p in evidence.panel_ids)
            and all(
                len(text_panels.get(t, set())) == 1
                and (not evidence.panel_ids or text_panels[t].issubset(evidence.panel_ids))
                for t in evidence.text_region_ids
            )
        )

    initial = doc.initial_world_state
    if initial.possessions or initial.locations or any(initial.knowledge.values()):
        if not approved(initial.approval):
            warn("UNAPPROVED_INITIAL_STATE", "Initial world facts require an explicit creator approval.")
        if not grounded(initial.evidence):
            warn("UNGROUNDED_INITIAL_STATE", "Initial world facts require known source evidence.")
        if not 0.8 <= initial.evidence.confidence <= 1.0:
            warn("UNCERTAIN_INITIAL_STATE", "Initial world evidence is uncertain.")
        if (any(owner is not None and owner not in chars for owner in initial.possessions.values())
                or any(c not in chars or (loc is not None and loc not in locations) for c, loc in initial.locations.items())
                or any(c not in chars for c in initial.knowledge)):
            warn("INVALID_INITIAL_REFERENCE", "Initial state references an unknown character or location.")
        if result.warnings:
            # Untrusted initial facts cannot seed later canonical transitions.
            result.state = WorldState()
            return result

    counts = Counter(e.event_id for e in doc.events)
    positions = {e.event_id: i for i, e in enumerate(doc.events)}
    invalid = set()
    parents = {i: set(e.caused_by) for i, e in enumerate(doc.events)}
    for i, event in enumerate(doc.events):
        if counts[event.event_id] > 1:
            warn("DUPLICATE_EVENT_ID", f"Event ID '{event.event_id}' is not unique.", i)
            invalid.add(i)
        for dependency in event.caused_by:
            if dependency not in positions:
                warn("MISSING_CAUSAL_DEPENDENCY", f"Event '{event.event_id}' requires missing event '{dependency}'.", i)
                invalid.add(i)
            elif positions[dependency] >= i:
                warn("FORWARD_CAUSAL_DEPENDENCY", f"Event '{event.event_id}' requires a cause before it: '{dependency}'.", i)
                invalid.add(i)
        for enabled in event.enables:
            if enabled not in positions:
                warn("MISSING_CAUSAL_DEPENDENCY", f"Event '{event.event_id}' enables missing event '{enabled}'.", i)
                invalid.add(i)
            elif positions[enabled] <= i:
                warn("FORWARD_CAUSAL_DEPENDENCY", f"Event '{event.event_id}' must precede enabled event '{enabled}'.", i)
                invalid.add(i)
            else:
                parents[positions[enabled]].add(event.event_id)

    applied = set()
    for i, event in enumerate(doc.events):
        if i in invalid:
            continue
        if any(parent not in applied for parent in parents[i]):
            warn("UNAPPLIED_CAUSAL_DEPENDENCY", f"Event '{event.event_id}' depends on a rejected event.", i)
            continue
        candidate = result.state.model_copy(deep=True)
        warning_count = len(result.warnings)
        for change in event.state_changes:
            prefix = f"Event '{event.event_id}' {change.domain.lower()} '{change.subject_id}'"
            if not approved(change.approval):
                warn("UNAPPROVED_STATE_CHANGE", f"{prefix} requires an explicit creator approval.", i)
            if not grounded(change.evidence):
                warn("UNGROUNDED_STATE_CHANGE", f"{prefix} requires known source evidence.", i)
            if (not change.after.known or not 0.8 <= change.evidence.confidence <= 1.0
                    or not 0.8 <= event.confidence <= 1.0):
                warn("UNCERTAIN_STATE_CHANGE", f"{prefix} cannot establish an uncertain fact.", i)
            values = [v.value for v in (change.before, change.after) if v.known and v.value is not None]
            invalid_ref = (
                change.domain == "POSSESSION" and any(v not in chars for v in values)
                or change.domain == "LOCATION" and (change.subject_id not in chars or any(v not in locations for v in values))
                or change.domain == "KNOWLEDGE" and change.subject_id not in chars
            )
            if invalid_ref:
                warn("INVALID_STATE_REFERENCE", f"{prefix} references an unknown character or location.", i)
            if change.domain == "POSSESSION":
                table = candidate.possessions
                key = change.subject_id
            elif change.domain == "LOCATION":
                table = candidate.locations
                key = change.subject_id
            else:
                table = candidate.knowledge.setdefault(change.subject_id, {})
                key = change.fact_id
            current = StateValue(known=key in table, value=table.get(key))
            if current != change.before:
                warn("STATE_BEFORE_MISMATCH", f"{prefix} before-value contradicts canonical state.", i)
            if change.after.known:
                table[key] = change.after.value
        if len(result.warnings) == warning_count:
            result.state = candidate
            result.applied_event_ids.append(event.event_id)
            applied.add(event.event_id)
    return result


def prepare_generated_world_state(
    candidate: NarrativeDocument, previous: NarrativeDocument | None = None,
) -> NarrativeDocument:
    """Strip model approvals and protect existing canonical work during analysis.

    Source digests must be computed from source records by the calling service,
    never supplied by the model. Preservation copies whole prior events rather
    than transferring creator approvals onto freshly inferred event identities.
    Changed source with prior state needs explicit canonical change review before
    persistence; neither input document is mutated.
    """
    prepared = candidate.model_copy(deep=True)
    prepared.initial_world_state.approval = StateApproval()
    for event in prepared.events:
        for change in event.state_changes:
            change.approval = StateApproval()
    if previous is None:
        return prepared
    initial = previous.initial_world_state
    has_canonical_work = bool(
        initial.possessions or initial.locations or initial.knowledge
        or any(event.state_changes for event in previous.events)
    )
    if not has_canonical_work:
        return prepared
    old_digest = previous.analysis_metadata.get("source_context_digest")
    new_digest = candidate.analysis_metadata.get("source_context_digest")
    if (not isinstance(old_digest, str) or not old_digest.strip()
            or not isinstance(new_digest, str) or not new_digest.strip()
            or old_digest != new_digest):
        raise ValueError("Source changed or provenance digest is missing; canonical change review is required before persistence.")
    prepared.initial_world_state = initial.model_copy(deep=True)
    prepared.events = [event.model_copy(deep=True) for event in previous.events]
    return prepared
