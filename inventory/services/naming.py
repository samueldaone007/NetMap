"""Placeholder naming for records that arrive without identifiers."""
from __future__ import annotations

import re

from django.db.models import Max

from ..models import Device

PLACEHOLDER_PREFIX = "UNNAMED"


def next_placeholder_name(prefix: str = PLACEHOLDER_PREFIX) -> str:
    names = Device.objects.filter(name__startswith=f"{prefix}-").values_list(
        "name", flat=True
    )
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for name in names:
        match = pattern.match(name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def placeholder_device_name(hint: str = "") -> str:
    """A readable placeholder from a free-text reference, kept unique."""
    hint = (hint or "").strip()
    if hint:
        candidate = f"{hint} (unverified)"
        if len(candidate) > 190:
            candidate = candidate[:190].rstrip()
        base = candidate
        suffix = 2
        while Device.objects.filter(name=candidate).exists():
            candidate = f"{base} {suffix}"
            suffix += 1
        return candidate
    return next_placeholder_name()
