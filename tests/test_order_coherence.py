"""Every artifact matches the order and each other (QA 2026-10-13).

Runs real orders against the real assemblies data and checks the
package the way a design reviewer would: the order reaches the hardware,
the BOM and the device data list the same devices, every device has
install steps and every polled device a comms run, and every tag is unique.
"""

from collections import Counter
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.bom_models import Bom, BomOrder, ProcurementPath
from src.bom_generator.cable_hose_lines import cable_hose_lines
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import CableHoseScheduleService
from src.drawing.install_sequence_service import build_mop_rows
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.dtm import Dtm
from tests.assemblies_checkout import REPO, AssembliesCheckoutClient

pytestmark = pytest.mark.skipif(
    not (REPO / "manifest.yaml").is_file(),
    reason="edp-module-assemblies checkout required",
)

_BASE: dict = {
    "operator_org": "acme",
    "deployment_site_name": "brookside dc-1",
    "contact_email": "ops@example.com",
    "primary_workload": "ai_training",
    "climate_zone": "temperate",
    "aws_partition": "standard",
    "site": {"location": {"lat": 32.7, "lon": -96.8}, "country": "US"},
    "onsite_generation": {"type": "none"},
    "grid": {"path": "off_grid"},
}
_ORDERS: dict[str, dict] = {
    "8xH100-1MWh-ac": {
        "gpu_variant": "h100_sxm",
        "target_gpu_count": 8,
        "bess_coupling": "ac_coupled",
        "bess_capacity_mwh": 1.0,
        "deployment_context": "commercial",
    },
    "600xB200-4MWh-dc_ext": {
        "gpu_variant": "b200",
        "target_gpu_count": 600,
        "bess_coupling": "dc_external_pcs",
        "bess_capacity_mwh": 4.0,
        "deployment_context": "commercial",
    },
    "56xH100-defense": {
        "gpu_variant": "h100_sxm",
        "target_gpu_count": 56,
        "bess_coupling": "ac_coupled",
        "bess_capacity_mwh": 2.0,
        "deployment_context": "defense_forward",
        "aws_partition": "govcloud",
    },
}
_NODE_FOR_GPU = {"h100_sxm": "CMP-NODE-002", "b200": "CMP-NODE-001"}


def _package(order: dict) -> tuple[ConfiguratorPayload, Bom, Dtm, CableHoseSchedule]:
    payload = ConfiguratorPayload.model_validate(
        {**_BASE, **order, "deployment_id": str(uuid4())}
    )
    resolution = ModuleResolverService().resolve(payload)
    client = cast(ManifestClient, AssembliesCheckoutClient())
    catalog = TemplateLoader(
        root=Path(__file__).resolve().parents[1] / "device_templates"
    ).load_catalog()
    dtm = DtmGeneratorService(client, template_catalog=catalog).generate(
        profile=resolution.deployment_profile.value,
        resolution=resolution,
        manifest=client.fetch_manifest(),
    )
    schedule = CableHoseScheduleService().generate(dtm)
    bom = BomGeneratorService(client).generate(
        deployment_id=payload.deployment_id,
        profile=resolution.deployment_profile.value,
        gpu_variant=resolution.gpu_variant,
        order=BomOrder(
            customer=payload.operator_org,
            site=payload.deployment_site_name,
            deployment_context=payload.deployment_context.value,
            gpu_variant=payload.gpu_variant.value,
            gpus_requested=payload.target_gpu_count,
            gpus_delivered=resolution.gpu_count,
            bess_capacity_mwh=payload.bess_capacity_mwh,
            bess_coupling=payload.bess_coupling.value,
        ),
        compute_container_qty=resolution.compute_container_count,
        grid_container_qty=resolution.grid_container_count,
        field_lines=cable_hose_lines(schedule),
    )
    return payload, bom, dtm, schedule


@pytest.fixture(scope="module", params=sorted(_ORDERS))
def package(
    request: pytest.FixtureRequest,
) -> tuple[ConfiguratorPayload, Bom, Dtm, CableHoseSchedule]:
    return _package(_ORDERS[request.param])


def test_the_order_reaches_the_hardware(package: tuple) -> None:
    # Arrange
    payload, bom, _, _ = package

    # Act
    nodes = {
        li.equipment_id
        for li in bom.line_items
        if (li.equipment_id or "").startswith("CMP-NODE")
    }
    bess = [li for li in bom.line_items if li.ref_des == "BESS-1"]

    # Assert — the ordered GPU's node, and the ordered battery size
    assert nodes == {_NODE_FOR_GPU[payload.gpu_variant.value]}
    assert f"{payload.bess_capacity_mwh:g} MWh" in bess[0].description
    assert bom.order.gpus_requested == payload.target_gpu_count


def test_bom_and_device_data_list_the_same_devices(package: tuple) -> None:
    # Arrange
    _, bom, dtm, _ = package
    bought = (ProcurementPath.CATALOG, ProcurementPath.ENGINEERED_TO_ORDER)

    # Act — qty per equipment on both sides (the customer's battery included)
    in_bom: Counter[str] = Counter()
    for li in bom.line_items:
        if li.equipment_id and li.procurement_path in bought:
            in_bom[li.equipment_id] += li.qty
    in_dtm = Counter(
        dtm.templates_used[d.template].equipment_id
        for d in dtm.devices.values()
        if d.parent is not None and not d.template.startswith("bess")
    )

    # Assert
    assert in_bom == in_dtm
    assert any(d.display_name == "BESS-1" for d in dtm.devices.values())


def test_every_device_has_install_steps(package: tuple) -> None:
    # Arrange
    _, _, dtm, _ = package
    leaves = {d.display_name for d in dtm.devices.values() if d.parent is not None}

    # Act
    stepped = {row.device for row in build_mop_rows(dtm)}

    # Assert
    assert leaves - stepped == set()


def test_every_polled_device_has_a_comms_run_and_every_run_lands(
    package: tuple,
) -> None:
    # Arrange
    _, _, dtm, schedule = package
    tags = {d.display_name for d in dtm.devices.values()} | {"EMS-GW"}
    polled = {d.display_name for d in dtm.devices.values() if d.connection is not None}

    # Act
    comms_from = {
        c.from_device for c in schedule.cables if c.service.startswith("Comms")
    }
    ends = {
        e
        for r in [*schedule.cables, *schedule.hoses]
        for e in (r.from_device, r.to_device)
    }

    # Assert
    assert (polled - comms_from, ends - tags) == (set(), set())


def test_every_tag_names_one_device(package: tuple) -> None:
    # Arrange
    _, _, dtm, _ = package

    # Act
    repeated = [
        t
        for t, n in Counter(d.display_name for d in dtm.devices.values()).items()
        if n > 1
    ]

    # Assert
    assert repeated == []
