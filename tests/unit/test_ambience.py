"""Weather sound for silent clips: layers from the shot's words, lightning flashes found in the picture, thunder placed after them."""
import subprocess

import cv2
import numpy as np

from engine.original import ambience as am


def _clip(path, flash_frames=(), n=96, fps=24):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 90))
    for i in range(n):
        w.write(np.full((90, 160, 3), 200 if i in flash_frames else 60, np.uint8))
    w.release()
    return path


def test_layers_come_from_the_shot_words():
    assert am.layers("Heavy rain streaks across the view while wind bends the grass") == {"rain", "wind"}
    assert am.layers("A lightning bolt splits the dark purple sky") == {"thunder"}
    assert am.layers("Bright blue sky with soft golden sunlight") == set()
    assert am.layers("Maya points right as rain stops and wind bends grass") == {"wind"}  # weather that has ended is not heard


def test_a_flash_is_found_where_the_picture_jumps_brighter(tmp_path):
    assert am.flashes(_clip(tmp_path / "f.mp4", flash_frames=(48, 49))) == [2.0]
    assert am.flashes(_clip(tmp_path / "n.mp4")) == []


def test_thunder_follows_the_flash_and_the_bed_stays_quiet():
    x = am.render(6.0, "lightning over the hills", [2.0], seed=1)
    assert x.shape == (6 * am.SR, 2)
    env = np.abs(x[:, 0])
    before, after = env[: int(2.3 * am.SR)].max(), env[int(2.3 * am.SR): int(3.6 * am.SR)].max()
    assert after > 5 * before  # nothing loud until the sound of the flash arrives (0.4-1.2 s later)
    calm = am.render(6.0, "bright blue sky", [], seed=1)
    assert 20 * np.log10(np.sqrt(np.mean(calm ** 2))) < -40  # a sunny shot only gets a faint outdoor air bed


def test_a_clip_with_its_own_sound_is_left_alone(tmp_path):
    silent = _clip(tmp_path / "s.mp4")
    loud = tmp_path / "l.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest", "-c:v", "copy", "-c:a", "aac", str(loud)], check=True)
    assert am.ensure(loud, "rain", tmp_path / "l.wav", 4.0) is None
    assert am.ensure(silent, "rain", tmp_path / "s.wav", 4.0).exists()
