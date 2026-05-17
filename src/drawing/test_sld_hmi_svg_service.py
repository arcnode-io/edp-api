"""SldHmiSvgService TDD tests — structural-only SVG emission."""

import re

from src.drawing.conftest import make_bus, make_device, make_dtm, make_template
from src.drawing.sld_hmi_svg_service import SldHmiSvgService


def test_emits_device_node_group_with_id_and_data_attrs() -> None:
    # Arrange — one device, no buses
    dtm = make_dtm({"bess_rack_1": make_device("bess_rack_1", template="bess_rack")})
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert — device_id on the <g>, data-comp + data-template hooks present
    assert 'id="bess_rack_1"' in svg
    assert 'data-comp="device-node"' in svg
    assert 'data-template="bess_rack"' in svg


def test_emits_bus_path_with_source_first_direction() -> None:
    # Arrange — BESS (MMXU.W → source) + inverter (no MMXU.W → sink), one DC bus
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
    svg = svc.generate(dtm).decode()

    # Assert — bus path emitted with required HMI hooks
    assert 'id="bus_dc_bus_1"' in svg
    assert 'data-comp="bus"' in svg
    assert 'data-bus-type="dc"' in svg

    # Assert — path direction: source (bess) at M, sink (inverter) at L.
    # Locate the bus path's `d` attribute. Path direction is the contract;
    # the HMI engineer animates flow per [[sld-hmi-bus-direction]].
    match = re.search(
        r'id="bus_dc_bus_1"[^>]*d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+)"', svg
    )
    assert match is not None, f"bus path d=... not found in: {svg}"
    sx, sy, ex, ey = (float(x) for x in match.groups())

    # The source's <g id="bess_rack_1"> is positioned at (sx, sy); the sink's
    # is at (ex, ey). We assert that the path's M-point coincides with the
    # BESS device-node coords and the L-point with the inverter's.
    bess_pos = re.search(
        r'id="bess_rack_1"[^>]*transform="translate\(([\d.]+) ([\d.]+)\)"', svg
    )
    inverter_pos = re.search(
        r'id="inverter_1"[^>]*transform="translate\(([\d.]+) ([\d.]+)\)"', svg
    )
    assert bess_pos is not None and inverter_pos is not None
    assert (sx, sy) == (float(bess_pos.group(1)), float(bess_pos.group(2)))
    assert (ex, ey) == (float(inverter_pos.group(1)), float(inverter_pos.group(2)))


def test_device_node_carries_all_data_region_subelements() -> None:
    # Arrange — one device with display_name set
    dtm = make_dtm(
        {"bess_rack_1": make_device("bess_rack_1", display_name="BESS Rack 1")}
    )
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert — body, status-indicator, label-name, label-template, hit-area
    for region in (
        "body",
        "status-indicator",
        "label-name",
        "label-template",
        "hit-area",
    ):
        assert f'data-region="{region}"' in svg, f"missing data-region={region}"

    # Assert — display_name rendered in label-name
    assert ">BESS Rack 1</text>" in svg
    # Assert — template slug rendered in label-template
    assert ">bess_rack</text>" in svg


def test_breaker_device_renders_breaker_region() -> None:
    # Arrange — device whose template measurement carries an XCBR.Pos.stVal ref
    dtm = make_dtm(
        devices={"poi_breaker_1": make_device("poi_breaker_1", template="poi_breaker")},
        templates={
            "poi_breaker": make_template("poi_breaker", iec_61850_ref="XCBR.Pos.stVal")
        },
    )
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert — breaker subgroup emitted inside the device-node <g>
    assert 'data-region="breaker"' in svg


def test_non_breaker_device_omits_breaker_region() -> None:
    # Arrange — BESS template has no XCBR/XSWI ref
    dtm = make_dtm({"bess_rack_1": make_device("bess_rack_1")})
    svc = SldHmiSvgService()

    # Act
    svg = svc.generate(dtm).decode()

    # Assert
    assert 'data-region="breaker"' not in svg


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
    assert coords["bess_rack_1"][0] == coords["inverter_1"][0], (
        f"portrait must stack on x-axis: {coords}"
    )
    assert coords["bess_rack_1"][1] != coords["inverter_1"][1], (
        f"portrait must spread on y-axis: {coords}"
    )


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
