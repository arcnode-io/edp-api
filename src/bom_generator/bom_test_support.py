"""Shared BOM test values; import explicitly into the tests that use them."""

from typing import Final

from src.bom_generator.bom_models import BomOrder

ORDER: Final[BomOrder] = BomOrder(
    customer="acme",
    site="brookside dc-1",
    deployment_context="commercial",
    gpu_variant="b200",
    gpus_requested=56,
    gpus_delivered=56,  # 7 servers, one full container
    bess_capacity_mwh=1.0,
    bess_coupling="ac_coupled",
    pcs_qty=0,
)
