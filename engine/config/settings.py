import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

def _get_default_app_data() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "PanelFlow Studio"
    return Path.home() / ".panelflow"

class Settings(BaseSettings):
    app_name: str = "PanelFlow Studio"
    version: str = "1.0.0-beta.2"
    
    # Application State Directory (database, logs, config, cache)
    app_data_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("PANELFLOW_APP_DATA", str(_get_default_app_data())))
    )
    
    # Default Workspace Root for projects (when not explicitly chosen by user)
    workspace_root: Path = Field(
        default_factory=lambda: Path(os.getenv("PANELFLOW_WORKSPACE_ROOT", str(_get_default_app_data() / "projects")))
    )
    database_url: str | None = None
    
    # Engine Network & API
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8765",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8765",
        "tauri://localhost",
        "https://tauri.localhost",
        "http://tauri.localhost",
        "https://localhost",
    ]
    
    # Acquisition & Safety Limits
    max_concurrent_downloads: int = 4
    download_timeout_seconds: float = 30.0
    max_download_bytes_per_file: int = 50 * 1024 * 1024  # 50 MB
    rate_limit_delay_seconds: float = 0.2
    max_retries: int = 3
    retry_backoff_factor: float = 1.5
    
    # Image constraints
    allowed_image_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    allowed_mime_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
    )

    model_config = SettingsConfigDict(
        env_prefix="PANELFLOW_",
        arbitrary_types_allowed=True,
    )
    
    @property
    def database_dir(self) -> Path:
        d = self.app_data_dir / "database"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def logs_dir(self) -> Path:
        d = self.app_data_dir / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def db_file_path(self) -> Path:
        return self.database_dir / "panelflow.db"

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.database_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_file_path.as_posix()}"


settings = Settings()
