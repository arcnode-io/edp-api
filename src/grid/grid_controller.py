"""Grid HTTP controller — GET /edp-api/grid/regions."""

from classy_fastapi import Routable, get

from src.shared.schemas.grid_regions import GridRegionsConfig


class GridController(Routable):
    """Serves the parsed grid_regions.yaml so other services can embed it."""

    def __init__(self, regions: GridRegionsConfig) -> None:
        super().__init__()
        self._regions = regions

    @get(
        "/edp-api/grid/regions",
        response_model=GridRegionsConfig,
        tags=["Grid"],
        summary="Region thresholds + flex-level presets from grid_regions.yaml",
    )
    async def get_regions(self) -> GridRegionsConfig:
        """Return the config loaded at startup — no params, no I/O per request."""
        return self._regions
