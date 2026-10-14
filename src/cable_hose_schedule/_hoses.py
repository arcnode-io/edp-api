"""Hoses: the P&ID, loop by loop.

Primary (facility) loop per compute container: dry cooler → CDU primary
supply, CDU primary return → dry cooler, through the CD plate and the
by-others pump and buffer tank (P&ID sheet 2). Secondary (rack) loop:
CDU → each node's DLC plate and back, through the rack manifold (sheet 1).
"""

from typing import Final

from src.cable_hose_schedule._site_index import Container, tag
from src.cable_hose_schedule.cable_hose_schedule_models import HoseEntry
from src.dtm.device_roles import GPU_NODE_TEMPLATES
from src.shared.schemas.dtm import Device

_DRY_COOLERS: Final[tuple[str, ...]] = ("dc_external", "dc_external_dod")
_PRIMARY: Final[str] = "EPDM 1in PG/W rated"
_SECONDARY: Final[str] = "EPDM 0.5in DEI water rated"


def hoses(sites: list[Container]) -> list[HoseEntry]:
    """Primary then secondary loop hoses for every compute container."""
    found: list[HoseEntry] = []
    for c in sites:
        cdu = c.one("cdu")
        if cdu is None:
            continue
        cooler = c.one(*_DRY_COOLERS)
        if cooler is not None:
            via = "Via the CD plate and the facility pump + buffer tank (by others)."
            found += [
                _hose(
                    "primary supply",
                    cooler,
                    "FLUID_OUT",
                    cdu,
                    "PRI_SUPPLY",
                    _PRIMARY,
                    via,
                ),
                _hose(
                    "primary return",
                    cdu,
                    "PRI_RETURN",
                    cooler,
                    "FLUID_IN",
                    _PRIMARY,
                    via,
                ),
            ]
        for node in c.of(*GPU_NODE_TEMPLATES):
            via = "Through the rack manifold."
            found += [
                _hose(
                    "secondary supply",
                    cdu,
                    "SEC_SUPPLY",
                    node,
                    "GPU_LIQ_SUPPLY",
                    _SECONDARY,
                    via,
                ),
                _hose(
                    "secondary return",
                    node,
                    "GPU_LIQ_RETURN",
                    cdu,
                    "SEC_RETURN",
                    _SECONDARY,
                    via,
                ),
            ]
    return found


def _hose(
    service: str,
    src: Device,
    src_port: str,
    dst: Device,
    dst_port: str,
    kind: str,
    notes: str,
) -> HoseEntry:
    return HoseEntry(
        tag="",
        service=f"Coolant {service}",
        from_device=tag(src),
        from_port=src_port,
        to_device=tag(dst),
        to_port=dst_port,
        hose_type=kind,
        notes=notes,
    )
