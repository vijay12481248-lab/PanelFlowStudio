"""Task 4 of the review-page plan: the app starts ComfyUI the way the second vision judge needs."""
from pathlib import Path

from engine.system.setup import comfyui_launch_command


def test_launch_command_disables_dynamic_vram_and_keeps_the_old_flags():
    # measured: with dynamic VRAM on, TextGenerate (Qwen3-VL 8B) fails inside ComfyUI; with it off drawing still works
    cmd = comfyui_launch_command(Path("C:/py/python.exe"), Path("E:/ComfyUI/main.py"), "127.0.0.1", 8188)
    assert cmd == [str(Path("C:/py/python.exe")), str(Path("E:/ComfyUI/main.py")), "--listen", "127.0.0.1", "--port", "8188",
                   "--disable-auto-launch", "--enable-cors-header", "*", "--disable-dynamic-vram"]
