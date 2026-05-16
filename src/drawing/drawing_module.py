"""DI wiring for the drawing feature (SLD HMI SVG generator)."""

from src.drawing.drawing_controller import DrawingController
from src.drawing.sld_hmi_svg_service import SldHmiSvgService


class DrawingModule:
    """Composes the drawing-feature services + HTTP surface."""

    def __init__(self) -> None:
        self.sld_hmi_svg = SldHmiSvgService()
        self.router = DrawingController(self.sld_hmi_svg).router
