"""Report scanlator promotion visible in a rendered video. Usage: python scripts/check_video_promo.py <video.mp4> [every_sec]"""
import sys

from engine.render.promo_gate import describe_hits, scan_video_for_promotion

if __name__ == "__main__":
    hits = scan_video_for_promotion(sys.argv[1], every_sec=float(sys.argv[2]) if len(sys.argv) > 2 else 1.0)
    print(describe_hits(hits, limit=50) if hits else "No promotional text found.")
    sys.exit(1 if hits else 0)
