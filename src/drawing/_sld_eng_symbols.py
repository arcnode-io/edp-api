"""IEC 60617 graphical symbols for the engineering SLD.

Each function builds a named block in the ezdxf document — the block can
then be INSERTed any number of times at different positions. Blocks are
authored at the origin (0,0) at unit scale; the INSERT call positions
+ scales them.

Symbol selection is driven by the same IEC 61850 measurement-ref rules
used by the HMI SVG (see `_iec_61850.py`): a device whose template has an
`XCBR.Pos.stVal` / `XSWI.Pos.stVal` measurement renders as a circuit
breaker; everything else picks by template slug; unknown slugs fall back
to a labelled rectangle so nothing is silently dropped.

Symbol geometry follows IEC 60617 conventions:
- Circuit breaker (S00286): circle 6mm radius, contact bar across center.
- Two-winding transformer (S00309): two tangent circles 5mm radius.
- Generator (S00308): circle 6mm radius with "G" inside.
- Switch / disconnector (S00282): hinge dot + diagonal blade.
- Bus bar segment: bold horizontal line.
- Battery (S00306): pairs of long+short lines stacked.
- Meter (S00313): circle 6mm radius with "M" inside (revenue / measurement).
- Fallback: 12x8mm rectangle with template-slug label.
"""

from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout

from src.drawing._iec_61850 import is_breaker_template
from src.shared.schemas.template import DeviceTemplate


def ensure_symbol_block(doc: Drawing, template: DeviceTemplate) -> str:
    """Define (idempotent) the IEC 60617 symbol block for this template.

    Returns the block name so the caller can INSERT it. Same template slug
    always maps to the same block — defined once per doc, INSERTed many.
    """
    block_name = f"sym_{template.template}"
    if block_name in doc.blocks:
        return block_name
    block = doc.blocks.new(name=block_name)
    _author_block(block, template)
    return block_name


def _author_block(block: BlockLayout, template: DeviceTemplate) -> None:
    """Pick the IEC 60617 primitive that fits this template's role."""
    if is_breaker_template(template):
        _circuit_breaker(block)
        return
    match template.template:
        case "switchgear":
            _switch_disconnector(block)
        case "protective_relay":
            _relay(block)
        case "revenue_meter":
            _meter(block, glyph="M")
        case "bess_rack" | "bess_module":
            _battery(block)
        case "gpu_node" | "compute_module":
            _load_block(block, glyph="L")
        case _:
            _fallback_rectangle(block, label=template.template)


def _circuit_breaker(block: BlockLayout) -> None:
    """IEC 60617 S00286 — closed-state circuit breaker."""
    block.add_circle(center=(0, 0), radius=6)
    block.add_line(start=(-6, 0), end=(6, 0))


def _switch_disconnector(block: BlockLayout) -> None:
    """IEC 60617 S00282 — disconnector (hinge + open blade up-right)."""
    block.add_circle(center=(-6, 0), radius=0.5)  # hinge dot
    block.add_line(start=(-6, 0), end=(2, 4))  # blade
    block.add_line(start=(-6, 0), end=(6, 0))  # closed-position reference
    block.add_point(location=(6, 0))


def _relay(block: BlockLayout) -> None:
    """Protective relay — IEC convention: square with diagonal cross."""
    block.add_lwpolyline([(-5, -5), (5, -5), (5, 5), (-5, 5)], close=True)
    block.add_line(start=(-5, -5), end=(5, 5))
    block.add_line(start=(-5, 5), end=(5, -5))


def _meter(block: BlockLayout, glyph: str) -> None:
    """IEC 60617 S00313 — meter (circle + letter glyph inside)."""
    block.add_circle(center=(0, 0), radius=6)
    block.add_text(
        glyph,
        dxfattribs={"height": 4, "halign": 4, "valign": 2, "align_point": (0, 0)},
    )


def _battery(block: BlockLayout) -> None:
    """IEC 60617 S00306 — battery (alternating long + short plates)."""
    # Long plate (positive), short plate (negative), repeated twice.
    for i in range(2):
        y = 3 - i * 6
        block.add_line(start=(-4, y), end=(4, y))  # long
        block.add_line(start=(-2, y - 2), end=(2, y - 2))  # short


def _load_block(block: BlockLayout, glyph: str) -> None:
    """Generic load — circle with letter glyph (used for compute/GPU loads)."""
    block.add_circle(center=(0, 0), radius=6)
    block.add_text(
        glyph,
        dxfattribs={"height": 4, "halign": 4, "valign": 2, "align_point": (0, 0)},
    )


def _fallback_rectangle(block: BlockLayout, label: str) -> None:
    """Anything we don't have an IEC primitive for — labelled rectangle.

    Truncate label to first 12 chars so it fits inside the box. Stays
    obvious in review: anything boxed is "missing IEC symbol".
    """
    block.add_lwpolyline([(-6, -4), (6, -4), (6, 4), (-6, 4)], close=True)
    block.add_text(
        label[:12],
        dxfattribs={"height": 2, "halign": 4, "valign": 2, "align_point": (0, 0)},
    )
