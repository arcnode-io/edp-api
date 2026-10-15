"""The sheet's drawing area: everything inside the frame except the title block.

Every engineering sheet (SLD, comms, P&ID, ...) lays out inside this area.
`bind_to_drawing_area` is the guard each service runs before serializing:
if any content entity crosses the border or the title block, all content
on the sheet is scaled down (never up) and moved into the band above the
title block. `violations` is what the guard and the tests check.
"""

from collections.abc import Iterable
from typing import Final

from ezdxf import bbox
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Modelspace
from ezdxf.math import Matrix44

from src.drawing._eng_title_block import (
    FRAME_INSET_MM,
    SHEET_H_MM,
    SHEET_W_MM,
    TITLE_BLOCK_H_MM,
    TITLE_BLOCK_W_MM,
)

# (xmin, ymin, xmax, ymax) in sheet mm
Rect = tuple[float, float, float, float]

_FRAME_LAYERS: Final[frozenset[str]] = frozenset({"FRAME", "TITLE_BLOCK"})
_MARGIN_MM: Final[float] = 2.0
_TOLERANCE_MM: Final[float] = 1e-6
# Inside the border, with a margin so nothing touches the frame line.
FRAME_INNER: Final[Rect] = (
    FRAME_INSET_MM + _MARGIN_MM,
    FRAME_INSET_MM + _MARGIN_MM,
    SHEET_W_MM - FRAME_INSET_MM - _MARGIN_MM,
    SHEET_H_MM - FRAME_INSET_MM - _MARGIN_MM,
)
# Title block in the bottom-right corner, grown by the margin.
TITLE_KEEPOUT: Final[Rect] = (
    SHEET_W_MM - FRAME_INSET_MM - TITLE_BLOCK_W_MM - _MARGIN_MM,
    FRAME_INSET_MM,
    SHEET_W_MM - FRAME_INSET_MM,
    FRAME_INSET_MM + TITLE_BLOCK_H_MM + _MARGIN_MM,
)
# Where overflowing content is fitted: the full-width band above the title block.
_FIT_AREA: Final[Rect] = (
    FRAME_INNER[0],
    TITLE_KEEPOUT[3] + _MARGIN_MM,
    FRAME_INNER[2],
    FRAME_INNER[3],
)


def violations(entities: Iterable[DXFGraphic], dx: float = 0.0) -> list[str]:
    """Content entities that cross the border or the title block.

    Args:
        entities: A sheet's entities (a modelspace, or one sheet's share of
            a multi-sheet DXF).
        dx: x offset of this sheet in the modelspace (multi-sheet DXF lays
            sheets left to right).
    """
    found = []
    for entity in _content(entities):
        rect = _rect(entity, dx)
        if rect is None:
            continue
        if not _inside(rect, FRAME_INNER) or _overlaps(rect, TITLE_KEEPOUT):
            found.append(f"{entity.dxftype()} on {entity.dxf.layer} at {rect}")
    return found


def bind_to_drawing_area(msp: Modelspace) -> None:
    """Scale and move all content into the drawing area if any of it escapes.

    Raises:
        ValueError: If content still escapes after fitting.
    """
    if not violations(msp):
        return
    content = list(_content(msp))
    extents = bbox.extents(content)
    (x0, y0, _), (x1, y1, _) = extents.extmin, extents.extmax
    fx0, fy0, fx1, fy1 = _FIT_AREA
    # Reason: a dimension with no extent (a lone straight line) puts no limit
    # on the scale.
    limits = [
        (fx1 - fx0) / (x1 - x0) if x1 > x0 else 1.0,
        (fy1 - fy0) / (y1 - y0) if y1 > y0 else 1.0,
    ]
    scale = min(1.0, *limits)
    # Reason: anchor top-left so a scaled sheet still reads top-down.
    matrix = (
        Matrix44.translate(-x0, -y1, 0)
        @ Matrix44.scale(scale)
        @ Matrix44.translate(fx0, fy1, 0)
    )
    for entity in content:
        entity.transform(matrix)
    left = violations(msp)
    if left:
        raise ValueError(f"content still outside the drawing area: {left[:3]}")


def _content(entities: Iterable[DXFGraphic]) -> list[DXFGraphic]:
    return [e for e in entities if e.dxf.layer not in _FRAME_LAYERS]


def _rect(entity: DXFGraphic, dx: float) -> Rect | None:
    box = bbox.extents([entity])
    if not box.has_data:
        return None
    return (box.extmin.x - dx, box.extmin.y, box.extmax.x - dx, box.extmax.y)


def _inside(r: Rect, outer: Rect) -> bool:
    # Reason: fitting scales content exactly onto the edge, and the transform
    # lands it a float rounding error past it (413.00000000000006 vs 413).
    t = _TOLERANCE_MM
    return (
        r[0] >= outer[0] - t
        and r[1] >= outer[1] - t
        and r[2] <= outer[2] + t
        and r[3] <= outer[3] + t
    )


def _overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
