"""SizingService — composes the pure sizing math into a SizingPreview."""

from src.grid.region_validation import check_flex_preset
from src.shared.enums import BessCoupling, FlexLevel, ServiceType
from src.shared.schemas.configurator_grid import FlexObligation
from src.shared.schemas.grid_regions import GridRegionsConfig
from src.shared.schemas.sizing import SizingLimits, SizingPreview, SizingPreviewRequest
from src.sizing.sizing_flags import compute_flags
from src.sizing.sizing_internals import (
    bess_min_mwh,
    effective_service_type,
    firm_onsite_mw,
    flex_preview,
    grid_peak_mw,
    interconnection_level,
    limit_state,
    recommend,
    reserve_mwh,
    site_peak_mw,
)


class SizingService:
    """Pure closed-form sizing preview — no I/O per call, regions loaded once."""

    def __init__(self, *, regions: GridRegionsConfig) -> None:
        self._regions = regions

    def preview(self, request: SizingPreviewRequest) -> SizingPreview:
        """Composes site_peak/limit_state/recommend/flex/flags per CONTRACT §4.2/§5.

        Raises ValueError if request.grid.flex_obligation drifts from its
        preset (FL/D12) — the only region-dependent check expressible on
        this endpoint's narrower grid shape.
        """
        check_flex_preset(request.grid.flex_obligation, self._regions)

        grid = request.grid
        peak = site_peak_mw(request.gpu_variant, request.target_gpu_count)
        firm = firm_onsite_mw(request.onsite_generation)
        g_peak = grid_peak_mw(site_peak=peak, firm_onsite=firm)
        state = limit_state(g_peak, self._regions.defaults)
        level = interconnection_level(g_peak, self._regions.defaults)
        path, reason = recommend(
            deployment_context=request.deployment_context,
            market_region=grid.market_region,
            limit_state=state,
            bess_coupling=request.bess_coupling,
            grid_peak_mw=g_peak,
        )
        e_reserve = reserve_mwh(
            ride_through_hours=request.ride_through_hours, grid_peak_mw=g_peak
        )

        flex = None
        if effective_service_type(grid) == ServiceType.FLEXIBLE:
            fx = grid.flex_obligation or self._standard_preset()
            flex = flex_preview(
                grid_peak_mw=g_peak,
                flex_obligation=fx,
                e_reserve_mwh=e_reserve,
                usable_mwh=request.bess_capacity_mwh,
            )

        flags = compute_flags(
            grid=grid,
            limit_state=state,
            effective_service_type=effective_service_type(grid),
            bess_coupling_is_none=request.bess_coupling == BessCoupling.NONE,
            usable_mwh=request.bess_capacity_mwh,
            e_reserve_mwh=e_reserve,
            e_min_usable_mwh=flex.e_min_usable_mwh if flex else None,
            ride_through_hours=request.ride_through_hours,
        )

        region_cfg = (
            self._regions.regions.get(grid.market_region)
            if grid.market_region is not None
            else None
        )
        return SizingPreview(
            site_peak_mw=peak,
            firm_onsite_mw=firm,
            grid_peak_mw=g_peak,
            e_reserve_mwh=e_reserve,
            bess_min_mwh=bess_min_mwh(
                e_reserve_mwh=e_reserve, e_flex_mwh=flex.e_flex_mwh if flex else None
            ),
            interconnection_level=level,
            limit_state=state,
            limits=SizingLimits(
                distribution_limit_mw=self._regions.defaults.distribution_limit_mw,
                distribution_near_mw=self._regions.defaults.distribution_near_mw,
                large_load_mw=region_cfg.large_load_mw if region_cfg else None,
            ),
            recommended_path=path,
            recommended_reason=reason,
            flex=flex,
            flags=flags,
        )

    def _standard_preset(self) -> FlexObligation:
        """Absent flex_obligation + flexible -> use the `standard` preset (§4.2)."""
        preset = self._regions.flex_levels[FlexLevel.STANDARD]
        return FlexObligation(level=FlexLevel.STANDARD, **preset.model_dump())
