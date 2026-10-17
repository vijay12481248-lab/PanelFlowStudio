from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    app_name: str = "PanelFlow Studio"
    version: str = "1.0.0-beta.1"
    
    # Workspace & Database
    workspace_root: Path = Field(
        default_factory=lambda: Path(os.getenv("PANELFLOW_WORKSPACE_ROOT", str(Path.home() / ".panelflow" / "workspaces")))
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
    def db_file_path(self) -> Path:
        return self.workspace_root / "panelflow.db"

    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_file_path.as_posix()}"


settings = Settings()
