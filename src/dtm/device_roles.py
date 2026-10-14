"""Template slugs that play the same role across GPU variants.

Each GPU variant has its own node + compute-module templates (templates are
1:1 with equipment; the module's power cap targets its own node template).
Code that asks "is this a GPU node / a compute container?" asks here.
"""

from typing import Final

GPU_NODE_TEMPLATES: Final[frozenset[str]] = frozenset({"gpu_node", "gpu_node_h100"})
COMPUTE_MODULE_TEMPLATES: Final[frozenset[str]] = frozenset(
    {"compute_module", "compute_module_h100"}
)
