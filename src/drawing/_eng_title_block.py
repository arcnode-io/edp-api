"""Title block + sheet frame shared by ARCNODE engineering deliverables.

ISO 5457 sheet frame + a simplified ISO 7200 title block in the bottom-
right corner. Sheet origin (0,0) at bottom-left; A3 landscape is 420x297
mm. Title block: 200mm wide x 50mm tall, bottom-right corner. Extra
height (vs the v1 SLD's 4-row block) accommodates the ARCNODE logo glyph
to the left of the text column.

Title block layout (left-to-right):
- 30mm strip: ARCNODE logo glyph (vector from `_arcnode_logo`).
- ~170mm text column, 4 rows top-to-bottom:
    - Title (e.g. "SINGLE LINE DIAGRAM", "P&ID — COOLANT SYSTEM").
    - Deployment UUID — drawing-trace handle for engineering review.
    - Profile slug + generated_at timestamp.
    - "sheet n/m    scale: NTS    rev: A".
"""

from datetime import UTC, datetime

from ezdxf.layouts import Modelspace

from src.drawing._arcnode_logo import arcnode_logo_polylines
from src.shared.schemas.dtm import Dtm

_SHEET_WIDTH: float = 420.0
_SHEET_HEIGHT: float = 297.0
_FRAME_INSET: float = 5.0

_TITLE_BLOCK_WIDTH: float = 200.0
_TITLE_BLOCK_HEIGHT: float = 50.0
_LOGO_STRIP_WIDTH: float = 30.0


def draw_sheet_frame(msp: Modelspace) -> None:
    """ISO 5457-style rectangular border, 5mm inset from sheet edges."""
    inset = _FRAME_INSET
    msp.add_lwpolyline(
        [
            (inset, inset),
            (_SHEET_WIDTH - inset, inset),
            (_SHEET_WIDTH - inset, _SHEET_HEIGHT - inset),
            (inset, _SHEET_HEIGHT - inset),
        ],
        close=True,
        dxfattribs={"layer": "FRAME"},
    )


def draw_title_block(
    msp: Modelspace,
    dtm: Dtm,
    *,
    title: str,
    profile: str,
    sheet_n: int = 1,
    sheet_m: int = 1,
) -> None:
    """ISO 7200-lite title block + ARCNODE logo glyph in the bottom-right corner.

    Args:
        msp: ezdxf modelspace to draw into.
        dtm: deployment DTM. Only `deployment_uuid` is read here so reviewers
             can trace the drawing back to its source.
        title: drawing title, e.g. "SINGLE LINE DIAGRAM" or
               "P&ID  —  COOLANT SYSTEM (RACK-INTERNAL)".
        profile: deployment profile slug (label-only).
        sheet_n: 1-based sheet number on this drawing.
        sheet_m: total sheets on this drawing.
    """
    right = _SHEET_WIDTH - _FRAME_INSET
    bottom = _FRAME_INSET
    left = right - _TITLE_BLOCK_WIDTH
    top = bottom + _TITLE_BLOCK_HEIGHT
    text_left = left + _LOGO_STRIP_WIDTH

    # Outer rectangle.
    msp.add_lwpolyline(
        [(left, bottom), (right, bottom), (right, top), (left, top)],
        close=True,
        dxfattribs={"layer": "TITLE_BLOCK"},
    )
    # Vertical divider separating the logo strip from the text column.
    msp.add_line(
        start=(text_left, bottom),
        end=(text_left, top),
        dxfattribs={"layer": "TITLE_BLOCK"},
    )

    # 4 horizontal rows in the text column.
    text_column_width = right - text_left
    row_height = _TITLE_BLOCK_HEIGHT / 4
    for i in range(1, 4):
        y = bottom + i * row_height
        msp.add_line(
            start=(text_left, y),
            end=(right, y),
            dxfattribs={"layer": "TITLE_BLOCK"},
        )

    _draw_logo(msp, left=left, bottom=bottom)

    # ISO 8601 to keep the row width predictable; UTC implicit per ISO.
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    rows = [
        f"ARCNODE — {title}",
        f"deployment: {dtm.deployment_uuid}",
        f"profile: {profile}   generated: {generated_at}",
        f"sheet {sheet_n}/{sheet_m}   scale: NTS   rev: A",
    ]
    # Title gets ~4.4mm; body ~2.8mm — fits a 60-char body row in 167mm column.
    title_height = row_height * 0.35
    body_height = row_height * 0.22
    for i, text in enumerate(rows):
        height = title_height if i == 0 else body_height
        y = top - (i + 0.5) * row_height
        msp.add_mtext(
            text,
            dxfattribs={
                "layer": "TITLE_BLOCK",
                "char_height": height,
                "insert": (text_left + 3, y),
                # 4 = middle-left attachment — anchors text vertical center
                # to insert.y, left edge to insert.x.
                "attachment_point": 4,
                "width": text_column_width - 6,
            },
        )


def _draw_logo(msp: Modelspace, *, left: float, bottom: float) -> None:
    """Place the ARCNODE glyph in the logo strip — left edge of the title block.

    Source path coordinates from `_arcnode_logo` come out of a (60..180) box
    (after the source SVG's translate+scale). We re-fit to the logo strip
    here and flip y (SVG y points down; DXF/model y points up).
    """
    contours = arcnode_logo_polylines()
    if not contours:
        return

    xs = [p[0] for c in contours for p in c]
    ys = [p[1] for c in contours for p in c]
    src_min_x, src_max_x = min(xs), max(xs)
    src_min_y, src_max_y = min(ys), max(ys)
    src_w = src_max_x - src_min_x
    src_h = src_max_y - src_min_y

    # Fit the glyph into the logo strip with a 3mm margin all around.
    margin = 3.0
    dst_w = _LOGO_STRIP_WIDTH - 2 * margin
    dst_h = _TITLE_BLOCK_HEIGHT - 2 * margin
    scale = min(dst_w / src_w, dst_h / src_h)

    # Center the glyph horizontally + vertically inside the strip.
    glyph_w = src_w * scale
    glyph_h = src_h * scale
    x_offset = left + margin + (dst_w - glyph_w) / 2
    y_offset = bottom + margin + (dst_h - glyph_h) / 2

    for contour in contours:
        points = [
            (
                x_offset + (p[0] - src_min_x) * scale,
                # Flip y: SVG +y is down, DXF +y is up.
                y_offset + (src_max_y - p[1]) * scale,
            )
            for p in contour
        ]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "TITLE_BLOCK"})
