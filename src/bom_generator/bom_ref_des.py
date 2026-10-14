"""Reference designators for BOM lines: which devices a line covers.

Tags come from each container's equipment list (bom.yaml `tags`), so the
BOM names the same devices as the drawings and the device data. A site
tag is the container plus the local tag (C3-NODE-5); a line covering
many containers lists the container range once.
"""

import re

_NUMBERED = re.compile(r"^(.*?)(\d+)$")

# (container prefix "C"/"G", first number, last number, container-local tags)
Group = tuple[str, int, int, list[str]]


def ref_des(groups: list[Group]) -> str:
    """Tags per container range, e.g. "C1-C10: NODE-1…7".

    Groups holding the same tags merge into one range (G1 primary and
    G2-G3 feeders both holding RLY-1 → "G1-G3: RLY-1").
    """
    if len({tuple(tags) for *_, tags in groups}) == 1:
        prefix, first, _, tags = groups[0]
        groups = [(prefix, first, groups[-1][2], tags)]
    return "; ".join(
        f"{containers(prefix, first, last)}: {compress(tags)}"
        for prefix, first, last, tags in groups
        if tags
    )


def containers(prefix: str, first: int, last: int) -> str:
    """Container range label: C1, or C1-C10 for several."""
    return f"{prefix}{first}" if first == last else f"{prefix}{first}-{prefix}{last}"


def compress(tags: list[str]) -> str:
    """Consecutive numbered tags collapse: NODE-1..NODE-7 → "NODE-1…7"."""
    runs: list[list[str]] = []
    for tag in tags:
        if runs and _follows(runs[-1][-1], tag):
            runs[-1].append(tag)
        else:
            runs.append([tag])
    return ", ".join(r[0] if len(r) == 1 else f"{r[0]}…{_tail(r[-1])}" for r in runs)


def _follows(prev: str, tag: str) -> bool:
    a, b = _NUMBERED.match(prev), _NUMBERED.match(tag)
    return bool(a and b and a[1] == b[1] and int(b[2]) == int(a[2]) + 1)


def _tail(tag: str) -> str:
    """The part after the last hyphen: NODE-7 → "7", PDU-A3 → "A3"."""
    return tag.rsplit("-", 1)[-1]
