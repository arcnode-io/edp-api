"""Build the install-sequence DAG from a DTM.

Pure functions — no I/O, no rendering. Output is a Pydantic model so
downstream renderers consume a stable shape.

Edge derivation:
- Intra-device: each task's `depends_on` (local task names) becomes an
  edge from the prior task to the next, within the same device.
- Cross-device: BICSI commissioning levels gate the phases. Any task at
  L(n) depends on every L(n-1) task across all devices. This produces
  the visible "phase columns" + parallel branches per device.

Critical path: longest cumulative `est_minutes` path through the DAG.
Used by the renderer to thicken those edges so the bottleneck reads at
a glance.
"""

from itertools import pairwise

from pydantic import BaseModel, Field

from src.shared.schemas.dtm import Dtm
from src.shared.schemas.install_task import CxLevel


class DagNode(BaseModel):
    """One install task instance, scoped to a specific device."""

    node_id: str  # "<device_id>__<task_name>"
    device_id: str
    task_name: str
    crew_role: str
    cx_level: CxLevel
    est_minutes: int


class InstallDag(BaseModel):
    """Full DAG: ordered nodes + edges + critical-path node-id set."""

    nodes: list[DagNode]
    edges: list[tuple[str, str]] = Field(default_factory=list)
    critical_path: set[str] = Field(default_factory=set)


def build_install_dag(dtm: Dtm) -> InstallDag:
    """Expand DTM devices → per-device install tasks → layered DAG."""
    nodes = _build_nodes(dtm)
    edges = _intra_device_edges(nodes, dtm) + _cross_device_cx_edges(nodes)
    critical_path = _critical_path(nodes, edges)
    return InstallDag(nodes=nodes, edges=edges, critical_path=critical_path)


def _build_nodes(dtm: Dtm) -> list[DagNode]:
    """Flatten DTM devices to per-task DagNodes (sorted for determinism)."""
    out: list[DagNode] = []
    for device_id in sorted(dtm.devices):
        device = dtm.devices[device_id]
        template = dtm.templates_used[device.template]
        out.extend(
            DagNode(
                node_id=f"{device_id}__{task.name}",
                device_id=device_id,
                task_name=task.name,
                crew_role=task.crew_role,
                cx_level=task.cx_level,
                est_minutes=task.est_minutes,
            )
            for task in template.install_tasks
        )
    return out


def _intra_device_edges(nodes: list[DagNode], dtm: Dtm) -> list[tuple[str, str]]:
    """Per-device edges from each task's `depends_on` list."""
    name_to_id: dict[str, dict[str, str]] = {}
    for n in nodes:
        name_to_id.setdefault(n.device_id, {})[n.task_name] = n.node_id
    edges: list[tuple[str, str]] = []
    for device_id, names in name_to_id.items():
        device = dtm.devices[device_id]
        template = dtm.templates_used[device.template]
        for task in template.install_tasks:
            dst = names[task.name]
            edges.extend((names[dep_name], dst) for dep_name in task.depends_on)
    return edges


def _cross_device_cx_edges(nodes: list[DagNode]) -> list[tuple[str, str]]:
    """L(n) tasks depend on every L(n-1) task across all OTHER devices."""
    by_level: dict[CxLevel, list[DagNode]] = {}
    for n in nodes:
        by_level.setdefault(n.cx_level, []).append(n)
    levels_sorted = sorted(by_level)
    edges: list[tuple[str, str]] = []
    for prior, current in pairwise(levels_sorted):
        for src in by_level[prior]:
            for dst in by_level[current]:
                if src.device_id == dst.device_id:
                    continue  # intra-device gating handled by depends_on
                edges.append((src.node_id, dst.node_id))
    return edges


def _critical_path(nodes: list[DagNode], edges: list[tuple[str, str]]) -> set[str]:
    """Longest cumulative-est_minutes path through the DAG (CPM forward pass)."""
    preds: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for src, dst in edges:
        preds.setdefault(dst, []).append(src)
    earliest: dict[str, int] = {}
    chain: dict[str, str | None] = {}
    # Topological order: sort by cx_level then node_id (stable). All edges
    # advance in cx_level or stay within a device, so this respects them.
    order = sorted(nodes, key=lambda n: (n.cx_level.value, n.node_id))
    for node in order:
        prev_finishes = [(earliest[p], p) for p in preds[node.node_id]]
        if prev_finishes:
            best_finish, best_pred = max(prev_finishes)
            earliest[node.node_id] = best_finish + node.est_minutes
            chain[node.node_id] = best_pred
        else:
            earliest[node.node_id] = node.est_minutes
            chain[node.node_id] = None
    if not earliest:
        return set()
    end_node = max(earliest, key=lambda nid: earliest[nid])
    path: set[str] = set()
    cur: str | None = end_node
    while cur is not None:
        path.add(cur)
        cur = chain[cur]
    return path
