"""The take ledger: what each generated take was made from.

A take records the script revision its words came from, the direction revision
its delivery came from, the cast profile that read it and the provider that
produced it. With that, an outdated take is recognisable: the line has moved on
since it was made, and the take must not be treated as the current one.
"""
from __future__ import annotations

from typing import Any

from engine.narration.artifacts import ScriptIR, VoiceTake


class TakeLedger:
    """The provenance a take carries, and the test for whether it is still current."""

    def __init__(self, script: ScriptIR, script_revision: int | None = None,
                 direction_revision: int = 0, voice_profile_ids: dict[str, str] | None = None,
                 provider: str = "") -> None:
        self.script = script
        self.script_revision = script.revision if script_revision is None else script_revision
        self.direction_revision = direction_revision
        self.voice_profile_ids = voice_profile_ids or {}
        self.provider = provider

    def provenance(self, line) -> dict[str, Any]:
        """The ledger fields of a take made from this line."""
        return {
            "script_revision": self.script_revision,
            "direction_revision": self.direction_revision,
            "voice_profile_id": self.voice_profile_ids.get(getattr(line, "speaker_id", ""), ""),
            "provider": self.provider,
        }

    def is_outdated(self, take: VoiceTake, script: ScriptIR | None = None) -> bool:
        """True when the take no longer matches the line it belongs to.

        A take is outdated when the text it read has changed, when the direction
        it was delivered with has changed, or when it was read by another voice.
        """
        script = script if script is not None else self.script
        line = next((ln for ln in script.lines if ln.line_id == take.line_id), None)
        if line is None:
            return True  # the line is gone: the take belongs to nothing
        if take.script_revision != self.script_revision:
            return True
        if take.direction_revision != self.direction_revision:
            return True
        speaker_id = getattr(line, "speaker_id", "")
        if take.voice_profile_id != self.voice_profile_ids.get(speaker_id, take.voice_profile_id):
            return True
        return False


def outdated_lines(takes: list[VoiceTake], ledger: TakeLedger) -> list[str]:
    """The lines whose take is no longer current."""
    return [t.line_id for t in takes if ledger.is_outdated(t)]
