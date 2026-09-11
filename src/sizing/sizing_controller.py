"""Sizing HTTP controller — POST /edp-api/sizing/preview."""

from classy_fastapi import Routable, post
from fastapi import HTTPException, status

from src.shared.schemas.sizing import SizingPreview, SizingPreviewRequest
from src.sizing.sizing_service import SizingService


class SizingController(Routable):
    """Sync, closed-form sizing preview — no I/O per request, < 300 ms."""

    def __init__(self, service: SizingService) -> None:
        super().__init__()
        self._service = service

    @post(
        "/edp-api/sizing/preview",
        response_model=SizingPreview,
        tags=["Sizing"],
        summary="Closed-form site sizing preview for the configurator",
    )
    async def preview(self, request: SizingPreviewRequest) -> SizingPreview:
        """Raises 422 on a region-dependent rule violation (FL/D12)."""
        try:
            return self._service.preview(request)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
            ) from e
