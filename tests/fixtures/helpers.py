import io
import zipfile
from pathlib import Path
from PIL import Image

def create_test_image_bytes(width: int = 100, height: int = 100, color: str = "blue", format: str = "JPEG") -> bytes:
    """Generates valid image bytes in memory."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()

def create_test_zip_archive(target_path: Path, files: dict[str, bytes]) -> Path:
    """Creates a zip archive on disk with the given internal filename -> bytes mapping."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return target_path
