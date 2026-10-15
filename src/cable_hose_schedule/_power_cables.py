"""Power runs: the single-line diagram, run by run.

- Grid switchboard → each compute panelboard it feeds (ADR-018 split),
  through CG.
- dc_ext battery pad: CATL strings → each PCS DC input (ADR-022). The PCS
  AC side goes to the customer's step-up, which isn't a device here.
- Compute panelboard → each PDU, the CDU and the dry cooler (ADR-017).
- PDUs → loads on both paths (ADR-005): node i is fed from PDU-A and
  PDU-B number (i mod 3) + 1; switches from PDU-A1 and PDU-B1.
Sizes per ADR-021: compute feeder 175 A.
"""

from typing import Final

from src.cable_hose_schedule._site_index import Container, tag
from src.cable_hose_schedule.cable_hose_schedule_models import CableEntry
from src.dtm.device_roles import GPU_NODE_TEMPLATES
from src.shared.schemas.dtm import Device
from src.sizing.compute_feeds import compute_feeds

_DRY_COOLERS: Final[tuple[str, ...]] = ("dc_external", "dc_external_dod")
_SWITCHES: Final[tuple[str, ...]] = ("network_switch", "mgmt_switch")
_NODE_CORD: Final[dict[str, str]] = {
    "gpu_node": "C19-C20 cordset, 16 A, x4 (4 of 8 PSU inlets per path)",
    "gpu_node_h100": "C19-C20 cordset, 16 A, x4 (4 of 8 PSU inlets per path)",
}
_FEEDER: Final[str] = "4 x 2/0 AWG Cu + ground, 175 A (size for run length)"
_PCS_DC: Final[str] = "1500 V DC PV/BESS cable, size per CATL string count"


def power_cables(sites: list[Container]) -> list[CableEntry]:
    """Feeders between containers, then each compute container's branches."""
    compute = [c for c in sites if c.kind == "compute"]
    grids = [c for c in sites if c.kind == "grid"]
    pads = [c for c in sites if c.kind == "bess"]
    cables: list[CableEntry] = []
    for grid, fed in zip(grids, compute_feeds(len(compute), len(grids)), strict=True):
        swbd = grid.one("lv_switchboard")
        if swbd is None:
            continue
        for n in fed:
            pnl = compute[n - 1].one("panelboard")
            if pnl is not None:
                cables.append(
                    _run(
                        swbd,
                        pnl,
                        "415Y/240 V 3ph feeder, 175 A breaker",
                        _FEEDER,
                        "Through CG.",
                    )
                )
    for pad in pads:
        battery = pad.one("bess_catl")
        if battery is not None:
            cables += [
                _run(
                    battery,
                    pcs,
                    "1500 V DC strings",
                    _PCS_DC,
                    "On the battery pad (ADR-022).",
                )
                for pcs in pad.of("pcs")
            ]
    for container in compute:
        cables += _compute_branches(container)
    return cables


def _compute_branches(c: Container) -> list[CableEntry]:
    pnl = c.one("panelboard")
    pdus_a = [d for d in c.of("pdu") if tag(d).split("-")[-1].startswith("A")]
    pdus_b = [d for d in c.of("pdu") if tag(d).split("-")[-1].startswith("B")]
    cables: list[CableEntry] = []
    if pnl is not None:
        cables += [
            _run(
                pnl,
                pdu,
                "415Y/240 V 3ph branch, 60 A breaker",
                "60 A 4P5W cord, IEC 60309 3P+N+PE plug",
                "PX4 inlet.",
            )
            for pdu in [*pdus_a, *pdus_b]
        ]
        cables += [
            _run(
                pnl,
                load,
                "415Y/240 V 3ph branch",
                "3ph 4-wire + ground, field-wired",
                "Outdoor run to the pad." if load.template in _DRY_COOLERS else "",
            )
            for load in [*c.of("cdu"), *c.of(*_DRY_COOLERS)]
        ]
    for i, node in enumerate(c.of(*GPU_NODE_TEMPLATES)):
        for path in (pdus_a, pdus_b):
            if path:
                cables.append(
                    _run(
                        path[i % len(path)],
                        node,
                        "240 V 1ph PSU feed",
                        _NODE_CORD[node.template],
                        "A/B dual-path (ADR-005).",
                    )
                )
    for switch in c.of(*_SWITCHES):
        for path in (pdus_a, pdus_b):
            if path:
                cables.append(
                    _run(path[0], switch, "240 V 1ph PSU feed", "C13-C14 cordset", "")
                )
    return cables


def _run(src: Device, dst: Device, service: str, cable: str, notes: str) -> CableEntry:
    return CableEntry(
        tag="",
        service=f"Power - {service}",
        from_device=tag(src),
        from_port="OUT",
        to_device=tag(dst),
        to_port="PWR",
        cable_type=cable,
        notes=notes,
    )
