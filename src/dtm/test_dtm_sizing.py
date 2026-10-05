"""DTM sizing_params — the EMS-facing numbers the generator derives from the order."""

import pytest

from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.test_dtm_generator_fixtures import (
    _make_client,
    _manifest,
    _real_catalog,
    _resolution,
)
from src.shared.enums import (
    FlexLevel,
    GpuVariant,
    GridPath,
    MarketRegion,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import FlexObligation, Grid, WiresOwner
from src.sizing.sizing_internals import (
    flex_energy_mwh,
    grid_peak_mw,
    recharge_mw,
    reserve_mwh,
    site_peak_mw,
)


def test_sizing_params_reserve_floor_zero_by_default() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    assert actual.sizing_params.ride_through_hours == 0.0
    assert actual.sizing_params.bess_reserve_floor_mwh == 0.0
    assert actual.sizing_params.compute_shed_enabled is False


def test_sizing_params_carry_compute_shed_choice() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution().model_copy(update={"compute_shed_enabled": True})
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )
    # Assert
    assert actual.sizing_params.compute_shed_enabled is True


def test_sizing_params_reserve_floor_computed_from_ride_through_hours() -> None:
    # Arrange — same pure math the sizing-preview endpoint uses (no onsite gen)
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(container_count=1, ride_through_hours=2.0)
    expected_grid_peak = grid_peak_mw(
        site_peak=site_peak_mw(GpuVariant.H100_SXM, 56), firm_onsite=0.0
    )
    expected_reserve = reserve_mwh(
        ride_through_hours=2.0, grid_peak_mw=expected_grid_peak
    )

    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    assert actual.sizing_params.ride_through_hours == 2.0
    assert actual.sizing_params.bess_reserve_floor_mwh == pytest.approx(
        expected_reserve
    )


def test_sizing_params_compute_load_matches_site_peak() -> None:
    # Arrange — compute load and reserve share one per-container figure
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(container_count=1, ride_through_hours=2.0)
    expected_kw = site_peak_mw(GpuVariant.H100_SXM, 56) * 1000

    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    assert actual.sizing_params.P_compute_total_kW == pytest.approx(expected_kw)


def test_sizing_params_readiness_is_the_floor_when_site_is_not_flexible() -> None:
    # Arrange — fixture resolution is off-grid: no flex obligation
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(ride_through_hours=2.0)
    # Act
    sp = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    ).sizing_params
    # Assert
    assert (sp.bess_readiness_mwh, sp.bess_recharge_mw) == (
        sp.bess_reserve_floor_mwh,
        0.0,
    )


def test_sizing_params_readiness_adds_the_contracted_flex_energy() -> None:
    # Arrange — ERCOT heavy: 100% depth for 4 h, 20 h between events
    flex = FlexObligation(
        level=FlexLevel.HEAVY,
        depth_pct=100,
        max_duration_h=4,
        max_events_yr=60,
        min_interval_h=20,
        notice_s=600,
    )
    grid = Grid(
        path=GridPath.FLEXIBLE,
        wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
        market_region=MarketRegion.ERCOT,
        service_type=ServiceType.FLEXIBLE,
        flex_obligation=flex,
    )
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(ride_through_hours=2.0, grid=grid)
    g_peak = grid_peak_mw(
        site_peak=site_peak_mw(GpuVariant.H100_SXM, 56), firm_onsite=0.0
    )
    e_flex = flex_energy_mwh(grid_peak_mw=g_peak, flex_obligation=flex)
    # Act
    sp = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    ).sizing_params
    # Assert
    assert sp.bess_readiness_mwh == pytest.approx(sp.bess_reserve_floor_mwh + e_flex)
    assert sp.bess_recharge_mw == pytest.approx(
        recharge_mw(e_flex_mwh=e_flex, flex_obligation=flex)
    )
