import cv2
import numpy as np
from PIL import Image
from pathlib import Path

# Paths
input_path = Path("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/real_mechanic_spritesheet_1.png")
output_dir = Path("C:/Users/user/.gemini/antigravity/scratch/stupid-zombies-analysis/game_assets/sam_sprites")
output_dir.mkdir(parents=True, exist_ok=True)

# 1. Load image and create transparent PNG
im = Image.open(input_path).convert("RGBA")
data = np.array(im)

# Make pure white/near-white transparent (RGB > 245)
r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
white_mask = (r > 240) & (g > 240) & (b > 240)
data[white_mask, 3] = 0

trans_im = Image.fromarray(data)
trans_im.save(output_dir / "sam_spritesheet_transparent.png", "PNG")
print(f"Saved transparent sprite sheet to {output_dir / 'sam_spritesheet_transparent.png'}")

# Also save a copy in brain artifacts for chat display
trans_im.save("C:/Users/user/.gemini/antigravity/brain/914ab523-8f31-4403-99f5-599b1916c18a/sam_spritesheet_transparent.png", "PNG")
