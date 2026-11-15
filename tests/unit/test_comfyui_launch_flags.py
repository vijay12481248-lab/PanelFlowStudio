"""Task 4 of the review-page plan: the app starts ComfyUI the way the second vision judge needs."""
from pathlib import Path

from engine.system.setup import comfyui_launch_command


def test_launch_command_disables_dynamic_vram_and_keeps_the_old_flags():
    # measured: with dynamic VRAM on, TextGenerate (Qwen3-VL 8B) fails inside ComfyUI; with it off drawing still works
    cmd = comfyui_launch_command(Path("C:/py/python.exe"), Path("E:/ComfyUI/main.py"), "127.0.0.1", 8188)
    assert cmd == [str(Path("C:/py/python.exe")), str(Path("E:/ComfyUI/main.py")), "--listen", "127.0.0.1", "--port", "8188",
                   "--disable-auto-launch", "--enable-cors-header", "*", "--disable-dynamic-vram"]


def test_the_flag_can_be_left_out_for_a_comfyui_that_does_not_know_it():
    cmd = comfyui_launch_command(Path("py.exe"), Path("main.py"), "127.0.0.1", 8188, disable_dynamic_vram=False)
    assert "--disable-dynamic-vram" not in cmd and "--listen" in cmd


def test_ensure_running_retries_once_without_the_flag_when_comfyui_exits_at_start(monkeypatch, tmp_path):
    # review finding I10: a ComfyUI build that rejects the new flag must not stop all art
    import subprocess

    from engine.system import setup

    launches = []

    class Proc:
        def __init__(self, cmd):
            self.pid, self.cmd = 1000 + len(launches), cmd

        def poll(self):
            return 2 if "--disable-dynamic-vram" in self.cmd else None  # the flagged launch dies at once, the plain one stays up

    def fake_popen(cmd, **kw):
        launches.append(cmd)
        return Proc(cmd)

    mgr = setup.ComfyUIManager()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mgr, "locate", lambda: {"installed": True, "root": "C:/c", "python": "py.exe", "main_py": "main.py"})
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # the launcher writes comfyui.log: keep it out of the real log folder

    def up_after_second(host="127.0.0.1", port=8188):
        return len(launches) >= 2

    monkeypatch.setattr(mgr, "is_running", up_after_second)
    res = mgr.ensure_running(timeout_s=3.0)
    assert len(launches) == 2 and "--disable-dynamic-vram" in launches[0] and "--disable-dynamic-vram" not in launches[1]
    assert res["running"] is True
