import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist_engine"
RESOURCES_DIR = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "resources"
RELEASE_DIR = REPO_ROOT / "release"

RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
RELEASE_DIR.mkdir(parents=True, exist_ok=True)

print("=== Building Standalone Fast Engine Runtime (--onedir) ===")
print(f"Repository Root: {REPO_ROOT}")

# PyInstaller command using --onedir for instant startup (no runtime unpacking delay)
cmd = [
    sys.executable,
    "-m", "PyInstaller",
    "--name=panelflow-engine",
    "--onedir",
    "--noconfirm",
    "--clean",
    f"--distpath={DIST_DIR}",
    f"--workpath={REPO_ROOT / 'build_engine'}",
    # Hidden imports required for Uvicorn / FastAPI / Pydantic / SQLAlchemy
    "--hidden-import=uvicorn",
    "--hidden-import=uvicorn.logging",
    "--hidden-import=uvicorn.loops",
    "--hidden-import=uvicorn.loops.auto",
    "--hidden-import=uvicorn.loops.asyncio",
    "--hidden-import=uvicorn.protocols",
    "--hidden-import=uvicorn.protocols.http",
    "--hidden-import=uvicorn.protocols.http.auto",
    "--hidden-import=uvicorn.protocols.http.h11_impl",
    "--hidden-import=uvicorn.protocols.websockets",
    "--hidden-import=uvicorn.protocols.websockets.auto",
    "--hidden-import=uvicorn.lifespan",
    "--hidden-import=uvicorn.lifespan.on",
    "--hidden-import=uvicorn.lifespan.off",
    "--hidden-import=fastapi",
    "--hidden-import=pydantic",
    "--hidden-import=pydantic_settings",
    "--hidden-import=sqlalchemy",
    "--hidden-import=sqlalchemy.dialects.sqlite",
    "--hidden-import=sqlite3",
    "--hidden-import=engine",
    "--hidden-import=engine.api.app",
    # Exclude unused heavy packages that pull in 2.5GB of CUDA DLLs
    "--exclude-module=torch",
    "--exclude-module=torchvision",
    "--exclude-module=torchaudio",
    "--exclude-module=triton",
    "--exclude-module=bitsandbytes",
    "--exclude-module=tensorboard",
    # Add engine directory to search path
    f"--paths={REPO_ROOT}",
    str(REPO_ROOT / "run_engine.py"),
]

print(f"Running command: {' '.join(cmd)}")
result = subprocess.run(cmd, cwd=REPO_ROOT)

if result.returncode != 0:
    print("PyInstaller build failed!")
    sys.exit(result.returncode)

built_dir = DIST_DIR / "panelflow-engine"
built_exe = built_dir / "panelflow-engine.exe"
if not built_exe.exists():
    print(f"Error: Expected output {built_exe} was not found.")
    sys.exit(1)

print(f"Successfully compiled engine runtime to: {built_dir}")

# Deploy to Tauri resources for installer bundling
target_resource_dir = RESOURCES_DIR / "engine_runtime"
if target_resource_dir.exists():
    shutil.rmtree(target_resource_dir)
shutil.copytree(built_dir, target_resource_dir)
print(f"Deployed engine runtime to Tauri resources: {target_resource_dir}")

# Deploy to release folder for standalone portable distribution
target_release_dir = RELEASE_DIR / "engine_runtime"
if target_release_dir.exists():
    shutil.rmtree(target_release_dir)
shutil.copytree(built_dir, target_release_dir)
print(f"Deployed engine runtime to Release folder: {target_release_dir}")

print("=== Standalone Engine Runtime Built Successfully ===")
