"""DI wiring for the drawing feature (SLD HMI SVG generator)."""

from src.drawing.sld_hmi_svg_service import SldHmiSvgService


class DrawingModule:
    """Composes the drawing-feature services for the pipeline to consume."""

    def __init__(self) -> None:
        self.sld_hmi_svg = SldHmiSvgService()
