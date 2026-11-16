"""Which licences the Audio Studio may use for published videos: CC0 always, CC-BY only when the plan allows it."""
from __future__ import annotations

import re

_VERSION = re.compile(r"^\d+(\.\d+)*$")


def licence_allowed(licence: str | None, allow_cc_by: bool) -> bool:
    tokens = [t for t in re.split(r"[\s_/-]+", str(licence or "").strip().lower()) if t and t not in {"cc", "licence", "license"}]
    if not tokens:
        return False
    if tokens[0] in {"cc0", "pdm", "publicdomain", "public", "user", "user-supplied", "mit"} and not {"nc", "sa", "nd"} & set(tokens):
        return True
    if tokens[0] == "by" and all(_VERSION.match(t) for t in tokens[1:]):
        return allow_cc_by  # any NC / SA / ND suffix makes a token that is not a version -> refused
    return False
