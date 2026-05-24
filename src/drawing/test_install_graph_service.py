"""InstallGraphService unit tests — top-down container floor plans (schematic).

Per v1 scope: schematic equipment placement (NOT to scale). Real layout
positions land when edp-module-assemblies surfaces a `layout.json`
artifact alongside `topology.yaml`. Tests assert structural shape
(container outlines + per-device boxes) rather than coordinate exactness.
"""

import io

import ezdxf
import pytest

from src.drawing.conftest import make_device, make_dtm, make_template
from src.drawing.install_graph_service import (
    InstallGraphOutputs,
    InstallGraphService,
)
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.template import DeviceTemplate, TemplateKind


def _module_tpl(slug: str) -> DeviceTemplate:
    """Module template with empty contains for the test fixture."""
    from src.shared.schemas.measurement import Measurement, Publisher

    return DeviceTemplate(
        template=slug,
        kind=TemplateKind.MODULE,
        description=slug,
        measurements={
            "total": Measurement(
                unit="watts", type="float", publisher=Publisher.LINE_CONTROLLER
            )
        },
    )


@pytest.fixture
def compute_plus_grid_dtm() -> Dtm:
    """Minimal deployment shape: 1 compute module + 1 grid module + child devices."""
    return make_dtm(
        devices={
            "compute_module_1": make_device(
                "compute_module_1", template="compute_module"
            ).model_copy(update={"connection": None, "parent": None}),
            "grid_module_1": make_device(
                "grid_module_1", template="grid_module"
            ).model_copy(update={"connection": None, "parent": None}),
            "cdu_1": make_device("cdu_1", template="cdu").model_copy(
                update={"parent": "compute_module_1"}
            ),
            "gpu_node_1": make_device("gpu_node_1", template="gpu_node").model_copy(
                update={"parent": "compute_module_1"}
            ),
            "switchgear_1": make_device(
                "switchgear_1", template="switchgear"
            ).model_copy(update={"parent": "grid_module_1"}),
        },
        templates={
            "compute_module": _module_tpl("compute_module"),
            "grid_module": _module_tpl("grid_module"),
            "cdu": make_template("cdu"),
            "gpu_node": make_template("gpu_node"),
            "switchgear": make_template("switchgear"),
        },
    )


def test_generate_returns_dxf_and_pdf_bytes(compute_plus_grid_dtm: Dtm) -> None:
    """generate() returns an outputs bundle with non-empty dxf + pdf bytes."""
    # Act
    actual = InstallGraphService().generate(compute_plus_grid_dtm)

    # Assert
    assert isinstance(actual, InstallGraphOutputs)
    assert len(actual.dxf) > 0
    assert len(actual.pdf) > 0


def test_pdf_starts_with_magic(compute_plus_grid_dtm: Dtm) -> None:
    """PDF bytes start with %PDF- — proves real vector PDF."""
    # Act
    outputs = InstallGraphService().generate(compute_plus_grid_dtm)

    # Assert
    assert outputs.pdf.startswith(b"%PDF-")


def test_pdf_is_one_page_per_module_in_deployment(
    compute_plus_grid_dtm: Dtm,
) -> None:
    """1 module device → 1 sheet. 2 modules → 2 sheets."""
    # Act
    outputs = InstallGraphService().generate(compute_plus_grid_dtm)

    # Assert — fixture has 1 compute_module + 1 grid_module → 2 sheets.
    import re

    pages = re.findall(rb"/Type\s*/Page(?!s)", outputs.pdf)
    assert len(pages) == 2


def test_dxf_carries_title_block_marking_schematic_not_to_scale(
    compute_plus_grid_dtm: Dtm,
) -> None:
    """Title block explicitly flags 'SCHEMATIC — NOT TO SCALE' so reviewers know.

    v1 placement is logical/schematic only; precise positions land when
    edp-module-assemblies surfaces a layout.json artifact.
    """
    # Act
    outputs = InstallGraphService().generate(compute_plus_grid_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    from ezdxf.entities import MText

    mtexts = [m for m in doc.modelspace().query("MTEXT") if isinstance(m, MText)]
    blob = " ".join(m.text for m in mtexts)
    assert "INSTALLATION" in blob.upper()
    assert "SCHEMATIC" in blob.upper()


def test_dxf_carries_one_block_ref_per_child_device(
    compute_plus_grid_dtm: Dtm,
) -> None:
    """Each child device in the module appears as an INSERT in the DXF.

    DXF carries sheet 1 only (DXF is single-modelspace); the full multi-
    sheet PDF surfaces the rest. Compute module has 2 children (cdu_1 +
    gpu_node_1) — both should be present in the sheet-1 DXF.
    """
    # Act
    outputs = InstallGraphService().generate(compute_plus_grid_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert
    inserts = list(doc.modelspace().query("INSERT"))
    insert_names = {ins.dxf.name for ins in inserts}
    # Per-device block names follow the `device_{device_id}` convention.
    assert "device_cdu_1" in insert_names
    assert "device_gpu_node_1" in insert_names


def test_dxf_emits_container_outline_on_dedicated_layer(
    compute_plus_grid_dtm: Dtm,
) -> None:
    """Container walls live on the CONTAINER layer — engineering-review separation."""
    # Act
    outputs = InstallGraphService().generate(compute_plus_grid_dtm)
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))

    # Assert — at least one LWPolyline or LINE on the CONTAINER layer.
    container_entities = [e for e in doc.modelspace() if e.dxf.layer == "CONTAINER"]
    assert len(container_entities) >= 1
