import io
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw

def create_sample_comic_page(page_num: int, title: str = "Captain Cosmos #1") -> bytes:
    width, height = 1200, 1800
    img = Image.new("RGB", (width, height), color="#0f172a")
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([20, 20, width - 20, height - 20], outline="#38bdf8", width=4)

    # Title Banner
    draw.rectangle([40, 40, width - 40, 140], fill="#1e293b", outline="#64748b", width=2)
    draw.text((60, 75), f"{title} - PAGE {page_num:02d}", fill="#f8fafc")

    # Panel 1 (Top Left)
    draw.rectangle([50, 170, 570, 750], fill="#1e1e2e", outline="#f43f5e", width=4)
    draw.text((80, 200), f"PANEL 1: The Cosmic Rift opens...", fill="#fda4af")
    # Draw simple illustration shapes
    draw.ellipse([200, 350, 420, 570], fill="#881337", outline="#f43f5e", width=3)

    # Panel 2 (Top Right)
    draw.rectangle([610, 170, 1150, 750], fill="#1e1e2e", outline="#3b82f6", width=4)
    draw.text((640, 200), f"PANEL 2: Resonance Pulse Detected", fill="#93c5fd")
    draw.polygon([(880, 300), (750, 600), (1010, 600)], fill="#1e3a8a", outline="#60a5fa", width=3)

    # Panel 3 (Bottom Full Width)
    draw.rectangle([50, 790, 1150, 1700], fill="#18181b", outline="#10b981", width=4)
    draw.text((80, 820), f"PANEL 3: Hero steps onto the crystalline platform", fill="#6ee7b7")
    draw.rectangle([350, 1100, 850, 1550], fill="#064e3b", outline="#34d399", width=3)

    # Footer sequence label
    draw.text((width // 2 - 30, height - 50), f"- {page_num} -", fill="#94a3b8")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def main():
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    folder_dir = fixtures_dir / "sample_comic"
    folder_dir.mkdir(parents=True, exist_ok=True)

    zip_path = fixtures_dir / "sample_comic.cbz"
    zip_entries = {}

    print("Generating sample comic fixtures...")
    for i in range(1, 6):
        data = create_sample_comic_page(i)
        filename = f"page_{i:02d}.jpg"
        (folder_dir / filename).write_bytes(data)
        zip_entries[f"chapter_01/{filename}"] = data
        print(f"Generated {filename} ({len(data)} bytes)")

    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in zip_entries.items():
            zf.writestr(name, data)
    print(f"Generated sample archive: {zip_path}")

if __name__ == "__main__":
    main()
