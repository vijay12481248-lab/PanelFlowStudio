from PIL import Image
from pathlib import Path

im = Image.open("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/sam_spritesheet_transparent.png")
out_dir = Path("C:/Users/user/.gemini/antigravity/scratch/stupid-zombies-analysis/game_assets/sam_sprites")

# Dimensions: 1920 x 1280
# 3 rows, roughly 6 columns per row
col_w = 1920 // 6 # 320px
row_h = 1280 // 3 # ~426px

labels = [
    ["idle_01", "idle_02", "idle_03", "idle_04", "idle_05", "idle_06"],
    ["run_01", "run_02", "run_03", "run_04", "jump_01", "jump_02"],
    ["aim_01", "aim_02", "aim_03", "jump_crouch_01", "jump_crouch_02", "jump_land"]
]

for r in range(3):
    for c in range(6):
        box = (c * col_w, r * row_h, (c + 1) * col_w, (r + 1) * row_h)
        frame = im.crop(box)
        # Trim transparent borders if needed
        bbox = frame.getbbox()
        if bbox:
            cropped = frame.crop(bbox)
            name = labels[r][c]
            cropped.save(out_dir / f"{name}.png")
            print(f"Saved: {name}.png ({cropped.size[0]}x{cropped.size[1]})")

print("All frames successfully extracted!")
