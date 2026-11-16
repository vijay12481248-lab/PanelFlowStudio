"""Audience-intelligence metric math. Unknown stays unknown: every function returns None instead of guessing or using 0."""
from statistics import mean, median

THRESHOLDS = (100_000, 500_000, 1_000_000, 10_000_000)


def views_to_subs(views: int | None, subs: int | None) -> float | None:
    """Views / subscribers. None when either is missing or the channel hides/has zero subscribers."""
    if views is None or not subs:
        return None
    return views / subs


def summarize(views: list[int | None]) -> dict:
    """Average, median, top-10 average and the share of videos over each view threshold. Videos with unknown views are not counted."""
    v = sorted((x for x in views if x is not None), reverse=True)
    if not v:
        return {"n": 0, "mean": None, "median": None, "top10_mean": None, "share_over": {t: None for t in THRESHOLDS}}
    return {"n": len(v), "mean": mean(v), "median": median(v), "top10_mean": mean(v[:10]),
            "share_over": {t: sum(x >= t for x in v) / len(v) for t in THRESHOLDS}}


def outlier_score(video_views: int | None, channel_views: list[int | None]) -> float | None:
    """How far one video beat its own channel: views / the channel's median views."""
    med = summarize(channel_views)["median"]
    if video_views is None or not med:
        return None
    return video_views / med
