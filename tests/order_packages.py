"""Real orders run against the real assemblies checkout: the full package.

Shared by the order-level tests (coherence, drawings).
"""

from pathlib import Path
from typing import Final, cast
from uuid import uuid4

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.bom_models import Bom, BomOrder
from src.bom_generator.cable_hose_lines import cable_hose_lines
from src.bom_generator.manifest_client import ManifestClient
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import CableHoseScheduleService
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.dtm import Dtm
from tests.assemblies_checkout import AssembliesCheckoutClient

BASE: Final[dict] = {
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
ORDERS: Final[dict[str, dict]] = {
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
NODE_FOR_GPU: Final[dict[str, str]] = {
    "h100_sxm": "CMP-NODE-002",
    "b200": "CMP-NODE-001",
}


def package_for(
    order: dict,
) -> tuple[ConfiguratorPayload, Bom, Dtm, CableHoseSchedule]:
    """Payload, BOM, DTM and cable schedule for one order."""
    payload = ConfiguratorPayload.model_validate(
        {**BASE, **order, "deployment_id": str(uuid4())}
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
