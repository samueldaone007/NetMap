"""Port label helpers shared by paste import and spreadsheet import."""
from __future__ import annotations

import re

_RANGE = re.compile(r"^(?P<prefix>.*?)(?P<start>\d+)\s*[-–—]\s*(?P<end>\d+)$")


def expand_port_labels(raw) -> list[str]:
    """Expand a label, range or comma list into individual port labels.

    Examples:
        "LAN2-7" -> LAN2 … LAN7
        "19,20" -> 19, 20
        "4,5,7-12" -> 4, 5, 7 … 12
        "Gi1/0/1-4" -> Gi1/0/1 … Gi1/0/4
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []

    labels: list[str] = []
    for part in re.split(r"\s*[,;]\s*", text):
        part = part.strip()
        if not part:
            continue
        match = _RANGE.match(part)
        if not match:
            labels.append(part)
            continue
        prefix = match.group("prefix")
        start_text = match.group("start")
        end_text = match.group("end")
        start = int(start_text)
        end = int(end_text)
        if end < start:
            # Not a sensible range; keep the literal text so validation can explain it.
            labels.append(part)
            continue
        width = len(start_text) if start_text.startswith("0") else 0
        for number in range(start, end + 1):
            labels.append(f"{prefix}{number:0{width}d}" if width else f"{prefix}{number}")

    seen = set()
    unique = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            unique.append(label)
    return unique
