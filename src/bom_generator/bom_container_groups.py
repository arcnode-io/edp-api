"""Which bom.yaml builds which containers, the last compute one partial.

Split out of bom_generator_service.py (200-line budget). The last compute
container holds only the servers left over, and their PDUs; the panelboard
stays full size so servers can be added later.
"""

from src.bom_generator.bom_container_lines import ContainerGroup
from src.bom_generator.bom_models import BomLineItem, BomSection
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest, ProfileAssemblies
from src.shared.enums import GpuVariant
from src.sizing.compute_nodes import (
    NODES_PER_COMPUTE_CONTAINER,
    PDUS_PER_SIDE,
    dropped_tags,
    nodes_in_container,
)

PANELBOARD = "CMP-PNL-001"


def container_groups(
    client: ManifestClient,
    manifest: Manifest,
    prof: ProfileAssemblies,
    gpu_variant: GpuVariant,
    counts: tuple[int, int, int],
) -> list[ContainerGroup]:
    """Compute C1-CN (CN maybe partial); grid G1 (primary) + G2-GM feeders.

    Args:
        counts: (servers, compute containers, grid containers).
    """
    nodes, compute_qty, grid_qty = counts

    def bom(kind: str, name: str) -> dict:
        return client.fetch_bom_yaml(manifest.assemblies[kind][name].bom)

    compute = bom("compute_container", prof.compute_variant(gpu_variant))
    last = nodes_in_container(nodes, compute_qty)
    full_qty = compute_qty if last == NODES_PER_COMPUTE_CONTAINER else compute_qty - 1
    groups: list[ContainerGroup] = []
    if full_qty > 0:
        groups.append(ContainerGroup(BomSection.COMPUTE, "C", 1, full_qty, compute))
    if full_qty < compute_qty:
        partial = _without(compute, dropped_tags(last))
        groups.append(
            ContainerGroup(BomSection.COMPUTE, "C", compute_qty, compute_qty, partial)
        )
    if prof.grid_container is not None:
        primary = bom("grid_container", prof.grid_container)
        groups.append(ContainerGroup(BomSection.GRID, "G", 1, 1, primary))
        if grid_qty > 1:
            if prof.grid_feeder_container is None:
                raise ValueError(f"{grid_qty} grid containers but no feeder variant")
            feeder = bom("grid_container", prof.grid_feeder_container)
            groups.append(ContainerGroup(BomSection.GRID, "G", 2, grid_qty, feeder))
    return groups


def with_partial_panel_note(
    lines: list[BomLineItem], nodes: int, compute_qty: int
) -> list[BomLineItem]:
    """Tell the panel builder the partial container's breakers are fewer."""
    last = nodes_in_container(nodes, compute_qty)
    if last == NODES_PER_COMPUTE_CONTAINER:
        return lines
    pdus = 2 * PDUS_PER_SIDE - sum(t.startswith("PDU-") for t in dropped_tags(last))
    note = (
        f"C{compute_qty} holds {last} server{'s' if last != 1 else ''}: branch "
        f"breakers for its {pdus} PDUs, CDU and dry cooler only; keep every PDU "
        "space so servers can be added."
    )
    return [
        (
            li.model_copy(update={"notes": f"{li.notes} {note}".strip()})
            if li.equipment_id == PANELBOARD
            else li
        )
        for li in lines
    ]


def _without(bom: dict, drop: frozenset[str]) -> dict:
    """bom.yaml with the dropped tags (and their qty) taken out."""
    parts = []
    for p in bom["parts"]:
        tags = p.get("tags") or []
        kept = [t for t in tags if t not in drop]
        if len(kept) == len(tags):
            parts.append(p)
        elif kept:
            parts.append({**p, "qty": len(kept), "tags": kept})
    return {**bom, "parts": parts}
