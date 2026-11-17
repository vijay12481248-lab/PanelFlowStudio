"""Level the effects against the voice, so a hit sits under the words instead of on top of them.

Library and synthesised effects arrive at very different loudness (a stock impact peaks near 0 dBFS, speech sits around -20 dB RMS), so a plan
mixed at the cues' own level is mostly loud effects. This works out, per cue, a trim in dB that is added to the cue's own gain and the track fader:

* effects land at a target relative to the speech level of the dialogue stem (hits by peak, ambience beds by RMS);
* a hit that lands while someone is talking is taken down another few dB, and further when the voice there is soft (a quiet, emotional line gets
  a quiet effect, a loud line keeps more of it);
* with no dialogue the speech level is assumed to be DEFAULT_REF_DB.

Pure numpy, no ffmpeg: the dialogue stem is already a 48 kHz float wav when this runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

BLOCK_S = 0.1
DEFAULT_REF_DB = -20.0
# (what to measure on the take, dB relative to the speech level the take should reach)
TARGETS = {"effects": ("peak", 6.0), "foley": ("peak", 0.0), "bed": ("rms", -14.0)}
VOICE_PRESENT_DB = -3.0      # a hit on top of speech
SOFT_VOICE_MAX_DB = -6.0     # extra, at most, when the voice there is much softer than usual
MAX_BOOST_DB, MAX_CUT_DB = 12.0, -60.0   # a stock hit near 0 dBFS under a quietly recorded narration needs a large cut


@dataclass
class VoiceProfile:
    ref_db: float            # speech level: mean power of the active 100 ms blocks, dBFS
    blocks_db: np.ndarray    # every block's RMS in dBFS
    active: np.ndarray       # bool: speech is present in that block


def profile(dialogue_wav: Path | str) -> VoiceProfile | None:
    """The speech level and where the speech is, or None when the stem is silent."""
    x, sr = sf.read(str(dialogue_wav), dtype="float32", always_2d=True)
    mono = x.mean(axis=1)
    n = max(1, int(sr * BLOCK_S))
    nb = len(mono) // n
    if nb == 0:
        return None
    power = (mono[:nb * n].reshape(nb, n) ** 2).mean(axis=1) + 1e-12
    db = 10 * np.log10(power)
    if db.max() < -60:
        return None
    active = db > max(db.max() - 30.0, -60.0)
    return VoiceProfile(float(10 * np.log10(power[active].mean())), db, active)


def duck_threshold(prof: VoiceProfile) -> float:
    """Sidechain threshold (linear) 12 dB under the speech level, so a bed ducks the same whether the narration was recorded quietly or hot."""
    return float(max(0.002, min(0.25, 10 ** ((prof.ref_db - 12.0) / 20))))


def _voice_near(prof: VoiceProfile, t0: float, t1: float) -> float | None:
    """Mean power (dBFS) of the speech blocks between t0 and t1, or None when nobody talks there."""
    a, b = max(0, int(t0 / BLOCK_S)), min(len(prof.blocks_db), int(np.ceil(t1 / BLOCK_S)))
    sel = prof.active[a:b]
    if b <= a or not sel.any():
        return None
    return float(10 * np.log10((10 ** (prof.blocks_db[a:b][sel] / 10)).mean()))


def trim_db(cue, group: str, prof: VoiceProfile | None) -> float:
    """dB to add to this effect cue. group: "effects" (a hit), "bed" (ambience / long bed). Takes that were never measured are left alone."""
    take = cue.chosen()
    if take is None:
        return 0.0
    key = "foley" if (group == "effects" and cue.track == "foley") else group
    what, rel = TARGETS[key]
    have = take.peak_db if what == "peak" else take.rms_db
    if have <= -100.0:
        return 0.0
    if sf.info(take.path).channels == 1:
        have -= 3.0   # render_cue upmixes mono to stereo with ffmpeg's -3 dB centre rule
    ref = prof.ref_db if prof else DEFAULT_REF_DB
    trim = (ref + rel) - have
    if group == "effects" and prof is not None:
        centre = cue.hit_t if cue.hit_t is not None else cue.t_in
        near = _voice_near(prof, centre - 0.4, centre + 0.8)
        if near is not None:
            trim += VOICE_PRESENT_DB + max(SOFT_VOICE_MAX_DB, min(0.0, 0.5 * (near - prof.ref_db)))
    return float(max(MAX_CUT_DB, min(MAX_BOOST_DB, trim)))
