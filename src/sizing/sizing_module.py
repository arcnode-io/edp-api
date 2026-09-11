"""DI wiring for sizing."""

from src.shared.schemas.grid_regions import GridRegionsConfig
from src.sizing.sizing_controller import SizingController
from src.sizing.sizing_service import SizingService


class SizingModule:
    """Wires the already-loaded GridRegionsConfig into SizingService + Controller."""

    def __init__(self, *, regions: GridRegionsConfig) -> None:
        self.service = SizingService(regions=regions)
        self.router = SizingController(self.service).router
