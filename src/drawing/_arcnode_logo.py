"""ARCNODE wordmark glyph loader — SVG path -> polyline contours.

Source asset: `assets/arcnode_logo_source.svg` (copied verbatim from
`~/arcnode/website/assets/banner.svg`). Only the glyph path is consumed
here; the banner's text + tagline + rule line are ignored — title-block
text is already rendered by `_eng_title_block.py`.

Output is suitable for ezdxf LWPOLYLINE entities (caller scales +
translates into the title-block region). Coordinates are in the SVG
path's local coordinate space after applying the source `<g transform>`
(roughly 60..180 in both axes). SVG y-axis points down; caller flips for
DXF if model-space y is up.

Cubic-bezier segments are approximated with line samples per
`_BEZIER_SAMPLES` (24 per segment — sufficient resolution at the
title-block scale; tightens linearly with sample count if needed).
"""

from functools import cache
from pathlib import Path
from typing import Final

import numpy as np
from svgpathtools import CubicBezier, Line, parse_path
from svgpathtools.parser import parse_transform

_ASSET_PATH: Final[Path] = Path(__file__).parent / "assets" / "arcnode_logo_source.svg"
_BEZIER_SAMPLES: Final[int] = 24


@cache
def arcnode_logo_polylines() -> tuple[tuple[tuple[float, float], ...], ...]:
    """Return immutable nested tuples of (x, y) per polyline contour.

    Cached: parse + sample happens once per process. Tuples (not lists) so
    the cached value can't be mutated by an accidental caller.
    """
    d, transform_matrix = _extract_path_and_transform(_ASSET_PATH.read_text())
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    path = parse_path(d)
    for seg in path:
        # New M (move) implies a fresh subpath; flush current if non-empty.
        if isinstance(seg, Line | CubicBezier):
            if not current or _far(current[-1], _xy(seg.start, transform_matrix)):
                if current:
                    contours.append(current)
                current = [_xy(seg.start, transform_matrix)]
            samples = _BEZIER_SAMPLES if isinstance(seg, CubicBezier) else 2
            for i in range(1, samples):
                t = i / (samples - 1)
                current.append(_xy(seg.point(t), transform_matrix))
        else:
            # Arc / QuadraticBezier / etc not in this glyph; fail loud if added.
            raise NotImplementedError(f"unsupported segment type: {type(seg).__name__}")

    if current:
        contours.append(current)

    return tuple(tuple(c) for c in contours)


def _extract_path_and_transform(
    svg_text: str,
) -> tuple[str, "np.ndarray"]:
    """Pull the logo path's `d` + its enclosing group's transform matrix.

    Banner SVG wraps the glyph in `<g transform="translate(60,30) scale(0.234)">`
    around `<path class="logo" d="...">`. We only care about the glyph; the
    text / tagline are drawn by the title block itself.

    Returns the raw `d` string and a 3x3 affine matrix per svgpathtools
    convention — `_xy()` applies it to each parsed point.
    """
    # Hand-extract — full XML parsing would also pull text we don't want
    # and adds an unnecessary stdlib dep surface here.
    d = _between(svg_text, 'class="logo" d="', '"')
    transform = _between(svg_text, '<g transform="', '"')
    return d, parse_transform(transform)


def _between(haystack: str, start: str, end: str) -> str:
    """Tiny no-regex slice helper. Raises if either marker isn't found."""
    s = haystack.index(start) + len(start)
    e = haystack.index(end, s)
    return haystack[s:e]


def _xy(point: complex, matrix: "np.ndarray") -> tuple[float, float]:
    """Apply svgpathtools 3x3 affine matrix to (re(p), im(p))."""
    x, y = point.real, point.imag
    v = matrix @ np.array([x, y, 1.0])
    return (float(v[0]), float(v[1]))


def _far(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
    """True if two points are non-coincident — distinguishes a new subpath."""
    return abs(p1[0] - p2[0]) > 1e-6 or abs(p1[1] - p2[1]) > 1e-6
