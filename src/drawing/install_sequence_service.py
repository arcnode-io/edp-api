"""InstallSequenceService — PERT-style commissioning DAG as PDF.

Walks the DTM, expands per-device install_tasks, lays out as a layered
left-to-right graph using graphviz `dot`. Within-template ordering comes
from `depends_on`; cross-device ordering comes from BICSI commissioning
level (L1 → L2 → L3 → L4 → L5 milestone gates).

PDF only — this artifact is project-mgmt (Gantt-adjacent), not an
engineering drawing, so no DXF emission. Tooling depends on the
`dot` system binary; verify with `dot -V` before running.
"""

from pydantic import BaseModel

from src.drawing._install_dot import build_dot_source, render_pdf_via_dot
from src.drawing._install_dag import build_install_dag
from src.shared.schemas.dtm import Dtm


class InstallSequenceOutputs(BaseModel):
    """Bundle of rendered formats from one DAG build."""

    pdf: bytes


class InstallSequenceService:
    """Builds the install sequence DAG as a graphviz PDF."""

    def generate(self, dtm: Dtm, profile: str = "") -> InstallSequenceOutputs:
        """Build the DAG, emit DOT, render to PDF via graphviz."""
        dag = build_install_dag(dtm)
        dot_src = build_dot_source(
            dag, deployment_uuid=dtm.deployment_uuid, profile=profile
        )
        pdf = render_pdf_via_dot(dot_src)
        return InstallSequenceOutputs(pdf=pdf)
