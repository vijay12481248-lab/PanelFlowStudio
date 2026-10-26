"""Pitch-preserving PCM derivatives for the shared preview audio clock."""
import io
import math
import os
import subprocess
from functools import lru_cache

import numpy as np
import soundfile as sf


@lru_cache(maxsize=8)
def tempo_preview(raw: bytes, tempo: float) -> bytes:
    if not math.isfinite(tempo) or not 0.0625 <= tempo <= 16:
        raise ValueError('Preview tempo must be between 0.0625 and 16')
    if abs(tempo - 1) < 0.00001:
        return raw
    from engine.render.encoder import FFmpegEncoder
    ffmpeg = FFmpegEncoder().ffmpeg_path
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required to preview stretched narration')
    samples, sr = sf.read(io.BytesIO(raw), dtype='float32', always_2d=True)
    remaining = tempo
    filters = []
    while remaining < 0.5:
        filters.append('atempo=0.5'); remaining /= 0.5
    while remaining > 2:
        filters.append('atempo=2'); remaining /= 2
    filters.append(f'atempo={remaining:.9f}')
    result = subprocess.run([
        str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-f', 'f32le',
        '-ar', str(sr), '-ac', str(samples.shape[1]), '-i', 'pipe:0',
        '-af', ','.join(filters), '-f', 'f32le', 'pipe:1',
    ], input=samples.astype('<f4').tobytes(), capture_output=True, check=True,
        timeout=max(30, len(samples) / sr * 2), creationflags=0x08000000 if os.name == 'nt' else 0)
    pcm = np.frombuffer(result.stdout, dtype='<f4').reshape(-1, samples.shape[1])
    count = round(len(samples) / tempo)
    pcm = np.pad(pcm[:count], ((0, max(0, count - len(pcm))), (0, 0)))
    out = io.BytesIO(); sf.write(out, pcm, sr, format='WAV', subtype='PCM_16')
    return out.getvalue()
