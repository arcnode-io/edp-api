"""Render an InstallDag to a graphviz DOT source string and then to PDF.

Layout:
- `rankdir=LR` — left-to-right flow.
- One column rank per commissioning level (L1, L2, L3, ...).
- Each device's tasks become a chain of boxes within the column band.
- Crew role drives node color (electrician=orange, plumber=blue,
  it=green, general=gray).
- Critical-path edges drawn bold red so the bottleneck reads at a glance.

The PDF render shells out to the `dot` binary. Failure raises so the
caller can surface a clear error — `dot` is a hard runtime dep.
"""

import subprocess  # nosec B404 — fixed cmd subprocess use only, see render_pdf_via_dot
from uuid import UUID

from src.drawing._install_dag import InstallDag

_CREW_COLOR: dict[str, str] = {
    "electrician": "#f6c177",
    "plumber": "#9ccfd8",
    "it": "#a3be8c",
    "general": "#c8c8c8",
}


def build_dot_source(
    dag: InstallDag, *, deployment_uuid: UUID, profile: str = ""
) -> str:
    """Serialize the DAG to a graphviz DOT source string."""
    title = f"ARCNODE INSTALL SEQUENCE  ·  {deployment_uuid}"
    if profile:
        title += f"  ·  {profile}"
    lines: list[str] = [
        "digraph install_sequence {",
        "  rankdir=LR;",
        '  graph [fontname="Helvetica", fontsize=14, ' f'label="{title}", labelloc=t];',
        '  node  [fontname="Helvetica", fontsize=10, shape=box, '
        'style="rounded,filled"];',
        '  edge  [fontname="Helvetica", fontsize=9, color="#666666"];',
    ]
    lines.extend(_node_lines(dag))
    lines.extend(_rank_lines(dag))
    lines.extend(_edge_lines(dag))
    lines.append("}")
    return "\n".join(lines)


def render_pdf_via_dot(dot_source: str) -> bytes:
    """Pipe DOT source to `dot -Tpdf`, return PDF bytes. Raises on failure."""
    result = subprocess.run(  # nosec B603 — fixed absolute cmd, no shell
        ["/usr/bin/dot", "-Tpdf"],
        input=dot_source.encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return result.stdout


def _node_lines(dag: InstallDag) -> list[str]:
    out: list[str] = []
    for n in dag.nodes:
        label = f"{n.device_id}\\n{n.task_name}\\n{n.est_minutes}m · {n.crew_role}"
        color = _CREW_COLOR.get(n.crew_role, "#c8c8c8")
        out.append(f'  "{n.node_id}" [label="{label}", fillcolor="{color}"];')
    return out


def _rank_lines(dag: InstallDag) -> list[str]:
    """Force same-cx_level nodes into the same column rank."""
    by_level: dict[str, list[str]] = {}
    for n in dag.nodes:
        by_level.setdefault(n.cx_level.value, []).append(n.node_id)
    out: list[str] = []
    for level in sorted(by_level):
        ids = " ".join(f'"{nid}"' for nid in by_level[level])
        out.append(f"  {{ rank=same; {ids} }}")
    return out


def _edge_lines(dag: InstallDag) -> list[str]:
    cp = dag.critical_path
    out: list[str] = []
    for src, dst in dag.edges:
        on_cp = src in cp and dst in cp
        attrs = ' [color="#d04050", penwidth=2.5]' if on_cp else ""
        out.append(f'  "{src}" -> "{dst}"{attrs};')
    return out
