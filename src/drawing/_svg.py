"""SVG authoring — hand-written XML so HMI's data-* attribute contract is exact.

Graphviz dot SVG output adds inline colors + class names that conflict with
HMI's CSS-theming. We use graphviz only for layout (plain format) and emit
SVG ourselves to keep full control over attributes, ids, and structure.
"""

from src.drawing._iec_61850 import is_breaker_template, source_member_index
from src.drawing._layout import DevicePosition
from src.shared.schemas.dtm import Bus, Dtm

# Graphviz plain-format units are inches; 72 user units per inch maps to the
# SVG point convention dot itself uses when emitting SVG.
_INCHES_TO_SVG_UNITS = 72.0


def author_svg(dtm: Dtm, positions: dict[str, DevicePosition]) -> str:
    """Compose the final SVG document from DTM + computed device positions."""
    width, height = _viewbox(positions)
    device_groups = [_device_group(dtm, pos) for pos in positions.values()]
    bus_paths = [_bus_path(bus, dtm, positions) for bus in dtm.buses]
    body = "\n".join(device_groups + bus_paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width:.2f} {height:.2f}">\n'
        f"{body}\n</svg>\n"
    )


def _viewbox(positions: dict[str, DevicePosition]) -> tuple[float, float]:
    """Bounding box covering every device, padded modestly."""
    if not positions:
        return (100.0, 100.0)
    max_x = max((p.x + p.width / 2) for p in positions.values()) * _INCHES_TO_SVG_UNITS
    max_y = max((p.y + p.height / 2) for p in positions.values()) * _INCHES_TO_SVG_UNITS
    return (max_x + 20, max_y + 20)


def _device_center(pos: DevicePosition) -> tuple[float, float]:
    """Device position in SVG units (centered)."""
    return (pos.x * _INCHES_TO_SVG_UNITS, pos.y * _INCHES_TO_SVG_UNITS)


_WCAG_MIN_TAP = 44.0
_STATUS_INDICATOR_RADIUS = 3.0


def _role_for_template(template_slug: str) -> str | None:
    """Special render-role for utility-side feed templates. Per UTILITY-FEEDS.md §5.

    POI revenue meter and DLR feed get distinct visual treatment downstream
    in the HMI — emitted here as semantic `data-role` markers + (for POI)
    reserved `<text>` slots for live state overlay. Returns None for
    standard device templates.
    """
    if template_slug == "revenue_meter":
        return "poi"
    if template_slug == "line_rating":
        return "dlr-badge"
    return None


def _poi_state_slots() -> str:
    """Reserved text slots for the revenue_meter (POI) live overlay.

    HMI fills `primary-value` with the settlement reading + DOE direction
    word, and the state row with `DOE` label + status token (OK / STALE /
    INVALID / COMM_FAIL / ISLAND). Slots emitted empty per the
    structural-only contract; positioning is local to the device-group.
    """
    return (
        '    <text data-region="primary-value" x="0" y="-2" '
        'text-anchor="middle" fill="currentColor"></text>\n'
        '    <text data-region="state-label" x="-18" y="14" '
        'text-anchor="middle" fill="currentColor">DOE</text>\n'
        '    <text data-region="state-token" x="18" y="14" '
        'text-anchor="middle" fill="currentColor"></text>\n'
    )


def _device_group(dtm: Dtm, pos: DevicePosition) -> str:
    """One <g> per device, positioned via translate, with id + HMI data-* hooks.

    Subelements (per handoff §3.1):
      - body rect: visible shape
      - status-indicator: top-right corner dot, HMI swaps fill per device state
      - label-name: display_name (or device_id fallback)
      - label-template: template slug
      - hit-area: invisible WCAG 2.5.5 tap target (>= 44x44)
    Coordinates are local to the group's transform (origin at body center).

    Utility-side feeds carry an additional `data-role` attribute (POI or
    DLR badge) so HMI can apply distinct visual treatment without DOM
    mutation. POI nodes also include reserved state-text slots.
    """
    device = dtm.devices[pos.device_id]
    template = dtm.templates_used[device.template]
    cx, cy = _device_center(pos)
    body_w = pos.width * _INCHES_TO_SVG_UNITS
    body_h = pos.height * _INCHES_TO_SVG_UNITS
    half_w, half_h = body_w / 2, body_h / 2
    hit_w = max(body_w, _WCAG_MIN_TAP)
    hit_h = max(body_h, _WCAG_MIN_TAP)
    name = device.display_name or device.device_id
    breaker = _breaker_glyph() if is_breaker_template(template) else ""
    role = _role_for_template(device.template)
    role_attr = f' data-role="{role}"' if role else ""
    poi_slots = _poi_state_slots() if role == "poi" else ""
    return (
        f'  <g id="{pos.device_id}" '
        f'data-comp="device-node" data-template="{device.template}"{role_attr} '
        f'transform="translate({cx:.2f} {cy:.2f})">\n'
        f'    <rect data-region="body" '
        f'x="{-half_w:.2f}" y="{-half_h:.2f}" '
        f'width="{body_w:.2f}" height="{body_h:.2f}" '
        f'fill="currentColor" />\n'
        f'    <circle data-region="status-indicator" '
        f'cx="{half_w:.2f}" cy="{-half_h:.2f}" r="{_STATUS_INDICATOR_RADIUS:.1f}" />\n'
        f"{breaker}"
        f'    <text data-region="label-name" x="0" y="0" '
        f'text-anchor="middle" fill="currentColor">{name}</text>\n'
        f'    <text data-region="label-template" x="0" y="12" '
        f'text-anchor="middle" fill="currentColor">{device.template}</text>\n'
        f"{poi_slots}"
        f'    <rect data-region="hit-area" '
        f'x="{-hit_w/2:.2f}" y="{-hit_h/2:.2f}" '
        f'width="{hit_w:.2f}" height="{hit_h:.2f}" '
        f'fill="transparent" />\n'
        "  </g>"
    )


def _breaker_glyph() -> str:
    """IEC breaker symbol in closed state: circle + horizontal bar.

    HMI swaps the inner shape on `breakerState` change. We render the closed
    baseline; open = angled gap, trip = alarm-color line — HMI's concern.
    """
    return (
        '    <g data-region="breaker">\n'
        '      <circle cx="0" cy="0" r="6" fill="none" stroke="currentColor" />\n'
        '      <line x1="-6" y1="0" x2="6" y2="0" stroke="currentColor" />\n'
        "    </g>\n"
    )


def _bus_path(bus: Bus, dtm: Dtm, positions: dict[str, DevicePosition]) -> str:
    """One <path id="bus_..."> per bus. Direction: source-side member → sink.

    Source-side identified via IEC 61850 MMXU.W presence per the locked rule
    in `_source_side.source_member_index`. Path geometry is a straight line
    from source center to sink center; HMI animates particles along it.
    """
    src_idx = source_member_index(bus, dtm)
    src_id = bus.members[src_idx].device_id
    sink_id = (
        bus.members[1 - src_idx].device_id
        if len(bus.members) == 2
        else bus.members[-1].device_id
    )
    sx, sy = _device_center(positions[src_id])
    ex, ey = _device_center(positions[sink_id])
    return (
        f'  <path id="bus_{bus.bus_id}" data-comp="bus" '
        f'data-bus-type="{bus.type}" '
        f'd="M {sx:.2f} {sy:.2f} L {ex:.2f} {ey:.2f}" '
        'fill="none" stroke="currentColor" />'
    )
