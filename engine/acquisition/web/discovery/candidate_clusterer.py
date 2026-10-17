"""
Image candidate clustering engine.
Partitions candidate pool into structural clusters based on host, path hierarchy,
ancestor tree, and dimension consistency.
"""
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
from engine.acquisition.web.models.image_candidate import ImageCandidate, CandidateCluster


class CandidateClusterer:
    """
    Groups individual image candidates into coherent clusters (e.g. Reader Chapter Pages vs Thumbnails vs Avatars).
    """

    def cluster_candidates(self, candidates: List[ImageCandidate]) -> List[CandidateCluster]:
        if not candidates:
            return []

        # 1. Feature key extraction per candidate: (host, path_parent, dom_parent)
        cluster_buckets: Dict[str, List[ImageCandidate]] = {}

        import posixpath
        import re

        for c in candidates:
            parsed = urlparse(c.resolved_url)
            host = parsed.netloc.lower()
            raw_path_parent = posixpath.dirname(parsed.path)
            # Normalize dynamic / date / hash subdirectories in CDN image paths
            norm_path = re.sub(r'/[0-9a-zA-Z_-]{8,}', '/[DYNAMIC]', raw_path_parent)

            dom_parent = c.dom_path or c.parent_tag or "unknown"
            if any(term in dom_parent.lower() for term in ("imagelist", "viewer", "chapter", "comic", "strip", "reader")):
                cluster_key = f"{host}::{dom_parent}::{norm_path}"
            else:
                cluster_key = f"{host}::{norm_path}"

            cluster_buckets.setdefault(cluster_key, []).append(c)

        # 2. Score and build CandidateCluster objects
        clusters: List[CandidateCluster] = []
        cluster_idx = 1

        for key, bucket in cluster_buckets.items():
            cluster_id = f"cluster_{cluster_idx}"
            cluster_idx += 1

            host, path_parent = key.split("::", 1)

            # Assign cluster_id to each candidate
            for c in bucket:
                c.cluster_id = cluster_id

            # Calculate cluster statistics
            widths = [c.natural_width or c.rendered_width for c in bucket if (c.natural_width or c.rendered_width)]
            heights = [c.natural_height or c.rendered_height for c in bucket if (c.natural_height or c.rendered_height)]
            avg_w = sum(widths) / len(widths) if widths else None
            avg_h = sum(heights) / len(heights) if heights else None
            avg_ar = (avg_w / avg_h) if (avg_w and avg_h and avg_h > 0) else None

            # Determine dominant parent
            parents = [c.parent_tag for c in bucket if c.parent_tag]
            dom_p = max(set(parents), key=parents.count) if parents else None

            # Cluster scoring
            score = 0.5
            reasons = []

            count = len(bucket)
            if count >= 10:
                score += 0.35
                reasons.append(f"large cluster size ({count} images)")
            elif count >= 3:
                score += 0.20
                reasons.append(f"moderate cluster size ({count} images)")
            else:
                score -= 0.15
                reasons.append(f"small cluster size ({count} images)")

            # Check dimensions if available
            if avg_w and avg_w >= 600:
                score += 0.15
                reasons.append(f"large average width ({int(avg_w)}px)")
            elif avg_w and avg_w <= 100:
                score -= 0.30
                reasons.append(f"thumbnail average width ({int(avg_w)}px)")

            # Sequential DOM order continuity
            dom_orders = [c.dom_order for c in bucket if c.dom_order > 0]
            if len(dom_orders) >= 3 and dom_orders == sorted(dom_orders):
                score += 0.10
                reasons.append("strictly sequential DOM placement")

            final_score = max(0.0, min(1.0, round(score, 2)))

            clusters.append(
                CandidateCluster(
                    cluster_id=cluster_id,
                    candidates=bucket,
                    dominant_parent=dom_p,
                    common_host=host,
                    common_path_prefix=path_parent,
                    avg_width=avg_w,
                    avg_height=avg_h,
                    avg_aspect_ratio=avg_ar,
                    cluster_score=final_score,
                    cluster_reasons=reasons,
                )
            )

        # Sort clusters by score descending so dominant cluster is first
        clusters.sort(key=lambda cl: cl.cluster_score, reverse=True)
        return clusters
