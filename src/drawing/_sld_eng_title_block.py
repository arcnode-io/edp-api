"""Title block + sheet frame for the engineering SLD.

ISO 5457 sheet frame + a simplified ISO 7200 title block in the bottom-
right corner. Sheet origin (0,0) at bottom-left; A3 landscape is 420x297
mm. Title block: 180mm wide x 40mm tall, bottom-right corner.

Title block rows (top → bottom):
- "ARCNODE — SINGLE LINE DIAGRAM" (title)
- Deployment UUID (drawing-trace handle for engineering review)
- Profile name + generated_at timestamp
- Sheet / scale / revision (1/1, NTS, A)

Sheet frame: 5mm inset border around the full sheet, with the title
block tucked inside the lower-right corner.
"""

from datetime import UTC, datetime

from ezdxf.layouts import Modelspace

from src.shared.schemas.dtm import Dtm

_SHEET_WIDTH: float = 420.0
_SHEET_HEIGHT: float = 297.0
_FRAME_INSET: float = 5.0

_TITLE_BLOCK_WIDTH: float = 180.0
_TITLE_BLOCK_HEIGHT: float = 40.0


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


def draw_title_block(msp: Modelspace, dtm: Dtm, profile: str) -> None:
    """ISO 7200-lite title block in the bottom-right corner.

    `profile` is the deployment profile slug (e.g. "commercial_ac"). The
    DTM doesn't carry it directly; the caller (SldEngineeringService) has
    it from the surrounding context.
    """
    right = _SHEET_WIDTH - _FRAME_INSET
    bottom = _FRAME_INSET
    left = right - _TITLE_BLOCK_WIDTH
    top = bottom + _TITLE_BLOCK_HEIGHT

    # Outer rectangle for the title block.
    msp.add_lwpolyline(
        [(left, bottom), (right, bottom), (right, top), (left, top)],
        close=True,
        dxfattribs={"layer": "TITLE_BLOCK"},
    )
    # 4 horizontal dividers => 4 rows of content.
    row_height = _TITLE_BLOCK_HEIGHT / 4
    for i in range(1, 4):
        y = bottom + i * row_height
        msp.add_line(
            start=(left, y), end=(right, y), dxfattribs={"layer": "TITLE_BLOCK"}
        )

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    rows = [
        "ARCNODE  —  SINGLE LINE DIAGRAM",
        f"deployment: {dtm.deployment_uuid}",
        f"profile: {profile}    generated: {generated_at}",
        "sheet 1/1    scale: NTS    rev: A",
    ]
    text_height = row_height * 0.35
    for i, text in enumerate(rows):
        # Top row is the title — slightly larger.
        height = text_height * (1.4 if i == 0 else 1.0)
        # i=0 is the top row, place it just below `top`; bottom row near `bottom`.
        y = top - (i + 0.5) * row_height
        msp.add_mtext(
            text,
            dxfattribs={
                "layer": "TITLE_BLOCK",
                "char_height": height,
                "insert": (left + 3, y),
                "attachment_point": 4,  # 4 = middle-left, anchors text vertical-center to insert.y
            },
        )
