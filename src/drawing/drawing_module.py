"""DI wiring for drawing services (HMI SVG, SLD eng, P&ID, comms, install graph)."""

from src.drawing.comms_diagram_service import CommsDiagramService
from src.drawing.drawing_controller import DrawingController
from src.drawing.install_graph_service import InstallGraphService
from src.drawing.pid_cooling_service import PidCoolingService
from src.drawing.sld_engineering_service import SldEngineeringService
from src.drawing.sld_hmi_svg_service import SldHmiSvgService


class DrawingModule:
    """Composes the drawing-feature services + HTTP surface."""

    def __init__(self) -> None:
        self.sld_hmi_svg = SldHmiSvgService()
        self.sld_engineering = SldEngineeringService()
        self.pid_cooling = PidCoolingService()
        self.comms_diagram = CommsDiagramService()
        self.install_graph = InstallGraphService()
        self.router = DrawingController(self.sld_hmi_svg).router
