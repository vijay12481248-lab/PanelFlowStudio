"""Native OS folder picker dialog helper for PanelFlow Studio."""

import asyncio
import os
import sys
from pathlib import Path


def _open_native_dialog_sync(initial_dir: str = "", title: str = "Select Folder for PanelFlow Studio") -> str:
    r"""Open native Windows/macOS/Linux system folder selection dialog."""
    # Method 1: Tkinter filedialog with topmost attribute
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        init_p = str(Path(initial_dir).resolve()) if initial_dir and Path(initial_dir).exists() else None
        selected = filedialog.askdirectory(parent=root, initialdir=init_p, title=title)
        try:
            root.destroy()
        except Exception:
            pass
        if selected:
            return str(Path(selected).resolve())
    except Exception:
        pass

    # Method 2: Fallback to PowerShell FolderBrowserDialog on Windows
    if os.name == "nt":
        try:
            import subprocess
            init_arg = f"$d.SelectedPath = '{initial_dir}';" if initial_dir and Path(initial_dir).exists() else ""
            ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '{title}'
$d.AutoUpgradeEnabled = $true
$d.ShowNewFolderButton = $true
{init_arg}
if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $d.SelectedPath
}}
"""
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code],
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            if out:
                return str(Path(out).resolve())
        except Exception:
            pass

    return ""


async def pick_native_folder(initial_dir: str = "", title: str = "Select Folder for PanelFlow Studio") -> str:
    """Run native folder dialog in a background thread without blocking event loop."""
    return await asyncio.to_thread(_open_native_dialog_sync, initial_dir, title)
