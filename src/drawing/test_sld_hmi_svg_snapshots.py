"""Syrupy snapshot tests for SLD HMI SVG generator.

Baselines guard against unintended drift in SVG byte output. Regenerate
intentionally with `uv run pytest src/drawing/test_sld_hmi_svg_snapshots.py
--snapshot-update` and review the diff before committing.

Snapshot stability requires dot binary major-version alignment between
dev + CI + Dockerfile (currently graphviz 13.x).
"""

from src.drawing.conftest import make_bus, make_device, make_dtm, make_template
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.shared.schemas.dtm import Dtm


def _generate(dtm: Dtm) -> str:
    return SldHmiSvgService().generate(dtm).decode("utf-8")


def test_snapshot_minimal_one_bess_one_inverter_one_grid(snapshot) -> None:  # type: ignore[no-untyped-def]
    # Arrange — 1 BESS + 1 inverter + 1 grid_module, one DC bus
    dtm = make_dtm(
        devices={
            "bess_rack_1": make_device(
                "bess_rack_1", template="bess_rack", display_name="BESS Rack 1"
            ),
            "inverter_1": make_device(
                "inverter_1", template="inverter", display_name="Inverter 1"
            ),
            "grid_module_1": make_device(
                "grid_module_1", template="grid_module", display_name="Grid Module 1"
            ),
        },
        buses=[make_bus("dc_bus_1", ["bess_rack_1", "inverter_1"], bus_type="dc")],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "inverter": make_template("inverter"),
            "grid_module": make_template("grid_module"),
        },
    )

    # Act / Assert
    assert _generate(dtm) == snapshot


def test_snapshot_multi_rack_four_bess_one_pcs_one_ac_bus(snapshot) -> None:  # type: ignore[no-untyped-def]
    # Arrange — 4 BESS racks → 1 PCS → 1 AC bus, modeled as 2 buses (DC + AC)
    racks = {f"bess_rack_{i}": make_device(f"bess_rack_{i}") for i in range(1, 5)}
    pcs = {"pcs_1": make_device("pcs_1", template="pcs")}
    dtm = make_dtm(
        devices={**racks, **pcs},
        buses=[
            make_bus(
                "dc_bus_1",
                [*[f"bess_rack_{i}" for i in range(1, 5)], "pcs_1"],
                bus_type="dc",
            ),
        ],
        templates={
            "bess_rack": make_template("bess_rack", iec_61850_ref="MMXU.W"),
            "pcs": make_template("pcs", iec_61850_ref="XCBR.Pos.stVal"),
        },
    )

    # Act / Assert
    assert _generate(dtm) == snapshot


def test_snapshot_mixed_two_bess_compute_grid(snapshot) -> None:  # type: ignore[no-untyped-def]
    # Arrange — 2 BESS modules + 1 compute_module + 1 grid_module
    dtm = make_dtm(
        devices={
            "bess_module_1": make_device("bess_module_1", template="bess_module"),
            "bess_module_2": make_device("bess_module_2", template="bess_module"),
            "compute_module_1": make_device(
                "compute_module_1", template="compute_module"
            ),
            "grid_module_1": make_device("grid_module_1", template="grid_module"),
        },
        buses=[
            make_bus(
                "ac_bus_1",
                ["bess_module_1", "bess_module_2", "grid_module_1"],
                bus_type="ac",
            ),
            make_bus(
                "load_bus_1", ["grid_module_1", "compute_module_1"], bus_type="ac"
            ),
        ],
        templates={
            "bess_module": make_template("bess_module", iec_61850_ref="MMXU.W"),
            "compute_module": make_template("compute_module"),
            "grid_module": make_template("grid_module", iec_61850_ref="MMXU.W"),
        },
    )

    # Act / Assert
    assert _generate(dtm) == snapshot
