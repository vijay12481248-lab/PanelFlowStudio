from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, Field

class DialogueLine(BaseModel):
    id: str
    panel_id: str | None = None
    speaker: str = "narrator"
    emotion: str = "neutral"  # neutral, whisper, angry, gasp, surprised, sad
    text: str
    pause_before: float = 0.0
    pause_after: float = 0.5
    importance: float = 1.0

class TTSEngine(ABC):
    @property
    @abstractmethod
    def engine_id(self) -> str:
        pass

    @abstractmethod
    async def synthesize_line(self, line: DialogueLine, voice_id: str, output_path: Path) -> dict:
        """Synthesizes speech per line to avoid monolithic audio clutter."""
        pass
