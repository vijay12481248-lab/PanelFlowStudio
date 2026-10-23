import argparse
import hashlib
import json
import os
import secrets
import socket
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist_engine"
RESOURCES_DIR = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "resources"
RELEASE_DIR = REPO_ROOT / "release"

def validate_runtime(directory: Path) -> Path:
    """Reject partial onedir output before it can reach an installer."""
    executable = directory / ("panelflow-engine.exe" if sys.platform == "win32" else "panelflow-engine")
    if not executable.is_file() or executable.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty standalone executable: {executable}")
    internal = directory / "_internal"
    if not internal.is_dir() or not any(internal.iterdir()):
        raise RuntimeError(f"Missing onedir dependencies: {internal}")
    return executable


def smoke_runtime(directory: Path, *, scratch_root: Path, timeout: float = 90.0) -> dict:
    """Cold-start the exact artifact, never the user's engine or database.

    All state and logs stay under scratch_root; the launch token exists only in
    memory/the child's environment. No repository cwd or ambient Python path.
    """
    executable = validate_runtime(directory).resolve()
    scratch_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="coldstart-", dir=scratch_root))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    if port == 8765:
        raise RuntimeError("Refusing to probe the user's engine port")
    token = secrets.token_urlsafe(48)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PANELFLOW_") and key not in {"PYTHONHOME", "PYTHONPATH"}}
    env.update(PANELFLOW_APP_DATA=str(work / "data"), PANELFLOW_WORKSPACE_ROOT=str(work / "workspace"),
               PANELFLOW_API_HOST="127.0.0.1", PANELFLOW_API_PORT=str(port), PANELFLOW_ENGINE_TOKEN=token,
               LOCALAPPDATA=str(work / "local"))
    base_url = f"http://127.0.0.1:{port}"
    # Proxy configuration must not route a local acceptance request externally.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path: str, *, authenticated: bool = True):
        headers = {"X-PanelFlow-Token": token} if authenticated else {}
        request = urllib.request.Request(base_url + path, headers=headers)
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    log_path = work / "engine.log"
    report = {"executable": str(executable), "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "executable_bytes": executable.stat().st_size, "scratch": str(work), "port": port}
    with log_path.open("wb") as log:
        process = subprocess.Popen([str(executable)], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Frozen engine exited with {process.returncode}; see {log_path}")
                try:
                    status, health = get("/api/system/health", authenticated=False)
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError(f"Frozen engine failed to become healthy; see {log_path}")
            if health.get("status") != "healthy" or health.get("app") != "PanelFlow Studio":
                raise RuntimeError(f"Unexpected engine health response; see {log_path}")
            if Path(health.get("workspace_root", "")).resolve() != (work / "workspace").resolve():
                raise RuntimeError("Frozen engine did not use its isolated workspace")
            report["health"] = {"status": status, "body": health}
            status, _ = get("/api/projects", authenticated=False)
            if status != 401:
                raise RuntimeError(f"Unauthenticated projects returned {status}, expected 401")
            report["unauthenticated_projects_status"] = status
            for name, path in (("projects", "/api/projects"), ("jobs", "/api/jobs"), ("openapi", "/openapi.json")):
                status, body = get(path)
                if status != 200:
                    raise RuntimeError(f"Authenticated {path} returned {status}")
                if name in {"projects", "jobs"} and body != []:
                    raise RuntimeError(f"Isolated {name} inventory was not empty")
                if name == "openapi" and "/api/projects" not in body.get("paths", {}):
                    raise RuntimeError("Frozen OpenAPI document is missing project routes")
                report[name] = {"status": status, "count": len(body["paths"]) if name == "openapi" else len(body)}
            database = work / "data/database/panelflow.db"
            if not database.is_file():
                raise RuntimeError("Frozen engine did not create its isolated database")
            with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
                report["database_tables"] = sorted(row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"))
            if not {"projects", "jobs", "panels"}.issubset(report["database_tables"]):
                raise RuntimeError("Frozen engine database schema is incomplete")
        finally:
            # Only terminate the child we launched; never use process-name killing.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
    report["log"] = str(log_path)
    (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Build and cold-start gate the standalone engine")
    parser.add_argument("--verify-only", type=Path, help="Verify an existing onedir runtime without rebuilding")
    parser.add_argument("--scratch-root", type=Path, default=REPO_ROOT / "build_engine" / "smoke")
    args = parser.parse_args(argv)
    if args.verify_only is not None:
        print(json.dumps(smoke_runtime(args.verify_only, scratch_root=args.scratch_root), indent=2))
        return
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
        "--hidden-import=engine.imaging.redaction",
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
    validate_runtime(built_dir)
    build_report = smoke_runtime(built_dir, scratch_root=args.scratch_root)
    print(json.dumps({"built_runtime_verification": build_report}, indent=2))

    print(f"Successfully compiled engine runtime to: {built_dir}")

    # Deploy to Tauri resources for installer bundling
    target_resource_dir = RESOURCES_DIR / "engine_runtime"
    if target_resource_dir.exists():
        shutil.rmtree(target_resource_dir)
    shutil.copytree(built_dir, target_resource_dir)
    validate_runtime(target_resource_dir)
    print(f"Deployed engine runtime to Tauri resources: {target_resource_dir}")

    # Deploy to release folder for standalone portable distribution
    target_release_dir = RELEASE_DIR / "engine_runtime"
    if target_release_dir.exists():
        shutil.rmtree(target_release_dir)
    shutil.copytree(built_dir, target_release_dir)
    validate_runtime(target_release_dir)
    print(f"Deployed engine runtime to Release folder: {target_release_dir}")

    resource_report = smoke_runtime(target_resource_dir, scratch_root=args.scratch_root)
    (RELEASE_DIR / "engine_runtime_verification.json").write_text(
        json.dumps(resource_report, indent=2), encoding="utf-8")
    print(json.dumps({"installer_resource_verification": resource_report}, indent=2))
    print("=== Standalone Engine Runtime Built Successfully ===")


if __name__ == "__main__":
    main()
