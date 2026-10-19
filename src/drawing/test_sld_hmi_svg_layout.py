"""HMI SLD styling and layout: theme-free SVG, labels, orientation, tap targets."""

import re

from src.drawing.conftest import make_bus, make_device, make_dtm, make_template
from src.drawing.sld_hmi_svg_service import SldHmiSvgService


def test_svg_contains_no_inline_hex_colors() -> None:
    # Arrange — multi-device DTM hitting every render branch
    dtm = make_dtm(
        devices={
            "bess_rack_1": make_device("bess_rack_1", display_name="BESS Rack 1"),
            "poi_breaker_1": make_device("poi_breaker_1", template="poi_breaker"),
        },
        buses=[make_bus("dc_bus_1", ["bess_rack_1", "poi_breaker_1"])],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "poi_breaker": make_template("poi_breaker", iec_61850_ref="XCBR.Pos.stVal"),
        },
    )
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert — no `fill="#..."` or `stroke="#..."` inline hex colors.
    # HMI applies theme tokens via CSS; inline hex breaks theming.
    assert not re.search(r'fill="#[0-9A-Fa-f]', svg)
    assert not re.search(r'stroke="#[0-9A-Fa-f]', svg)


def test_text_elements_only_carry_structural_labels() -> None:
    # Arrange — devices with distinct display_name + template
    dtm = make_dtm(
        devices={
            "bess_rack_1": make_device("bess_rack_1", display_name="BESS Rack 1"),
            "inv_1": make_device(
                "inv_1", template="inverter", display_name="Inverter 1"
            ),
        },
        templates={
            "bess_rack": make_template("bess_rack"),
            "inverter": make_template("inverter"),
        },
    )
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()
    text_bodies = re.findall(r"<text[^>]*>([^<]*)</text>", svg)

    # Assert — every text body is either a display_name or template slug.
    # No live measurement values, no ad-hoc strings.
    allowed = {"BESS Rack 1", "Inverter 1", "bess_rack", "inverter"}
    for body in text_bodies:
        assert body in allowed, f"unexpected <text> body: {body!r}"


def test_portrait_stacks_bus_members_vertically() -> None:
    """In portrait, graphviz's TB rankdir + invisible bus-member edges put
    bus members on different y-ranks. The HMI calls portrait on phone-shaped
    viewports so the diagram reads top-to-bottom instead of left-to-right.
    """
    # Arrange — two devices on a single bus
    dtm = make_dtm(
        devices={
            "bess_rack_1": make_device("bess_rack_1", template="bess_rack"),
            "inverter_1": make_device("inverter_1", template="inverter"),
        },
        buses=[make_bus("dc_bus_1", ["bess_rack_1", "inverter_1"], bus_type="dc")],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "inverter": make_template("inverter"),
        },
    )
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm, orientation="portrait").decode()

    # Assert — both devices on the SAME x, DIFFERENT y (vertical stack).
    matches = re.findall(
        r'id="(bess_rack_1|inverter_1)"[^>]*transform="translate\(([\d.]+) ([\d.]+)\)"',
        svg,
    )
    assert len(matches) == 2, f"expected both transforms, got: {matches}"
    coords = {name: (float(x), float(y)) for name, x, y in matches}
    assert (
        coords["bess_rack_1"][0] == coords["inverter_1"][0]
    ), f"portrait must stack on x-axis: {coords}"
    assert (
        coords["bess_rack_1"][1] != coords["inverter_1"][1]
    ), f"portrait must spread on y-axis: {coords}"


def test_landscape_default_keeps_horizontal_layout() -> None:
    """Default orientation is landscape — keeps the existing single-row layout
    so existing snapshots + downstream consumers don't drift.
    """
    # Arrange — same two devices on a single bus
    dtm = make_dtm(
        devices={
            "bess_rack_1": make_device("bess_rack_1", template="bess_rack"),
            "inverter_1": make_device("inverter_1", template="inverter"),
        },
        buses=[make_bus("dc_bus_1", ["bess_rack_1", "inverter_1"], bus_type="dc")],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "inverter": make_template("inverter"),
        },
    )
    svc = SldHmiSvgService()

    # Act — no orientation arg
    svg = svc.generate(dtm).decode()

    # Assert — both devices on the SAME y, DIFFERENT x (horizontal row).
    matches = re.findall(
        r'id="(bess_rack_1|inverter_1)"[^>]*transform="translate\(([\d.]+) ([\d.]+)\)"',
        svg,
    )
    coords = {name: (float(x), float(y)) for name, x, y in matches}
    assert coords["bess_rack_1"][1] == coords["inverter_1"][1], coords
    assert coords["bess_rack_1"][0] != coords["inverter_1"][0], coords


def test_hit_area_meets_wcag_min_tap_target() -> None:
    # Arrange — short-label device whose graphviz body may be small
    dtm = make_dtm({"x1": make_device("x1", display_name="X")})
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert — hit-area rect width + height ≥ 44 (WCAG 2.5.5)
    match = re.search(
        r'data-region="hit-area"[^/]*width="([\d.]+)"\s+height="([\d.]+)"', svg
    )
    assert match is not None
    width, height = float(match.group(1)), float(match.group(2))
    assert width >= 44.0 and height >= 44.0
