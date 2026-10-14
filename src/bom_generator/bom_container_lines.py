"""BOM lines for one container section (compute or grid).

A section holds one or more container groups: compute is one group of N
identical containers; grid is the primary G1 plus feeders G2-GM. Each
part becomes one line: qty = per-container qty x containers, reference
designators = the part's device tags under each container range.
"""

from collections.abc import Callable
from dataclasses import dataclass

from src.bom_generator.bom_models import BomLineItem, BomSection
from src.bom_generator.bom_ref_des import containers, ref_des


@dataclass(frozen=True)
class ContainerGroup:
    """Containers prefix+first … prefix+last, all built from one bom.yaml."""

    section: BomSection
    prefix: str  # "C" or "G"
    first: int
    last: int
    bom: dict

    @property
    def count(self) -> int:
        """Containers in the group."""
        return self.last - self.first + 1


# (equipment_id, qty, section, ref_des) → catalog line
PartLine = Callable[[str, int, BomSection, str], BomLineItem | None]
# (plate_id, qty, section, ref_des) → custom-fab line
PlateLine = Callable[[str, int, BomSection, str], BomLineItem | None]
# (shell block, qty, section, ref_des) → custom-fab line
ShellLine = Callable[[dict, int, BomSection, str], BomLineItem]


def section_lines(
    groups: list[ContainerGroup],
    *,
    shell_line: ShellLine,
    part_line: PartLine,
    plate_line: PlateLine,
) -> list[BomLineItem]:
    """Shell, parts and plates for one section's containers."""
    if not groups:
        return []
    section, prefix = groups[0].section, groups[0].prefix
    span = containers(prefix, groups[0].first, groups[-1].last)
    total = sum(g.count for g in groups)
    lines = [shell_line(groups[0].bom["shell"], total, section, span)]

    for eid in _ordered(groups, "parts", "equipment_id"):
        held = [
            (g, p) for g in groups for p in g.bom["parts"] if p["equipment_id"] == eid
        ]
        qty = sum(p["qty"] * g.count for g, p in held)
        tags = [(g.prefix, g.first, g.last, p.get("tags", [])) for g, p in held]
        ref = ref_des(tags) or _span(held)
        line = part_line(eid, qty, section, ref)
        if line is not None:
            lines.append(line)

    for pid in _ordered(groups, "plates", "id"):
        held = [
            (g, p) for g in groups for p in g.bom.get("plates", []) if p["id"] == pid
        ]
        qty = sum(p["qty"] * g.count for g, p in held)
        line = plate_line(pid, qty, section, _span(held))
        if line is not None:
            lines.append(line)
    return lines


def _ordered(groups: list[ContainerGroup], key: str, field: str) -> list[str]:
    """Ids in first-seen order across the groups' bom.yaml sections."""
    seen: dict[str, None] = {}
    for g in groups:
        for item in g.bom.get(key, []):
            seen.setdefault(item[field], None)
    return list(seen)


def _span(held: list[tuple[ContainerGroup, dict]]) -> str:
    """Container range covered, e.g. "C1-C4" or "G1-G3"."""
    first, last = held[0][0], held[-1][0]
    return containers(first.prefix, first.first, last.last)
