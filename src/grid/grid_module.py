"""DI wiring for grid."""

from src.grid.grid_controller import GridController
from src.shared.schemas.grid_regions import GridRegionsConfig


class GridModule:
    """Wraps the already-loaded GridRegionsConfig into a routable controller."""

    def __init__(self, *, regions: GridRegionsConfig) -> None:
        self.regions = regions
        self.router = GridController(regions).router
