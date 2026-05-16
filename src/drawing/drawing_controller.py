"""Drawing HTTP controller — stateless re-render for runtime-evolving DTMs.

ems-device-api owns runtime topology CRUD (add/remove/update equipment per
the dynamic-topology architecture). When its in-memory DTM mutates, it calls
this endpoint with the new DTM body and gets back a fresh SVG without
re-running the full EDP pipeline. Authoring logic stays in one place
(SldHmiSvgService); no SVG-mutation duplication on the device-api side.
"""

from classy_fastapi import Routable, post
from fastapi import Response, status

from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.shared.schemas.dtm import Dtm


class DrawingController(Routable):
    """REST surface for drawing-feature artifacts that need ad-hoc re-render."""

    def __init__(self, service: SldHmiSvgService) -> None:
        super().__init__()
        self._service = service

    @post(
        "/edp-api/sld-hmi-svg",
        status_code=status.HTTP_200_OK,
        tags=["Drawing"],
        responses={200: {"content": {"image/svg+xml": {}}}},
    )
    async def render(self, dtm: Dtm) -> Response:
        """Render the SLD HMI SVG for a (possibly runtime-mutated) DTM.

        Pure function: same DTM in -> same SVG bytes out. Stateless; no
        side effects, no persistence. Called by ems-device-api on
        `POST /topology` after applying runtime CRUD to its cached DTM.
        """
        return Response(
            content=self._service.generate(dtm),
            media_type="image/svg+xml",
        )
