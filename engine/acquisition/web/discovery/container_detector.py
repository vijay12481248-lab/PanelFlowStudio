"""
Reader container discovery and structural confidence evaluator.
Identifies probable chapter content containers without relying solely on brittle class names.
"""
import re
from typing import Dict, Any, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

READER_CLASS_HINTS = re.compile(
    r"(reader|chapter-content|chapter-images|manga-container|webtoon-viewer|comic-page|reading-content|viewer-cnt)",
    re.IGNORECASE,
)
NEGATIVE_CONTAINER_HINTS = re.compile(
    r"(sidebar|comment|nav|navbar|footer|header|ad-|advertisement|related|recommendation)",
    re.IGNORECASE,
)


class ContainerDetector:
    """
    Evaluates DOM tree elements to identify the dominant reader container.
    """

    def detect_reader_container(self, soup: BeautifulSoup) -> Tuple[Optional[Tag], float, str]:
        """
        Scans DOM tree and scores container candidates based on image density,
        structural repetition, and semantic signals.
        Returns (best_container_tag, confidence, container_signature).
        """
        # Look at containers that hold multiple <img> or picture elements
        potential_tags = soup.find_all(["div", "article", "main", "section", "figure"])
        scored_containers: List[Tuple[Tag, float, str]] = []

        for container in potential_tags:
            # Check how many direct or nested image elements exist
            images = container.find_all("img")
            img_count = len(images)
            if img_count < 2:
                continue

            score = 0.0
            reasons = []

            # 1. Image count density
            if img_count >= 10:
                score += 0.40
                reasons.append(f"{img_count} images")
            elif img_count >= 5:
                score += 0.30
                reasons.append(f"{img_count} images")
            else:
                score += 0.15

            # 2. Semantic class hints
            class_str = " ".join(container.get("class", []))
            id_str = container.get("id", "")
            combined_id_class = f"{class_str} {id_str}"

            if NEGATIVE_CONTAINER_HINTS.search(combined_id_class):
                score -= 0.50
                reasons.append("negative container match")

            if READER_CLASS_HINTS.search(combined_id_class):
                score += 0.30
                reasons.append("reader class hint")

            # 3. Ratio of images to text inside container
            text_len = len(container.get_text(strip=True))
            # In a comic reader container, text is minimal relative to images
            if text_len < img_count * 50:
                score += 0.20
                reasons.append("high image-to-text ratio")
            elif text_len > img_count * 500:
                score -= 0.20
                reasons.append("excessive text (likely article/forum)")

            # 4. Sibling structural repetition (images wrapped in similar child divs)
            child_divs = container.find_all(["div", "p"], recursive=False)
            if len(child_divs) >= img_count * 0.7:
                score += 0.10
                reasons.append("repeated sibling child structure")

            # Build a deterministic signature
            tag_name = container.name
            first_class = container.get("class", [""])[0] if container.get("class") else ""
            signature = f"{tag_name}.{first_class}" if first_class else tag_name
            if id_str:
                signature += f"#{id_str}"

            final_conf = max(0.0, min(1.0, round(score, 2)))
            scored_containers.append((container, final_conf, signature))

        if not scored_containers:
            # Fall back to <body> if images exist directly
            body = soup.find("body")
            if body and body.find_all("img"):
                return body, 0.40, "body"
            return None, 0.0, "none"

        # Sort by confidence descending
        scored_containers.sort(key=lambda x: x[1], reverse=True)
        return scored_containers[0]
