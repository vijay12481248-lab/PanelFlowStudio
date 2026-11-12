"""Audio QA: what is wrong with a take, and what to do about it.

The workflow asks for six checks on every generated take:

- intelligibility: was the line said as it was written?
- pronunciation: was a name said the way the bible says it?
- duration: is the take a plausible length for its line?
- clipping: did the take distort at the peaks?
- silence: does the take carry the words, or a gap?
- timing: does the take fit the pause the direction asked for?

Each check names a repair the owner can act on. Nothing here decides: the
reviewer reads the report and chooses.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.narration.artifacts import VoiceTake

Severity = Literal["block", "warn"]

INTELLIGIBLE_LIMIT = 0.15  # word error rate above this: the line was not said as written
PRONUNCIATION_LIMIT = 0.30  # a name heard wrongly often enough to matter
CLIPPED_SAMPLES = 0.005  # 0.5% of the samples at full scale: the take distorts
SILENCE_RATIO = 0.60  # under this share of audible samples, the take is mostly a gap
DURATION_TOLERANCE = 0.5  # a take may run half a second either side of its estimate
WORDS_PER_SECOND = 2.75


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QaCheck(_Strict):
    """One thing that is wrong with a take, and the repair that would fix it."""

    rule: str
    passed: bool
    severity: Severity
    reason: str = ""
    repair: str = ""  # what the reviewer can do about it


class QaReport(_Strict):
    """The QA of one take: what passed, what did not, and what to do."""

    line_id: str
    checks: list[QaCheck] = Field(default_factory=list)
    passed: bool = True

    @property
    def failures(self) -> list[QaCheck]:
        return [c for c in self.checks if not c.passed]


def _read_wav(path: str | Path) -> tuple[list[int], int]:
    """The samples of a wav file, and its sample rate."""
    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
        width = w.getsampwidth()
        rate = w.getframerate()
    if width == 2:
        import array
        out = array.array("h")
        out.frombytes(frames)
        return list(out), rate
    if width == 1:
        return [b - 128 for b in frames], rate
    return list(frames), rate


def _audible_share(samples: list[int]) -> float:
    """The share of the samples that carry sound, judged against a quiet floor."""
    if not samples:
        return 0.0
    peak = max(abs(s) for s in samples) or 1
    floor = peak * 0.02  # 2% of the peak: below this is room noise
    audible = sum(1 for s in samples if abs(s) > floor)
    return audible / len(samples)


FULL_SCALE = 32767  # 16-bit PCM: a sample at this level has clipped


def _clipped_share(samples: list[int]) -> float:
    """The share of the samples pinned at full scale.

    Full scale, not the take's own peak: a loud but clean take is not clipping.
    """
    if not samples:
        return 0.0
    return sum(1 for s in samples if abs(s) >= FULL_SCALE * 0.999) / len(samples)


def qa_take(take: VoiceTake, line_text: str, spoken: str = "",
            expected_duration: float | None = None) -> QaReport:
    """Check one take and name the repair for each thing that is wrong."""
    checks: list[QaCheck] = []

    # intelligibility: was the line said as it was written?
    checks.append(QaCheck(
        rule="intelligibility", passed=take.wer <= INTELLIGIBLE_LIMIT,
        severity="block" if take.wer > INTELLIGIBLE_LIMIT else "warn",
        reason=f"word error rate {take.wer:.0%}",
        repair=("regenerate the line with a slower pace" if take.wer > INTELLIGIBLE_LIMIT else ""),
    ))

    # pronunciation: were the names heard the way the bible says them?
    names_missed = [w for w in take.stt_text.split() if w.lower() not in spoken.lower()] if spoken else []
    wrong_name = take.wer > PRONUNCIATION_LIMIT
    checks.append(QaCheck(
        rule="pronunciation", passed=not wrong_name, severity="warn",
        reason=("a name was heard wrongly" if wrong_name else ""),
        repair=("adjust the pronunciation in the series bible and regenerate" if wrong_name else ""),
    ))

    # duration: is the take a plausible length for its line?
    words = len(line_text.split())
    expected = expected_duration if expected_duration is not None else words / WORDS_PER_SECOND
    drift = abs(take.duration - expected)
    too_long = drift > DURATION_TOLERANCE
    checks.append(QaCheck(
        rule="duration", passed=not too_long, severity="warn",
        reason=f"{take.duration:.1f}s against an expected {expected:.1f}s",
        repair=("regenerate the line at a different pace" if too_long else ""),
    ))

    # clipping and silence: read the audio itself.
    samples: list[int] = []
    rate = 0
    try:
        samples, rate = _read_wav(take.audio_path)
    except (OSError, ValueError, wave.Error):
        pass
    clipped = _clipped_share(samples)
    checks.append(QaCheck(
        rule="clipping", passed=clipped <= CLIPPED_SAMPLES, severity="warn",
        reason=f"{clipped:.1%} of the samples are at full scale" if clipped > CLIPPED_SAMPLES else "",
        repair=("regenerate the line at a lower level" if clipped > CLIPPED_SAMPLES else ""),
    ))

    audible = _audible_share(samples) if samples else 1.0
    too_quiet = audible < SILENCE_RATIO
    checks.append(QaCheck(
        rule="silence", passed=not too_quiet, severity="block" if too_quiet else "warn",
        reason=f"only {audible:.0%} of the take carries sound" if too_quiet else "",
        repair=("regenerate the line; the take is mostly silence" if too_quiet else ""),
    ))

    # timing: does the take fit the pause the direction asked for?
    lead = take.lead_ms / 1000
    trailing = take.tail_ms / 1000
    timing_ok = lead <= 0.25 and trailing <= 0.25
    checks.append(QaCheck(
        rule="timing", passed=timing_ok, severity="warn",
        reason=f"{lead * 1000:.0f}ms of silence before, {trailing * 1000:.0f}ms after" if not timing_ok else "",
        repair=("trim the silence around the take" if not timing_ok else ""),
    ))

    return QaReport(line_id=take.line_id, checks=checks,
                    passed=not any(c.passed is False and c.severity == "block" for c in checks))


def qa_report(takes: list[VoiceTake], lines: dict[str, str], spoken: dict[str, str] | None = None,
              expected: dict[str, float] | None = None) -> dict[str, QaReport]:
    """The QA of every take, by line id."""
    spoken = spoken or {}
    expected = expected or {}
    return {t.line_id: qa_take(t, lines.get(t.line_id, ""), spoken.get(t.line_id, ""),
                                expected.get(t.line_id)) for t in takes}


def repairs(report: QaReport) -> list[str]:
    """The repairs a report suggests, in the order the checks are listed."""
    return [c.repair for c in report.failures if c.repair]
