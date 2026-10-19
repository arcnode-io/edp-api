"""Servers per order, how they fill compute containers, and their load (pure math)."""

from math import ceil
from typing import Final

from src.module_resolver.deployment_profile import (
    GPUS_PER_NODE,
    NODES_PER_COMPUTE_CONTAINER,
)
from src.shared.enums import GpuVariant


def gpu_node_count(target_gpu_count: int) -> int:
    """Whole servers for the GPUs asked for; the customer buys per server."""
    return ceil(target_gpu_count / GPUS_PER_NODE)


def compute_container_count(nodes: int) -> int:
    """Containers to hold `nodes`; all full but the last."""
    return ceil(nodes / NODES_PER_COMPUTE_CONTAINER)


# CMP-PDU-001 34.5 kVA: on A/B failover one side carries 3 B200 servers
# (31.5 kW) + both switches (2.1 kW). A full container has 3 per side.
NODES_PER_PDU: Final[int] = 3
PDUS_PER_SIDE: Final[int] = ceil(NODES_PER_COMPUTE_CONTAINER / NODES_PER_PDU)


def dropped_tags(nodes: int) -> frozenset[str]:
    """Topology tags a container holding `nodes` servers leaves out.

    Servers past `nodes` and PDUs past ceil(nodes / 3) on each side. The
    panelboard stays full size, so filling it later adds servers + PDUs.
    """
    pdus = ceil(nodes / NODES_PER_PDU)
    servers = {f"NODE-{i}" for i in range(nodes + 1, NODES_PER_COMPUTE_CONTAINER + 1)}
    pdu_tags = {f"PDU-{s}{i}" for s in "AB" for i in range(pdus + 1, PDUS_PER_SIDE + 1)}
    return frozenset(servers | pdu_tags)


def nodes_in_container(nodes: int, n: int) -> int:
    """Servers in container Cn (1-based): full, or what's left in the last."""
    return min(
        NODES_PER_COMPUTE_CONTAINER, nodes - NODES_PER_COMPUTE_CONTAINER * (n - 1)
    )


# source: edp-module-assemblies/equipment/CMP-NODE-001/spec.yaml
# confidence_flags note on spec.electrical.power_kw. B200 first-principles:
# 8x1000W GPU + 2x350W CPU + 32x9W RAM + 8x12W NVMe + 8x35W NIC + 2x75W DPU +
# ~5% VRM (450W) + 150W fans/BMC/misc = 10,114W internal / 0.96 PSU efficiency
# = 10.5 kW/node. Container = 7 nodes x 10.5 + ~7kW switch/CDU/PDU overhead
# = 80 kW (CONTRACT §5.1, fixed).
#
# H100_SXM derived the same way, swapping only GPU TDP (700W vs 1000W):
# 8x700W GPU + same 700+288+96+280+150=1514W non-GPU + ~5% VRM (356W of the
# 7114W pre-VRM subtotal) + 150W fans/BMC = 7,620W internal / 0.96 = 7.94
# kW/node. Container = 7 x 7.94 + ~7kW overhead = 62.6 kW.
# [OPEN: PM/PO to confirm — derived by TDP substitution, not a real H100_SXM
# node datasheet; no such spec exists in edp-module-assemblies yet.]
CONTAINER_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.B200: 80.0,
    GpuVariant.H100_SXM: 62.6,
}

# EXT-DC-001/-002 dry cooler fans, one cooler per compute container, fed from
# its panelboard. Allowance (2 EC fans, conservative) until a Güntner GPC
# selection gives the real input power — flagged in the equipment spec.
DRY_COOLER_FAN_KW: Final[float] = 6.0


# CMP-NODE-001/-002 power_kw; the derivation above
NODE_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.B200: 10.5,
    GpuVariant.H100_SXM: 7.94,
}


def site_peak_mw(gpu_variant: GpuVariant, target_gpu_count: int) -> float:
    """5.1: servers * node_kw + containers * (overhead + dry cooler fans), MW.

    A container's switch/CDU/PDU overhead is there whatever it holds, so a
    partial container still carries it; a full one comes to CONTAINER_KW.
    """
    nodes = gpu_node_count(target_gpu_count)
    containers = compute_container_count(nodes)
    node_kw = NODE_KW[gpu_variant]
    overhead_kw = CONTAINER_KW[gpu_variant] - NODES_PER_COMPUTE_CONTAINER * node_kw
    return (nodes * node_kw + containers * (overhead_kw + DRY_COOLER_FAN_KW)) / 1000
